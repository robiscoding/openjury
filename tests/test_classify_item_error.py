"""Tests for batch item error classification."""

from openjury.errors import (
    EndpointErrorCode,
    EndpointFetchError,
    EvaluationErrorCode,
    OpenJuryEvaluationError,
)
from openjury.execution import EvalItemStatus, classify_item_error


def test_endpoint_fetch_error_maps_to_agent_stage() -> None:
    exc = EndpointFetchError("timeout", code=EndpointErrorCode.ENDPOINT_TIMEOUT)
    status, code, stage = classify_item_error(exc)
    assert status == EvalItemStatus.AGENT_FAILED
    assert code == EndpointErrorCode.ENDPOINT_TIMEOUT
    assert stage == "agent"


def test_all_jurors_failed_maps_to_juror_stage() -> None:
    exc = OpenJuryEvaluationError(
        "all jurors failed",
        code=EvaluationErrorCode.ALL_JURORS_FAILED,
    )
    status, code, stage = classify_item_error(exc)
    assert status == EvalItemStatus.ALL_JURORS_FAILED
    assert code == EvaluationErrorCode.ALL_JURORS_FAILED
    assert stage == "juror"


def test_cancelled_maps_to_infrastructure_stage() -> None:
    exc = OpenJuryEvaluationError(
        "cancelled",
        code=EvaluationErrorCode.EVALUATION_CANCELLED,
    )
    status, code, stage = classify_item_error(exc)
    assert status == EvalItemStatus.CANCELLED
    assert stage == "infrastructure"
