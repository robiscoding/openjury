"""Tests for structured error types."""

import pytest

from openjury.errors import (
    EndpointErrorCode,
    EndpointFetchError,
    EvaluationErrorCode,
    InitializationErrorCode,
    JurorErrorCode,
    JurorException,
    OpenJuryError,
    OpenJuryEvaluationError,
    OpenJuryInitializationError,
)


def test_endpoint_fetch_error_default_code() -> None:
    err = EndpointFetchError("request failed")
    assert err.message == "request failed"
    assert err.code == EndpointErrorCode.ENDPOINT_ERROR
    assert str(err) == "request failed"


def test_endpoint_fetch_error_explicit_code() -> None:
    err = EndpointFetchError("timed out", code=EndpointErrorCode.ENDPOINT_TIMEOUT)
    assert err.code == EndpointErrorCode.ENDPOINT_TIMEOUT


def test_juror_exception_default_code() -> None:
    err = JurorException("parse failed")
    assert err.code == JurorErrorCode.JUROR_ERROR


def test_openjury_evaluation_error_default_code() -> None:
    err = OpenJuryEvaluationError("all jurors failed")
    assert err.code == EvaluationErrorCode.EVALUATION_ERROR


def test_openjury_initialization_error_default_code() -> None:
    err = OpenJuryInitializationError("no jurors")
    assert err.code == InitializationErrorCode.INITIALIZATION_ERROR


def test_errors_are_catchable_as_exception() -> None:
    with pytest.raises(OpenJuryError):
        raise EndpointFetchError("boom")

    with pytest.raises(Exception):
        raise JurorException("boom")
