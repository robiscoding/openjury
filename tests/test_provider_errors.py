"""Tests for the provider error normalization allowlist."""

import httpx
import openai
import pytest

from openjury.provider_errors import (
    ProviderErrorInfo,
    normalize_anthropic_error,
    normalize_openai_error,
    normalize_provider_error,
)


def _openai_status_error(body: object, status: int = 429) -> openai.APIStatusError:
    response = httpx.Response(
        status,
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )
    return openai.APIStatusError(
        f"Error code: {status} - {body!r}", response=response, body=body
    )


def _openrouter_429_body(**metadata_overrides: object) -> dict:
    metadata = {
        "raw": "upstream provider's own freeform error text, possibly sensitive",
        "provider_name": "Darkbloom",
        "is_byok": False,
        "provider_error_code": "rate_limit_exceeded",
        "retry_after_seconds": 15,
        "headers": {"x-ratelimit-remaining": "0", "x-secret-internal": "abc"},
    }
    metadata.update(metadata_overrides)
    return {
        "error": {
            "message": "Provider returned error",
            "code": 429,
            "metadata": metadata,
            "user_id": "user_abc123",
        }
    }


class TestNormalizeOpenAIError:
    def test_realistic_openrouter_429_extracts_allowlisted_fields(self) -> None:
        exc = _openai_status_error(_openrouter_429_body())
        info = normalize_openai_error(exc)

        assert info.http_status == 429
        assert info.provider_error_code == "rate_limit_exceeded"
        assert info.retry_after_seconds == 15
        assert info.provider_name == "Darkbloom"

    def test_leaked_fields_never_appear_in_safe_summary(self) -> None:
        exc = _openai_status_error(_openrouter_429_body())
        info = normalize_openai_error(exc)

        for banned in (
            "user_id",
            "user_abc123",
            "headers",
            "x-secret-internal",
            "is_byok",
            "upstream provider's own freeform error text",
        ):
            assert banned not in info.safe_summary

    def test_unrecognized_future_field_is_silently_absent(self) -> None:
        body = _openrouter_429_body(
            account_ticket_id="TCKT-99999",
            internal_customer_segment="enterprise-tier-3",
        )
        exc = _openai_status_error(body)
        info = normalize_openai_error(exc)

        assert "TCKT-99999" not in info.safe_summary
        assert "enterprise-tier-3" not in info.safe_summary
        # The allowlisted fields still made it through even with new keys present.
        assert info.provider_error_code == "rate_limit_exceeded"
        assert info.retry_after_seconds == 15

    def test_non_dict_body_falls_back_to_generic_status_summary(self) -> None:
        exc = _openai_status_error("some unparsed raw string body", status=500)
        info = normalize_openai_error(exc)

        assert info.provider_error_code is None
        assert info.retry_after_seconds is None
        assert info.safe_summary == "Provider returned HTTP 500."

    def test_missing_status_and_body_falls_back_to_fully_generic_summary(self) -> None:
        class _BareException(Exception):
            pass

        info = normalize_openai_error(_BareException("boom"))

        assert info.http_status is None
        assert info.safe_summary == "Provider returned an error."

    def test_dict_body_without_allowlisted_keys_falls_back_to_status_only(self) -> None:
        exc = _openai_status_error({"error": {"message": "opaque failure"}}, status=503)
        info = normalize_openai_error(exc)

        assert info.provider_error_code is None
        assert info.safe_summary == "Provider returned HTTP 503."
        assert "opaque failure" not in info.safe_summary


class TestNormalizeAnthropicError:
    def test_extracts_status_and_error_type(self) -> None:
        class _FakeAnthropicError(Exception):
            status_code = 429
            body = {
                "type": "error",
                "error": {"type": "rate_limit_error", "message": "..."},
            }

        info = normalize_anthropic_error(_FakeAnthropicError())
        assert info.http_status == 429
        assert info.provider_error_code == "rate_limit_error"

    def test_non_dict_body_falls_back(self) -> None:
        class _FakeAnthropicError(Exception):
            status_code = 500
            body = None

        info = normalize_anthropic_error(_FakeAnthropicError())
        assert info.safe_summary == "Provider returned HTTP 500."


class TestNormalizeProviderErrorDispatch:
    def test_dispatches_openai_status_error(self) -> None:
        exc = _openai_status_error(_openrouter_429_body())
        info = normalize_provider_error(exc)
        assert info.provider_error_code == "rate_limit_exceeded"

    def test_unknown_exception_falls_back_to_status_only(self) -> None:
        class _WeirdError(Exception):
            status_code = 502

        info = normalize_provider_error(_WeirdError())
        assert info == ProviderErrorInfo(
            http_status=502, safe_summary="Provider returned HTTP 502."
        )

    def test_unknown_exception_without_status_is_fully_generic(self) -> None:
        info = normalize_provider_error(RuntimeError("network exploded"))
        assert info.http_status is None
        assert info.safe_summary == "Provider returned an error."
        assert "network exploded" not in info.safe_summary
