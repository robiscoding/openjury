"""Fetch LLM responses from HTTP endpoints before jury evaluation."""

from __future__ import annotations

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel, Field

from openjury.config import AgentResponse

logger = logging.getLogger(__name__)

_DEFAULT_RESPONSE_PATH_NON_STREAM = "choices.0.message.content"
_DEFAULT_RESPONSE_PATH_STREAM = "choices.0.delta.content"


class EndpointFetchError(Exception):
    pass


class AgentEndpoint(BaseModel):
    url: str
    model_name: Optional[str] = None
    alias: Optional[str] = None
    headers: Dict[str, str] = Field(default_factory=dict)
    request_body_template: Optional[Dict[str, Any]] = None
    stream: bool = False
    response_path: str = _DEFAULT_RESPONSE_PATH_NON_STREAM
    timeout_s: float = 60.0


def resolve_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """Substitute ${VAR_NAME} placeholders in header values from environment."""
    resolved: Dict[str, str] = {}
    pattern = re.compile(r"\$\{([^}]+)\}")
    for key, value in headers.items():

        def _replace(m: re.Match) -> str:  # type: ignore[type-arg]
            var = m.group(1)
            val = os.environ.get(var)
            if val is None:
                raise EndpointFetchError(
                    f"Environment variable '{var}' referenced in endpoint headers is not set"
                )
            return val

        resolved[key] = pattern.sub(_replace, value)
    return resolved


def _substitute_prompt(obj: Any, prompt: str) -> Any:
    """Recursively substitute {prompt} in all string leaf values of a dict/list."""
    if isinstance(obj, str):
        return obj.replace("{prompt}", prompt)
    if isinstance(obj, dict):
        return {k: _substitute_prompt(v, prompt) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_substitute_prompt(item, prompt) for item in obj]
    return obj


def build_request_body(
    template: Optional[Dict[str, Any]], prompt: str, stream: bool
) -> Dict[str, Any]:
    """Build the POST body for an endpoint request.

    When template is None, uses the OpenAI chat completions shape and
    auto-injects "stream": true when stream=True.
    When a custom template is provided, {prompt} is substituted in all string
    leaf values; the caller is responsible for including "stream" if required.
    """
    if template is None:
        body: Dict[str, Any] = {
            "messages": [{"role": "user", "content": prompt}],
        }
        if stream:
            body["stream"] = True
        return body
    return _substitute_prompt(template, prompt)  # type: ignore[no-any-return]


def _walk_path(data: Any, path: str) -> str:
    """Walk a dot-notation path into a parsed JSON object and return a string."""
    parts = path.split(".")
    current: Any = data
    for part in parts:
        if isinstance(current, dict):
            if part not in current:
                raise EndpointFetchError(
                    f"Key '{part}' not found in response (path: {path})"
                )
            current = current[part]
        elif isinstance(current, list):
            try:
                idx = int(part)
            except ValueError:
                raise EndpointFetchError(
                    f"Expected integer index for list, got '{part}' (path: {path})"
                )
            if idx >= len(current):
                raise EndpointFetchError(
                    f"List index {idx} out of range (path: {path})"
                )
            current = current[idx]
        else:
            raise EndpointFetchError(
                f"Cannot traverse into {type(current).__name__} at '{part}' (path: {path})"
            )
    if not isinstance(current, str):
        raise EndpointFetchError(
            f"Expected string at path '{path}', got {type(current).__name__}"
        )
    return current


def _collect_sse_stream(response: httpx.Response, response_path: str) -> str:
    """Parse an SSE response and assemble all delta text chunks."""
    buffer: List[str] = []
    try:
        for raw_line in response.iter_lines():
            line = raw_line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[len("data:") :].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue
            try:
                text = _walk_path(chunk, response_path)
                if text:
                    buffer.append(text)
            except EndpointFetchError:
                pass
    except Exception as exc:
        raise EndpointFetchError(f"Error reading SSE stream: {exc}") from exc
    return "".join(buffer)


def fetch_response(endpoint: AgentEndpoint, prompt: str) -> AgentResponse:
    """Fetch a single response from one endpoint for one prompt."""
    try:
        resolved_headers = resolve_headers(endpoint.headers)
    except EndpointFetchError:
        raise

    effective_response_path = endpoint.response_path
    if endpoint.stream and endpoint.response_path == _DEFAULT_RESPONSE_PATH_NON_STREAM:
        effective_response_path = _DEFAULT_RESPONSE_PATH_STREAM

    body = build_request_body(endpoint.request_body_template, prompt, endpoint.stream)
    alias = endpoint.alias or endpoint.url

    logger.info(f"Fetching response from endpoint '{alias}' (stream={endpoint.stream})")

    try:
        if endpoint.stream:
            with httpx.Client(timeout=endpoint.timeout_s) as client:
                with client.stream(
                    "POST",
                    endpoint.url,
                    json=body,
                    headers=resolved_headers,
                ) as response:
                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        raise EndpointFetchError(
                            f"Endpoint '{alias}' returned HTTP {exc.response.status_code}"
                        ) from exc
                    content = _collect_sse_stream(response, effective_response_path)
        else:
            with httpx.Client(timeout=endpoint.timeout_s) as client:
                response = client.post(
                    endpoint.url,
                    json=body,
                    headers=resolved_headers,
                )
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    raise EndpointFetchError(
                        f"Endpoint '{alias}' returned HTTP {exc.response.status_code}"
                    ) from exc
                try:
                    data = response.json()
                except Exception as exc:
                    raise EndpointFetchError(
                        f"Endpoint '{alias}' response is not valid JSON: {exc}"
                    ) from exc
                content = _walk_path(data, effective_response_path)

    except EndpointFetchError:
        raise
    except httpx.TimeoutException as exc:
        raise EndpointFetchError(
            f"Endpoint '{alias}' timed out after {endpoint.timeout_s}s"
        ) from exc
    except Exception as exc:
        raise EndpointFetchError(f"Endpoint '{alias}' request failed: {exc}") from exc

    if not content:
        raise EndpointFetchError(f"Endpoint '{alias}' returned empty content")

    logger.info(f"Received response from endpoint '{alias}' ({len(content)} chars)")

    kwargs: Dict[str, Any] = {"content": content}
    if endpoint.model_name is not None:
        kwargs["model_name"] = endpoint.model_name
    if endpoint.alias is not None:
        kwargs["alias"] = endpoint.alias
    return AgentResponse(**kwargs)


def fetch_all_responses(
    endpoints: List[AgentEndpoint], prompt: str
) -> List[AgentResponse]:
    """Fetch responses from all endpoints in parallel for a single prompt.

    If any endpoint fails, raises EndpointFetchError immediately. (TODO: make behavior configurable)
    The order of returned responses matches the order of endpoints.
    """
    if not endpoints:
        raise EndpointFetchError("No endpoints provided")

    results: Dict[int, AgentResponse] = {}
    errors: List[str] = []

    max_workers = min(len(endpoints), 10)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(fetch_response, ep, prompt): i
            for i, ep in enumerate(endpoints)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except EndpointFetchError as exc:
                errors.append(str(exc))
            except Exception as exc:
                errors.append(f"Unexpected error from endpoint {idx}: {exc}")

    if errors:
        raise EndpointFetchError(
            f"Failed to fetch from {len(errors)} endpoint(s): {'; '.join(errors)}"
        )

    return [results[i] for i in range(len(endpoints))]


def load_endpoints_file(path: str) -> List[AgentEndpoint]:
    """Load a JSON file containing a list of AgentEndpoint objects."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        raise EndpointFetchError(
            f"Failed to load endpoints file '{path}': {exc}"
        ) from exc
    if not isinstance(data, list):
        raise EndpointFetchError(
            f"Endpoints file '{path}' must be a JSON array of endpoint objects"
        )
    try:
        return [AgentEndpoint.model_validate(item) for item in data]
    except Exception as exc:
        raise EndpointFetchError(f"Invalid endpoint spec in '{path}': {exc}") from exc
