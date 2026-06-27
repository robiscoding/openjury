"""Structured errors with stable codes for programmatic handling."""

from __future__ import annotations

from enum import StrEnum


class EndpointErrorCode(StrEnum):
    ENDPOINT_ERROR = "endpoint_error"
    ENDPOINT_TIMEOUT = "endpoint_timeout"
    ENDPOINT_HTTP_ERROR = "endpoint_http_error"
    ENDPOINT_EMPTY_RESPONSE = "endpoint_empty_response"
    ENDPOINT_RESPONSE_TOO_LARGE = "endpoint_response_too_large"
    ENDPOINT_INVALID_PATH = "endpoint_invalid_path"
    ENDPOINT_TEMPLATE_ERROR = "endpoint_template_error"
    ENDPOINT_INVALID_JSON = "endpoint_invalid_json"
    SSE_IDLE_TIMEOUT = "sse_idle_timeout"
    SSE_EVENT_TOO_LARGE = "sse_event_too_large"
    SSE_MALFORMED = "sse_malformed"


class JurorErrorCode(StrEnum):
    JUROR_ERROR = "juror_error"
    JUROR_PARSE_ERROR = "juror_parse_error"
    JUROR_MISSING_CRITERIA = "juror_missing_criteria"
    JUROR_PROVIDER_ERROR = "juror_provider_error"


class EvaluationErrorCode(StrEnum):
    EVALUATION_ERROR = "evaluation_error"
    ALL_JURORS_FAILED = "all_jurors_failed"
    EVALUATION_CANCELLED = "evaluation_cancelled"


class InitializationErrorCode(StrEnum):
    INITIALIZATION_ERROR = "initialization_error"


class OpenJuryError(Exception):
    """Base exception with a stable machine-readable code."""

    default_code: str = "openjury_error"

    def __init__(self, message: str, code: str | None = None) -> None:
        self.message = message
        self.code = code or self.default_code
        super().__init__(message)

    def __str__(self) -> str:
        return self.message


class EndpointFetchError(OpenJuryError):
    default_code = EndpointErrorCode.ENDPOINT_ERROR


class JurorException(OpenJuryError):
    default_code = JurorErrorCode.JUROR_ERROR


class OpenJuryEvaluationError(OpenJuryError):
    default_code = EvaluationErrorCode.EVALUATION_ERROR


class OpenJuryInitializationError(OpenJuryError):
    default_code = InitializationErrorCode.INITIALIZATION_ERROR
