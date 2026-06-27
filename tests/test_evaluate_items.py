"""Tests for evaluate_items batch orchestration."""

from unittest.mock import MagicMock, patch

import pytest

from openjury import AgentResponse, OpenJury
from openjury.endpoint_fetcher import AgentEndpoint, EndpointFetchError
from openjury.errors import OpenJuryEvaluationError
from openjury.execution import (
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
    assert results[1].error is not None


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
