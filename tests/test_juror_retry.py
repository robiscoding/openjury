"""Tests for juror transient retry behavior."""

from unittest.mock import MagicMock, patch

import httpx
import openai
import pytest

from openjury import AgentResponse, Juror
from openjury.errors import JurorErrorCode
from openjury.juror import JurorException, _is_transient_provider_error


def _mock_openai_response(content: str) -> MagicMock:
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    return mock_resp


def _openai_rate_limit_error() -> openai.RateLimitError:
    response = httpx.Response(
        429,
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )
    body = {
        "error": {
            "message": "Provider returned error",
            "code": 429,
            "metadata": {
                "raw": "upstream freeform text that must never leak downstream",
                "provider_name": "Darkbloom",
                "provider_error_code": "rate_limit_exceeded",
                "retry_after_seconds": 15,
            },
            "user_id": "user_abc123",
        }
    }
    return openai.RateLimitError(
        f"Error code: 429 - {body!r}", response=response, body=body
    )


@patch("openjury.juror.time.sleep")
@patch("openjury.juror.OpenAI")
def test_juror_retries_transient_provider_error(
    mock_openai_class,
    mock_sleep,
    sample_jurors,
    sample_llm_provider,
    sample_criteria,
    sample_prompt,
) -> None:
    mock_client = MagicMock()
    ok_response = _mock_openai_response(
        '{"scores": {"factuality": {"score": 4, "explanation": "ok"}, '
        '"clarity": {"score": 4, "explanation": "ok"}}}'
    )
    mock_client.chat.completions.create.side_effect = [
        RuntimeError("HTTP 503 service unavailable"),
        ok_response,
    ]
    mock_openai_class.return_value = mock_client

    juror = Juror(sample_jurors[0], jury_llm_provider=sample_llm_provider)
    result = juror.evaluate(
        prompt=sample_prompt,
        response=AgentResponse(content="answer", id="r1"),
        criteria=sample_criteria,
        max_retries=3,
    )

    assert result.criterion_scores["factuality"] == 4.0
    assert mock_client.chat.completions.create.call_count == 2
    mock_sleep.assert_called_once()


@patch("openjury.juror.time.sleep")
@patch("openjury.juror.OpenAI")
def test_juror_does_not_retry_missing_criteria(
    mock_openai_class,
    mock_sleep,
    sample_jurors,
    sample_llm_provider,
    sample_criteria,
    sample_prompt,
) -> None:
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = _mock_openai_response(
        '{"scores": {"factuality": {"score": 4, "explanation": "ok"}}}'
    )
    mock_openai_class.return_value = mock_client

    juror = Juror(sample_jurors[0], jury_llm_provider=sample_llm_provider)
    with pytest.raises(JurorException) as exc_info:
        juror.evaluate(
            prompt=sample_prompt,
            response=AgentResponse(content="answer", id="r1"),
            criteria=sample_criteria,
            max_retries=3,
        )

    assert exc_info.value.code == JurorErrorCode.JUROR_MISSING_CRITERIA
    assert mock_client.chat.completions.create.call_count == 1
    mock_sleep.assert_not_called()


def test_is_transient_provider_error_heuristics() -> None:
    assert _is_transient_provider_error(RuntimeError("rate limit exceeded"))
    assert not _is_transient_provider_error(
        JurorException("parse failed", code=JurorErrorCode.JUROR_MISSING_CRITERIA)
    )


def test_is_transient_provider_error_prefers_structured_status_over_message() -> None:
    # No transient substring markers in the message at all — must be classified
    # transient purely from the typed exception's status_code/body, not string matching.
    assert _is_transient_provider_error(_openai_rate_limit_error())


@patch("openjury.juror.time.sleep")
@patch("openjury.juror.OpenAI")
def test_juror_exhausted_retries_attaches_safe_provider_error_info(
    mock_openai_class,
    mock_sleep,
    sample_jurors,
    sample_llm_provider,
    sample_criteria,
    sample_prompt,
) -> None:
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = _openai_rate_limit_error()
    mock_openai_class.return_value = mock_client

    juror = Juror(sample_jurors[0], jury_llm_provider=sample_llm_provider)
    with pytest.raises(JurorException) as exc_info:
        juror.evaluate(
            prompt=sample_prompt,
            response=AgentResponse(content="answer", id="r1"),
            criteria=sample_criteria,
            max_retries=2,
        )

    info = exc_info.value.provider_error_info
    assert info is not None
    assert info.http_status == 429
    assert info.provider_error_code == "rate_limit_exceeded"
    assert info.retry_after_seconds == 15
    for banned in ("user_id", "user_abc123", "upstream freeform text"):
        assert banned not in info.safe_summary

    # The existing full-string message field is untouched for back-compat.
    assert "Last error:" in str(exc_info.value)
