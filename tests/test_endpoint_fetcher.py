"""Tests for endpoint_fetcher: fetching, streaming, env interpolation, precedence."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from openjury.batch_dataset import BatchCase, EndpointSpec
from openjury.endpoint_fetcher import (
    AgentEndpoint,
    EndpointFetchError,
    _collect_sse_stream,
    _walk_path,
    build_request_body,
    fetch_agent_response,
    fetch_all_responses,
    fetch_response,
    load_endpoints_file,
    resolve_headers,
)
from openjury.errors import EndpointErrorCode
from openjury.execution import ExecutionOptions


def test_build_request_body_default_no_stream() -> None:
    body = build_request_body(None, "hello", stream=False)
    assert body == {"messages": [{"role": "user", "content": "hello"}]}
    assert "stream" not in body


def test_build_request_body_default_with_stream() -> None:
    body = build_request_body(None, "hello", stream=True)
    assert body["stream"] is True
    assert body["messages"][0]["content"] == "hello"


def test_build_request_body_custom() -> None:
    template: Dict[str, Any] = {"prompt": "{prompt}", "max_tokens": 512}
    body = build_request_body(template, "test prompt", stream=False)
    assert body == {"prompt": "test prompt", "max_tokens": 512}


def test_build_request_body_custom_nested() -> None:
    template: Dict[str, Any] = {
        "messages": [{"role": "user", "content": "{prompt}"}],
        "model": "my-model",
    }
    body = build_request_body(template, "nested test", stream=False)
    assert body["messages"][0]["content"] == "nested test"
    assert body["model"] == "my-model"


def test_resolve_headers_env_interpolation() -> None:
    os.environ["MY_TEST_KEY"] = "secret-value"
    headers = resolve_headers({"Authorization": "Bearer ${MY_TEST_KEY}"})
    assert headers["Authorization"] == "Bearer secret-value"


def test_resolve_headers_missing_var() -> None:
    key = "OPENJURY_NONEXISTENT_VAR_XYZ"
    os.environ.pop(key, None)
    with pytest.raises(EndpointFetchError, match=key):
        resolve_headers({"Authorization": "Bearer ${" + key + "}"})


def test_resolve_headers_no_placeholders() -> None:
    headers = resolve_headers({"Content-Type": "application/json"})
    assert headers == {"Content-Type": "application/json"}


def test_walk_path_nested_dict() -> None:
    data = {"choices": [{"message": {"content": "hello"}}]}
    assert _walk_path(data, "choices.0.message.content") == "hello"


def test_walk_path_simple() -> None:
    assert _walk_path({"text": "hi"}, "text") == "hi"


def test_walk_path_missing_key() -> None:
    with pytest.raises(EndpointFetchError, match="not found"):
        _walk_path({"a": 1}, "b")


def test_walk_path_bad_index() -> None:
    with pytest.raises(EndpointFetchError):
        _walk_path({"a": []}, "a.0")


def test_build_request_body_ground_truth() -> None:
    template: Dict[str, Any] = {
        "prompt": "{prompt}",
        "reference": "{ground_truth}",
    }
    body = build_request_body(
        template, "user q", stream=False, ground_truth="expected answer"
    )
    assert body == {"prompt": "user q", "reference": "expected answer"}


def test_build_request_body_unknown_placeholder() -> None:
    template: Dict[str, Any] = {"text": "{unknown}"}
    with pytest.raises(EndpointFetchError, match="Unknown template placeholder"):
        build_request_body(template, "q", stream=False)


def test_walk_path_forbidden_segment() -> None:
    with pytest.raises(EndpointFetchError, match="Forbidden"):
        _walk_path({"__proto__": "bad"}, "__proto__")


def _mock_response(json_data: Dict[str, Any], status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    if status_code >= 400:
        import httpx

        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status_code}", request=MagicMock(), response=resp
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


def test_fetch_response_ok_openai_shape() -> None:
    ep = AgentEndpoint(
        url="http://localhost:8080/v1/chat/completions",
        alias="test-model",
        model_name="test/model",
    )
    openai_resp = {"choices": [{"message": {"content": "This is the answer."}}]}
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value = _mock_response(openai_resp)

        candidate = fetch_response(ep, "What is 2+2?")

    assert candidate.content == "This is the answer."
    assert candidate.alias == "test-model"
    assert candidate.model_name == "test/model"


def test_fetch_response_ok_simple_shape() -> None:
    ep = AgentEndpoint(
        url="http://localhost:8080/generate",
        request_body_template={"prompt": "{prompt}"},
        response_path="text",
    )
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value = _mock_response({"text": "Simple answer."})

        candidate = fetch_response(ep, "A question")

    assert candidate.content == "Simple answer."


def test_fetch_response_http_error() -> None:
    ep = AgentEndpoint(url="http://localhost:9999/chat")
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value = _mock_response({}, status_code=401)

        with pytest.raises(EndpointFetchError, match="HTTP 401"):
            fetch_response(ep, "test")


def test_fetch_response_timeout() -> None:
    import httpx

    ep = AgentEndpoint(url="http://localhost:9999/chat", timeout_s=5.0)
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.side_effect = httpx.TimeoutException("timed out")

        with pytest.raises(EndpointFetchError, match="timed out"):
            fetch_response(ep, "test")


def test_fetch_response_bad_path() -> None:
    ep = AgentEndpoint(
        url="http://localhost:8080/v1",
        response_path="wrong.path.here",
    )
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value = _mock_response({"text": "hello"})

        with pytest.raises(EndpointFetchError):
            fetch_response(ep, "test")


def _sse_lines(chunks: List[str], done: bool = True) -> List[str]:
    lines = [
        f"data: {json.dumps({'choices': [{'delta': {'content': c}}]})}" for c in chunks
    ]
    if done:
        lines.append("data: [DONE]")
    return lines


def _collect_sse(
    mock_resp: MagicMock, response_path: str = "choices.0.delta.content"
) -> str:
    content, _metadata = _collect_sse_stream(
        mock_resp,
        response_path,
        ExecutionOptions(stream_idle_timeout_s=30.0),
        idle_timeout_s=30.0,
        alias="test",
    )
    return content


def test_collect_sse_stream_assembles_chunks() -> None:
    mock_resp = MagicMock()
    mock_resp.iter_lines.return_value = iter(_sse_lines(["Hello", ", ", "world", "!"]))
    result = _collect_sse(mock_resp)
    assert result == "Hello, world!"


def test_collect_sse_stream_skips_empty_deltas() -> None:
    lines = [
        "data: " + json.dumps({"choices": [{"delta": {"content": "hi"}}]}),
        "data: " + json.dumps({"choices": [{"delta": {}}]}),
        "data: [DONE]",
    ]
    mock_resp = MagicMock()
    mock_resp.iter_lines.return_value = iter(lines)
    result = _collect_sse(mock_resp)
    assert result == "hi"


def test_collect_sse_stream_multiline_data_field() -> None:
    payload = json.dumps({"choices": [{"delta": {"content": "ab"}}]})
    mid = len(payload) // 2
    lines = [
        "data: " + payload[:mid],
        "data: " + payload[mid:],
        "",
        "data: [DONE]",
    ]
    mock_resp = MagicMock()
    mock_resp.iter_lines.return_value = iter(lines)
    result = _collect_sse(mock_resp)
    assert result == "ab"


def test_collect_sse_stream_response_too_large() -> None:
    huge = "x" * 200
    lines = [
        "data: " + json.dumps({"choices": [{"delta": {"content": huge}}]}),
        "data: [DONE]",
    ]
    mock_resp = MagicMock()
    mock_resp.iter_lines.return_value = iter(lines)
    options = ExecutionOptions(max_agent_response_bytes=50)
    with pytest.raises(EndpointFetchError, match="accumulated response exceeds"):
        _collect_sse_stream(
            mock_resp,
            "choices.0.delta.content",
            options,
            idle_timeout_s=30.0,
            alias="test",
        )


def test_fetch_agent_response_sets_idempotency_header() -> None:
    ep = AgentEndpoint(url="http://localhost:8080/v1")
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value = _mock_response(
            {"choices": [{"message": {"content": "ok"}}]}
        )

        fetch_agent_response(
            ep,
            "q",
            options=ExecutionOptions(idempotency_key="exe_123"),
        )

        headers = mock_client.post.call_args.kwargs["headers"]
        assert headers["Idempotency-Key"] == "exe_123"


def test_fetch_response_http_error_has_code() -> None:
    ep = AgentEndpoint(url="http://localhost:9999/chat")
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value = _mock_response({}, status_code=401)

        with pytest.raises(EndpointFetchError) as exc_info:
            fetch_response(ep, "test")
        assert exc_info.value.code == EndpointErrorCode.ENDPOINT_HTTP_ERROR


def test_fetch_response_streaming_sse() -> None:
    ep = AgentEndpoint(
        url="http://localhost:8080/stream", stream=True, alias="streamer"
    )
    sse_lines = _sse_lines(["The ", "answer ", "is 42."])

    mock_stream_resp = MagicMock()
    mock_stream_resp.raise_for_status.return_value = None
    mock_stream_resp.iter_lines.return_value = iter(sse_lines)
    mock_stream_resp.__enter__ = lambda s: s
    mock_stream_resp.__exit__ = MagicMock(return_value=False)

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.stream.return_value = mock_stream_resp

        candidate = fetch_response(ep, "What is the answer?")

    assert candidate.content == "The answer is 42."
    assert candidate.alias == "streamer"


def test_fetch_response_streaming_default_path_auto_switches() -> None:
    """When stream=True and response_path is at default, auto-use delta path."""
    ep = AgentEndpoint(url="http://localhost/stream", stream=True)
    assert ep.response_path == "choices.0.message.content"

    sse_lines = [
        "data: " + json.dumps({"choices": [{"delta": {"content": "auto"}}]}),
        "data: [DONE]",
    ]
    mock_stream_resp = MagicMock()
    mock_stream_resp.raise_for_status.return_value = None
    mock_stream_resp.iter_lines.return_value = iter(sse_lines)
    mock_stream_resp.__enter__ = lambda s: s
    mock_stream_resp.__exit__ = MagicMock(return_value=False)

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.stream.return_value = mock_stream_resp

        candidate = fetch_response(ep, "test")

    assert candidate.content == "auto"


def test_fetch_response_streaming_mid_error() -> None:
    ep = AgentEndpoint(url="http://localhost/stream", stream=True)

    mock_stream_resp = MagicMock()
    mock_stream_resp.raise_for_status.return_value = None
    mock_stream_resp.iter_lines.side_effect = RuntimeError("connection dropped")
    mock_stream_resp.__enter__ = lambda s: s
    mock_stream_resp.__exit__ = MagicMock(return_value=False)

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.stream.return_value = mock_stream_resp

        with pytest.raises(EndpointFetchError, match="SSE stream"):
            fetch_response(ep, "test")


def test_fetch_all_responses_parallel() -> None:
    endpoints = [
        AgentEndpoint(url="http://localhost/a", alias="a"),
        AgentEndpoint(url="http://localhost/b", alias="b"),
    ]
    responses = [
        _mock_response({"choices": [{"message": {"content": "answer-a"}}]}),
        _mock_response({"choices": [{"message": {"content": "answer-b"}}]}),
    ]

    call_count = 0

    def side_effect(url: str, **kwargs: Any) -> MagicMock:
        nonlocal call_count
        resp = responses[0] if "localhost/a" in url else responses[1]
        call_count += 1
        return resp

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.side_effect = side_effect

        candidates = fetch_all_responses(endpoints, "test prompt")

    assert len(candidates) == 2
    contents = {c.content for c in candidates}
    assert contents == {"answer-a", "answer-b"}


def test_fetch_all_responses_single_endpoint() -> None:
    ep = AgentEndpoint(url="http://localhost/only", alias="single")
    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.return_value = _mock_response(
            {"choices": [{"message": {"content": "solo answer"}}]}
        )
        candidates = fetch_all_responses([ep], "test")

    assert len(candidates) == 1
    assert candidates[0].content == "solo answer"


def test_fetch_all_responses_partial_failure() -> None:
    import httpx

    endpoints = [
        AgentEndpoint(url="http://localhost/ok", alias="ok"),
        AgentEndpoint(url="http://localhost/fail", alias="fail"),
    ]

    def side_effect(url: str, **kwargs: Any) -> MagicMock:
        if "fail" in url:
            mock_resp = _mock_response({}, status_code=500)
            return mock_resp
        return _mock_response({"choices": [{"message": {"content": "ok"}}]})

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.post.side_effect = side_effect

        with pytest.raises(EndpointFetchError, match="Failed to fetch from 1"):
            fetch_all_responses(endpoints, "test")


def test_fetch_all_responses_empty_raises() -> None:
    with pytest.raises(EndpointFetchError, match="No endpoints"):
        fetch_all_responses([], "test")


def _make_case(
    case_id: str = "c1",
    endpoints: List[Dict[str, Any]] | None = None,
) -> BatchCase:
    data: Dict[str, Any] = {"case_id": case_id, "prompt": "test prompt"}
    if endpoints:
        data["endpoints"] = endpoints
    return BatchCase.model_validate(data)


def _endpoint_spec(alias: str = "ep") -> EndpointSpec:
    return EndpointSpec(url="http://localhost/ep", alias=alias)


def _mock_fetch(content: str = "fetched") -> MagicMock:
    from openjury.config import AgentResponse

    mock = MagicMock(return_value=[AgentResponse(content=content)])
    return mock


def test_precedence_case_endpoints_over_global() -> None:
    from openjury.batch_dataset import resolve_endpoint

    case = _make_case(
        endpoints=[{"url": "http://localhost/case-ep", "alias": "case-ep"}]
    )
    global_eps = [_endpoint_spec("global")]

    endpoint = resolve_endpoint(case, global_eps)
    assert "case-ep" in endpoint.url


def test_precedence_global_endpoints_fallback() -> None:
    from openjury.batch_dataset import resolve_endpoint

    case_no_ep = BatchCase.model_validate({"case_id": "c2", "prompt": "p"})
    global_eps = [_endpoint_spec("global")]

    endpoint = resolve_endpoint(case_no_ep, global_eps)
    assert "global" in endpoint.url or "localhost" in endpoint.url


def test_precedence_no_source_raises() -> None:
    from openjury.batch_dataset import resolve_endpoint

    case = BatchCase.model_validate({"case_id": "c-empty", "prompt": "p"})

    with pytest.raises(EndpointFetchError, match="no endpoints"):
        resolve_endpoint(case, None)


def test_load_endpoints_file_valid(tmp_path: Path) -> None:
    data = [
        {"url": "http://localhost/a", "alias": "a"},
        {"url": "http://localhost/b", "alias": "b", "stream": True},
    ]
    f = tmp_path / "endpoints.json"
    f.write_text(json.dumps(data))
    endpoints = load_endpoints_file(str(f))
    assert len(endpoints) == 2
    assert endpoints[1].stream is True


def test_load_endpoints_file_not_array(tmp_path: Path) -> None:
    f = tmp_path / "bad.json"
    f.write_text(json.dumps({"url": "http://x"}))
    with pytest.raises(EndpointFetchError, match="must be a JSON array"):
        load_endpoints_file(str(f))


def test_load_endpoints_file_missing(tmp_path: Path) -> None:
    with pytest.raises(EndpointFetchError, match="Failed to load"):
        load_endpoints_file(str(tmp_path / "nonexistent.json"))


def test_prompts_file_txt(tmp_path: Path) -> None:
    f = tmp_path / "prompts.txt"
    f.write_text("First prompt\nSecond prompt\n\nThird prompt\n")

    from openjury.cli import _load_prompts_file

    prompts = _load_prompts_file(f)
    assert prompts == ["First prompt", "Second prompt", "Third prompt"]


def test_prompts_file_jsonl(tmp_path: Path) -> None:
    f = tmp_path / "prompts.jsonl"
    f.write_text(
        json.dumps({"prompt": "Alpha"}) + "\n" + json.dumps({"prompt": "Beta"}) + "\n"
    )

    from openjury.cli import _load_prompts_file

    prompts = _load_prompts_file(f)
    assert prompts == ["Alpha", "Beta"]
