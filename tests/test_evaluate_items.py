"""Tests for evaluate_items batch orchestration."""

from unittest.mock import MagicMock, patch

import pytest

from openjury import AgentResponse, AssertionConfig, OpenJury
from openjury.endpoint_fetcher import AgentEndpoint, EndpointFetchError
from openjury.errors import EvaluationErrorCode, OpenJuryEvaluationError
from openjury.execution import (
    EvalItemStatus,
    EvaluationItem,
    ExecutionOptions,
    FetchMetadata,
    FetchResult,
)
from openjury.scoring import JurorScore


def _fetch_result(content: str) -> FetchResult:
    return FetchResult(
        response=AgentResponse(content=content),
        metadata=FetchMetadata(),
    )


def _score(name: str) -> JurorScore:
    return JurorScore(
        juror_name=name,
        juror_weight=1.0,
        criterion_scores={"factuality": 4.0, "clarity": 4.0},
        criterion_explanations={"factuality": "ok", "clarity": "ok"},
    )


def _make_juror_mocks(mock_juror_class: MagicMock) -> None:
    def make_juror(name: str) -> MagicMock:
        m = MagicMock()
        m.name = name
        m.config.weight = 1.0
        m.evaluate.return_value = _score(name)
        return m

    mock_juror_class.side_effect = [make_juror("Juror A"), make_juror("Juror B")]


@patch("openjury.jury_engine.fetch_agent_response")
@patch("openjury.jury_engine.Juror")
def test_evaluate_items_returns_all_results(
    mock_juror_class, mock_fetch, sample_jury_config
) -> None:
    mock_fetch.side_effect = [
        _fetch_result("answer one"),
        _fetch_result("answer two"),
    ]
    _make_juror_mocks(mock_juror_class)

    jury = OpenJury(sample_jury_config)
    items = [
        EvaluationItem(prompt="Q1?", item_id="item-1"),
        EvaluationItem(prompt="Q2?", item_id="item-2", ground_truth="gt"),
    ]
    endpoint = AgentEndpoint(url="http://localhost/v1")

    results = jury.evaluate_items(
        items,
        endpoint,
        options=ExecutionOptions(max_item_workers=1),
    )

    assert len(results) == 2
    assert all(r.result is not None for r in results)
    assert results[0].item.item_id == "item-1"
    assert mock_fetch.call_count == 2


@patch("openjury.jury_engine.fetch_agent_response")
@patch("openjury.jury_engine.Juror")
def test_evaluate_items_uses_per_item_assertions(
    mock_juror_class, mock_fetch, sample_jury_config
) -> None:
    mock_fetch.side_effect = [
        _fetch_result("alpha"),
        _fetch_result("beta"),
    ]
    _make_juror_mocks(mock_juror_class)
    common = {"type": "contains", "required": True}
    items = [
        EvaluationItem(
            prompt="Q1?",
            assertions=[AssertionConfig(name="expects alpha", value="alpha", **common)],
        ),
        EvaluationItem(
            prompt="Q2?",
            assertions=[AssertionConfig(name="expects beta", value="beta", **common)],
        ),
    ]

    results = OpenJury(sample_jury_config).evaluate_items(
        items,
        AgentEndpoint(url="http://localhost/v1"),
        options=ExecutionOptions(max_item_workers=1),
    )

    assert results[0].result is not None
    assert results[1].result is not None
    assert results[0].result.assertion_results[0].name == "expects alpha"
    assert results[1].result.assertion_results[0].name == "expects beta"
    assert all(item.result.assertions_passed for item in results if item.result)


@patch("openjury.jury_engine.fetch_agent_response")
@patch("openjury.jury_engine.Juror")
def test_evaluate_items_collects_errors_without_raising(
    mock_juror_class, mock_fetch, sample_jury_config
) -> None:
    mock_fetch.side_effect = [
        _fetch_result("ok"),
        EndpointFetchError("fetch failed"),
    ]
    _make_juror_mocks(mock_juror_class)

    jury = OpenJury(sample_jury_config)
    results = jury.evaluate_items(
        [
            EvaluationItem(prompt="ok"),
            EvaluationItem(prompt="fail"),
        ],
        AgentEndpoint(url="http://localhost/v1"),
    )

    assert results[0].result is not None
    assert results[0].error is None
    assert results[1].result is None
    assert results[0].error is None
    assert results[1].result is None
    assert results[1].error is not None
    assert results[1].status == EvalItemStatus.AGENT_FAILED
    assert results[1].error_stage == "agent"
    assert results[1].evaluation_duration_ms is not None


@patch("openjury.jury_engine.fetch_agent_response")
@patch("openjury.jury_engine.Juror")
def test_evaluate_items_populates_item_context_fields(
    mock_juror_class, mock_fetch, sample_jury_config
) -> None:
    mock_fetch.return_value = _fetch_result("ok")
    _make_juror_mocks(mock_juror_class)
    sample_jury_config.assertion_policy.quality_threshold = 4.0

    jury = OpenJury(sample_jury_config)
    results = jury.evaluate_items(
        [
            EvaluationItem(
                prompt="Q?",
                item_id="case-1",
                metadata={"topic": "rest"},
                quality_threshold=4.0,
            )
        ],
        AgentEndpoint(url="http://localhost/v1"),
    )

    result = results[0].result
    assert result is not None
    assert result.item_id == "case-1"
    assert result.metadata == {"topic": "rest"}
    assert result.quality_threshold == 4.0
    assert result.quality_passed is True
    assert result.evaluation_duration_ms is not None
    assert results[0].status == EvalItemStatus.SCORED


@patch("openjury.jury_engine.fetch_agent_response")
@patch("openjury.jury_engine.Juror")
def test_evaluate_items_with_summary_returns_aggregate_metrics(
    mock_juror_class, mock_fetch, sample_jury_config
) -> None:
    mock_fetch.side_effect = [_fetch_result("one"), _fetch_result("two")]
    _make_juror_mocks(mock_juror_class)

    batch = OpenJury(sample_jury_config).evaluate_items_with_summary(
        [
            EvaluationItem(prompt="Q1?", item_id="one"),
            EvaluationItem(prompt="Q2?", item_id="two"),
        ],
        AgentEndpoint(url="http://localhost/v1"),
    )

    assert len(batch.items) == 2
    assert batch.summary.scored_item_count == 2
    assert batch.summary.duration_ms is not None
    assert batch.duration_ms >= 0


@patch("openjury.jury_engine.fetch_agent_response")
@patch("openjury.jury_engine.Juror")
def test_all_jurors_failed_classified_as_juror_stage(
    mock_juror_class, mock_fetch, sample_jury_config
) -> None:
    mock_fetch.return_value = _fetch_result("ok")
    mock_juror = MagicMock()
    mock_juror.name = "Juror A"
    mock_juror.config.weight = 1.0
    mock_juror.evaluate.side_effect = OpenJuryEvaluationError(
        "all failed",
        code=EvaluationErrorCode.ALL_JURORS_FAILED,
    )
    mock_juror_class.side_effect = [mock_juror, mock_juror]

    results = OpenJury(sample_jury_config).evaluate_items(
        [EvaluationItem(prompt="Q")],
        AgentEndpoint(url="http://localhost/v1"),
    )

    assert results[0].status == EvalItemStatus.ALL_JURORS_FAILED
    assert results[0].error_stage == "juror"
    assert results[0].error_code == EvaluationErrorCode.ALL_JURORS_FAILED


@patch("openjury.jury_engine.fetch_agent_response")
@patch("openjury.jury_engine.Juror")
def test_score_batch_still_fail_fast(
    mock_juror_class, mock_fetch, sample_jury_config
) -> None:
    mock_fetch.side_effect = EndpointFetchError("boom")
    mock_juror_class.return_value = MagicMock(name="Juror A")
    jury = OpenJury(sample_jury_config)

    with pytest.raises(OpenJuryEvaluationError):
        jury.score_batch(
            ["Q1"],
            AgentEndpoint(url="http://localhost/v1"),
        )
