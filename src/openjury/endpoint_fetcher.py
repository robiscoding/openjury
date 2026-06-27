"""Fetch LLM responses from HTTP endpoints before jury evaluation."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Literal, Optional, Tuple

import httpx
from pydantic import BaseModel, Field

from openjury.config import AgentResponse
from openjury.errors import (
    EndpointErrorCode,
    EndpointFetchError,
    OpenJuryEvaluationError,
)
from openjury.execution import (
    ExecutionOptions,
    FetchMetadata,
    FetchResult,
    ProgressEvent,
    ProgressEventType,
)

logger = logging.getLogger(__name__)

_DEFAULT_RESPONSE_PATH_NON_STREAM = "choices.0.message.content"
_DEFAULT_RESPONSE_PATH_STREAM = "choices.0.delta.content"
_FORBIDDEN_PATH_SEGMENTS = frozenset({"__proto__", "prototype", "constructor"})
_KNOWN_TEMPLATE_PLACEHOLDERS = frozenset({"prompt", "ground_truth"})
_PLACEHOLDER_PATTERN = re.compile(r"\{(\w+)\}")


class AgentEndpoint(BaseModel):
    url: str
    model_name: Optional[str] = None
    alias: Optional[str] = None
    headers: Dict[str, str] = Field(default_factory=dict)
    request_body_template: Optional[Dict[str, Any]] = None
    stream: bool = False
    response_path: str = _DEFAULT_RESPONSE_PATH_NON_STREAM
    timeout_s: float = 60.0
    stream_idle_timeout_s: Optional[float] = None


def _default_options(options: ExecutionOptions | None) -> ExecutionOptions:
    return options if options is not None else ExecutionOptions()


def _effective_stream_idle_timeout(
    endpoint: AgentEndpoint, options: ExecutionOptions
) -> float:
    if endpoint.stream_idle_timeout_s is not None:
        return endpoint.stream_idle_timeout_s
    return options.stream_idle_timeout_s


def resolve_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """Substitute ${VAR_NAME} placeholders in header values from environment."""
    resolved: Dict[str, str] = {}
    pattern = re.compile(r"\$\{([^}]+)\}")
    for key, value in headers.items():

        def _replace(m: re.Match[str]) -> str:
            var = m.group(1)
            val = os.environ.get(var)
            if val is None:
                raise EndpointFetchError(
                    f"Environment variable '{var}' referenced in endpoint headers is not set"
                )
            return val

        resolved[key] = pattern.sub(_replace, value)
    return resolved


def _substitute_string(value: str, *, prompt: str, ground_truth: str) -> str:
    unknown = set(_PLACEHOLDER_PATTERN.findall(value)) - _KNOWN_TEMPLATE_PLACEHOLDERS
    if unknown:
        raise EndpointFetchError(
            f"Unknown template placeholder(s): {sorted(unknown)}",
            code=EndpointErrorCode.ENDPOINT_TEMPLATE_ERROR,
        )
    return value.replace("{prompt}", prompt).replace("{ground_truth}", ground_truth)


def _substitute_template_values(
    obj: Any,
    *,
    prompt: str,
    ground_truth: str | None = None,
) -> Any:
    """Recursively substitute {prompt} and {ground_truth} in string leaf values."""
    gt = ground_truth or ""
    if isinstance(obj, str):
        return _substitute_string(obj, prompt=prompt, ground_truth=gt)
    if isinstance(obj, dict):
        return {
            k: _substitute_template_values(v, prompt=prompt, ground_truth=ground_truth)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [
            _substitute_template_values(item, prompt=prompt, ground_truth=ground_truth)
            for item in obj
        ]
    return obj


def build_request_body(
    template: Optional[Dict[str, Any]],
    prompt: str,
    stream: bool,
    *,
    ground_truth: str | None = None,
) -> Dict[str, Any]:
    """Build the POST body for an endpoint request."""
    if template is None:
        body: Dict[str, Any] = {
            "messages": [{"role": "user", "content": prompt}],
        }
        if stream:
            body["stream"] = True
        return body
    return _substitute_template_values(  # type: ignore[no-any-return]
        template, prompt=prompt, ground_truth=ground_truth
    )


def _walk_path(data: Any, path: str) -> str:
    """Walk a dot-notation path into a parsed JSON object and return a string."""
    parts = path.split(".")
    for part in parts:
        if part in _FORBIDDEN_PATH_SEGMENTS:
            raise EndpointFetchError(
                f"Forbidden response path segment '{part}'",
                code=EndpointErrorCode.ENDPOINT_INVALID_PATH,
            )
        if isinstance(data, dict):
            if part not in data:
                raise EndpointFetchError(
                    f"Key '{part}' not found in response (path: {path})"
                )
            data = data[part]
        elif isinstance(data, list):
            try:
                idx = int(part)
            except ValueError:
                raise EndpointFetchError(
                    f"Expected integer index for list, got '{part}' (path: {path})"
                )
            if idx >= len(data):
                raise EndpointFetchError(
                    f"List index {idx} out of range (path: {path})"
                )
            data = data[idx]
        else:
            raise EndpointFetchError(
                f"Cannot traverse into {type(data).__name__} at '{part}' (path: {path})"
            )
    if not isinstance(data, str):
        raise EndpointFetchError(
            f"Expected string at path '{path}', got {type(data).__name__}"
        )
    return data


def _enforce_response_size(content: str, options: ExecutionOptions, alias: str) -> None:
    size = len(content.encode("utf-8"))
    if size > options.max_agent_response_bytes:
        raise EndpointFetchError(
            f"Endpoint '{alias}' response exceeds {options.max_agent_response_bytes} bytes",
            code=EndpointErrorCode.ENDPOINT_RESPONSE_TOO_LARGE,
        )


def _emit_progress(options: ExecutionOptions, event: ProgressEvent) -> None:
    if options.on_progress is not None:
        options.on_progress(event)


def _collect_sse_stream(
    response: httpx.Response,
    response_path: str,
    options: ExecutionOptions,
    *,
    idle_timeout_s: float,
    alias: str,
) -> Tuple[str, FetchMetadata]:
    """Parse an SSE response and assemble all delta text chunks."""
    start = time.monotonic()
    last_activity = start
    buffer: List[str] = []
    data_lines: List[str] = []
    chunk_count = 0
    first_chunk_latency_ms: int | None = None
    accumulated_bytes = 0

    def process_payload(payload: str) -> Literal["done", "continue"]:
        nonlocal chunk_count, first_chunk_latency_ms, accumulated_bytes, last_activity

        if payload == "[DONE]":
            return "done"

        payload_bytes = len(payload.encode("utf-8"))
        if payload_bytes > options.max_sse_event_bytes:
            raise EndpointFetchError(
                f"SSE event payload exceeds {options.max_sse_event_bytes} bytes",
                code=EndpointErrorCode.SSE_EVENT_TOO_LARGE,
            )

        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise EndpointFetchError(
                f"Malformed SSE event JSON: {exc}",
                code=EndpointErrorCode.SSE_MALFORMED,
            ) from exc

        try:
            text = _walk_path(chunk, response_path)
        except EndpointFetchError:
            return "continue"

        if not text:
            return "continue"

        text_bytes = len(text.encode("utf-8"))
        if accumulated_bytes + text_bytes > options.max_agent_response_bytes:
            raise EndpointFetchError(
                f"Endpoint '{alias}' accumulated response exceeds "
                f"{options.max_agent_response_bytes} bytes",
                code=EndpointErrorCode.ENDPOINT_RESPONSE_TOO_LARGE,
            )

        buffer.append(text)
        chunk_count += 1
        accumulated_bytes += text_bytes
        if first_chunk_latency_ms is None:
            first_chunk_latency_ms = int((time.monotonic() - start) * 1000)
        last_activity = time.monotonic()
        _emit_progress(
            options,
            ProgressEvent(
                type=ProgressEventType.AGENT_CHUNK,
                chunk_count=chunk_count,
                accumulated_bytes=accumulated_bytes,
            ),
        )
        return "continue"

    def flush_event(*, force: bool = False) -> Literal["done", "continue"]:
        if not data_lines:
            return "continue"

        payload = "\n".join(data_lines)
        if not force:
            try:
                json.loads(payload)
            except json.JSONDecodeError:
                return "continue"

        data_lines.clear()
        return process_payload(payload)

    try:
        for raw_line in response.iter_lines():
            options.check_cancelled()

            now = time.monotonic()
            if now - last_activity > idle_timeout_s:
                raise EndpointFetchError(
                    f"Endpoint '{alias}' SSE stream idle for {idle_timeout_s}s",
                    code=EndpointErrorCode.SSE_IDLE_TIMEOUT,
                )

            line = raw_line.rstrip("\r")
            if not line:
                status = flush_event(force=True)
                if status == "done":
                    break
                continue

            if line.startswith(":"):
                continue

            if not line.startswith("data:"):
                continue

            piece = line[len("data:") :].lstrip()
            if piece == "[DONE]":
                break

            data_lines.append(piece)
            status = flush_event(force=False)
            if status == "done":
                break

        if data_lines:
            flush_event(force=True)

    except EndpointFetchError:
        raise
    except Exception as exc:
        raise EndpointFetchError(
            f"Error reading SSE stream: {exc}",
            code=EndpointErrorCode.SSE_MALFORMED,
        ) from exc

    content = "".join(buffer)
    metadata = FetchMetadata(
        stream=True,
        chunk_count=chunk_count,
        first_chunk_latency_ms=first_chunk_latency_ms,
        total_latency_ms=int((time.monotonic() - start) * 1000),
        accumulated_bytes=accumulated_bytes,
    )
    return content, metadata


def _build_request_headers(
    endpoint: AgentEndpoint,
    resolved_headers: Dict[str, str],
    options: ExecutionOptions,
) -> Dict[str, str]:
    headers = dict(resolved_headers)
    if options.idempotency_key:
        headers["Idempotency-Key"] = options.idempotency_key
    return headers


def _agent_response_from_content(
    endpoint: AgentEndpoint, content: str
) -> AgentResponse:
    kwargs: Dict[str, Any] = {"content": content}
    if endpoint.model_name is not None:
        kwargs["model_name"] = endpoint.model_name
    if endpoint.alias is not None:
        kwargs["alias"] = endpoint.alias
    return AgentResponse(**kwargs)


def fetch_agent_response(
    endpoint: AgentEndpoint,
    prompt: str,
    *,
    options: ExecutionOptions | None = None,
) -> FetchResult:
    """Fetch a single agent response from one endpoint for one prompt."""
    opts = _default_options(options)
    opts.check_cancelled()

    resolved_headers = resolve_headers(endpoint.headers)
    request_headers = _build_request_headers(endpoint, resolved_headers, opts)

    effective_response_path = endpoint.response_path
    if endpoint.stream and endpoint.response_path == _DEFAULT_RESPONSE_PATH_NON_STREAM:
        effective_response_path = _DEFAULT_RESPONSE_PATH_STREAM

    body = build_request_body(
        endpoint.request_body_template,
        prompt,
        endpoint.stream,
        ground_truth=opts.ground_truth,
    )
    alias = endpoint.alias or endpoint.url
    idle_timeout_s = _effective_stream_idle_timeout(endpoint, opts)

    logger.info(f"Fetching response from endpoint '{alias}' (stream={endpoint.stream})")
    _emit_progress(opts, ProgressEvent(type=ProgressEventType.AGENT_STARTED))

    start = time.monotonic()
    metadata = FetchMetadata(stream=endpoint.stream)

    try:
        with opts.outbound_slot():
            if endpoint.stream:
                with httpx.Client(
                    timeout=endpoint.timeout_s, follow_redirects=False
                ) as client:
                    with client.stream(
                        "POST",
                        endpoint.url,
                        json=body,
                        headers=request_headers,
                    ) as response:
                        try:
                            response.raise_for_status()
                        except httpx.HTTPStatusError as exc:
                            raise EndpointFetchError(
                                f"Endpoint '{alias}' returned HTTP {exc.response.status_code}",
                                code=EndpointErrorCode.ENDPOINT_HTTP_ERROR,
                            ) from exc
                        content, metadata = _collect_sse_stream(
                            response,
                            effective_response_path,
                            opts,
                            idle_timeout_s=idle_timeout_s,
                            alias=alias,
                        )
            else:
                with httpx.Client(
                    timeout=endpoint.timeout_s, follow_redirects=False
                ) as client:
                    response = client.post(
                        endpoint.url,
                        json=body,
                        headers=request_headers,
                    )
                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        raise EndpointFetchError(
                            f"Endpoint '{alias}' returned HTTP {exc.response.status_code}",
                            code=EndpointErrorCode.ENDPOINT_HTTP_ERROR,
                        ) from exc
                    try:
                        data = response.json()
                    except Exception as exc:
                        raise EndpointFetchError(
                            f"Endpoint '{alias}' response is not valid JSON: {exc}",
                            code=EndpointErrorCode.ENDPOINT_INVALID_JSON,
                        ) from exc
                    content = _walk_path(data, effective_response_path)
                    metadata = FetchMetadata(
                        stream=False,
                        accumulated_bytes=len(content.encode("utf-8")),
                        total_latency_ms=int((time.monotonic() - start) * 1000),
                    )

    except EndpointFetchError:
        raise
    except httpx.TimeoutException as exc:
        raise EndpointFetchError(
            f"Endpoint '{alias}' timed out after {endpoint.timeout_s}s",
            code=EndpointErrorCode.ENDPOINT_TIMEOUT,
        ) from exc
    except OpenJuryEvaluationError:
        raise
    except Exception as exc:
        raise EndpointFetchError(
            f"Endpoint '{alias}' request failed: {exc}",
        ) from exc

    if not content:
        raise EndpointFetchError(
            f"Endpoint '{alias}' returned empty content",
            code=EndpointErrorCode.ENDPOINT_EMPTY_RESPONSE,
        )

    _enforce_response_size(content, opts, alias)

    logger.info(f"Received response from endpoint '{alias}' ({len(content)} chars)")
    _emit_progress(opts, ProgressEvent(type=ProgressEventType.AGENT_COMPLETED))

    return FetchResult(
        response=_agent_response_from_content(endpoint, content),
        metadata=metadata,
    )


def fetch_response(
    endpoint: AgentEndpoint,
    prompt: str,
    *,
    options: ExecutionOptions | None = None,
) -> AgentResponse:
    """Fetch a single response; returns AgentResponse only (backward compatible)."""
    return fetch_agent_response(endpoint, prompt, options=options).response


def fetch_all_responses(
    endpoints: List[AgentEndpoint],
    prompt: str,
    *,
    options: ExecutionOptions | None = None,
) -> List[AgentResponse]:
    """Fetch responses from all endpoints in parallel for a single prompt."""
    if not endpoints:
        raise EndpointFetchError("No endpoints provided")

    results: Dict[int, AgentResponse] = {}
    errors: List[str] = []

    max_workers = min(len(endpoints), 10)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(fetch_agent_response, ep, prompt, options=options): i
            for i, ep in enumerate(endpoints)
        }
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result().response
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
