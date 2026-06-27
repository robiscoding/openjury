"""Integration tests for agent evaluation flow (mocked jurors and endpoints)."""

from unittest.mock import MagicMock, patch

import pytest

from openjury.config import (
    AgentResponse,
    CriterionConfig,
    JurorConfig,
    JurorProvider,
    JuryConfig,
    LLMProviderConfig,
)
from openjury.endpoint_fetcher import AgentEndpoint
from openjury.execution import FetchMetadata, FetchResult
from openjury.output_format import AgentEvalResult
from openjury.scoring import ConsistencyResult, JurorScore


def _make_config(num_trials=1, custom_fn=None):
    return JuryConfig(
        name="Agent Test Jury",
        llm_provider=LLMProviderConfig(
            provider=JurorProvider.OPENAI_COMPATIBLE,
            model_name="gpt-4o-mini",
            api_key="test-api-key",
        ),
        criteria=[
            CriterionConfig(
                name="helpfulness",
                description="Is the response helpful?",
                weight=1.0,
                rubric={
                    "1": "Not helpful",
                    "3": "Somewhat helpful",
                    "5": "Very helpful",
                },
            ),
            CriterionConfig(
                name="accuracy",
                description="Is the response accurate?",
                weight=2.0,
            ),
        ],
        jurors=[
            JurorConfig(name="Juror A", weight=1.0),
            JurorConfig(name="Juror B", weight=1.0),
        ],
        score_scale=5,
        num_trials=num_trials,
        custom_scoring_function=custom_fn,
    )


def _make_endpoint():
    return AgentEndpoint(
        url="http://localhost:8080/v1/chat/completions",
        alias="test-agent",
    )


def _make_juror_score(name, helpfulness, accuracy, weight=1.0):
    return JurorScore(
        juror_name=name,
        juror_weight=weight,
        criterion_scores={"helpfulness": helpfulness, "accuracy": accuracy},
        criterion_explanations={
            "helpfulness": f"{name}: helpful comment",
            "accuracy": f"{name}: accuracy comment",
        },
    )


def _fetch_result(response: AgentResponse) -> FetchResult:
    return FetchResult(response=response, metadata=FetchMetadata())


@patch("openjury.jury_engine.fetch_agent_response")
@patch("openjury.jury_engine.Juror")
class TestScoreResponse:
    def test_single_trial_returns_agent_eval_result(self, mock_juror_class, mock_fetch):
        from openjury.jury_engine import OpenJury

        mock_response = AgentResponse(content="The answer is 42.", id="r1")
        mock_fetch.return_value = _fetch_result(mock_response)

        mock_juror_a = MagicMock()
        mock_juror_a.name = "Juror A"
        mock_juror_a.config.weight = 1.0
        mock_juror_a.evaluate.return_value = _make_juror_score("Juror A", 4.0, 5.0)

        mock_juror_b = MagicMock()
        mock_juror_b.name = "Juror B"
        mock_juror_b.config.weight = 1.0
        mock_juror_b.evaluate.return_value = _make_juror_score("Juror B", 3.0, 4.0)

        mock_juror_class.side_effect = [mock_juror_a, mock_juror_b]

        jury = OpenJury(_make_config())
        result = jury.evaluate(
            prompt="What is the answer?",
            endpoint=_make_endpoint(),
        )

        assert isinstance(result, AgentEvalResult)
        assert result.jury_name == "Agent Test Jury"
        assert result.score_scale == 5
        assert 0 < result.composite_score <= 5
        assert 0 <= result.normalized_composite_score <= 1
        assert result.consistency_result is None
        assert len(result.trial_results) == 1

    def test_criteria_evaluations_populated(self, mock_juror_class, mock_fetch):
        from openjury.jury_engine import OpenJury

        mock_response = AgentResponse(content="Response text", id="r1")
        mock_fetch.return_value = _fetch_result(mock_response)

        mock_juror_a = MagicMock()
        mock_juror_a.name = "Juror A"
        mock_juror_a.config.weight = 1.0
        mock_juror_a.evaluate.return_value = _make_juror_score("Juror A", 4.0, 4.0)

        mock_juror_b = MagicMock()
        mock_juror_b.name = "Juror B"
        mock_juror_b.config.weight = 1.0
        mock_juror_b.evaluate.return_value = _make_juror_score("Juror B", 4.0, 4.0)

        mock_juror_class.side_effect = [mock_juror_a, mock_juror_b]

        jury = OpenJury(_make_config())
        result = jury.evaluate(prompt="Q?", endpoint=_make_endpoint())

        assert "helpfulness" in result.criteria_evaluations
        assert "accuracy" in result.criteria_evaluations
        ce_help = result.criteria_evaluations["helpfulness"]
        assert ce_help.weighted_mean_score == 4.0
        assert ce_help.juror_agreement == 1.0

    def test_consistency_audit_when_num_trials_gt_1(self, mock_juror_class, mock_fetch):
        from openjury.jury_engine import OpenJury

        mock_response = AgentResponse(content="Response", id="r1")
        mock_fetch.return_value = _fetch_result(mock_response)

        def make_mock_juror(name):
            m = MagicMock()
            m.name = name
            m.config.weight = 1.0
            m.evaluate.return_value = _make_juror_score(name, 4.0, 4.0)
            return m

        mock_juror_class.side_effect = [
            make_mock_juror("Juror A"),
            make_mock_juror("Juror B"),
        ]

        jury = OpenJury(_make_config(num_trials=3))
        result = jury.evaluate(prompt="Q?", endpoint=_make_endpoint())

        assert result.consistency_result is not None
        assert isinstance(result.consistency_result, ConsistencyResult)
        assert result.consistency_result.num_trials == 3
        assert len(result.trial_results) == 3

    def test_no_consistency_result_when_single_trial(
        self, mock_juror_class, mock_fetch
    ):
        from openjury.jury_engine import OpenJury

        mock_response = AgentResponse(content="Response", id="r1")
        mock_fetch.return_value = _fetch_result(mock_response)

        def make_mock_juror(name):
            m = MagicMock()
            m.name = name
            m.config.weight = 1.0
            m.evaluate.return_value = _make_juror_score(name, 3.0, 3.0)
            return m

        mock_juror_class.side_effect = [
            make_mock_juror("Juror A"),
            make_mock_juror("Juror B"),
        ]

        jury = OpenJury(_make_config(num_trials=1))
        result = jury.evaluate(prompt="Q?", endpoint=_make_endpoint())

        assert result.consistency_result is None

    def test_normalized_composite_score_in_range(self, mock_juror_class, mock_fetch):
        from openjury.jury_engine import OpenJury

        mock_response = AgentResponse(content="Resp", id="r1")
        mock_fetch.return_value = _fetch_result(mock_response)

        def make_mock_juror(name):
            m = MagicMock()
            m.name = name
            m.config.weight = 1.0
            m.evaluate.return_value = _make_juror_score(name, 5.0, 5.0)
            return m

        mock_juror_class.side_effect = [
            make_mock_juror("Juror A"),
            make_mock_juror("Juror B"),
        ]

        jury = OpenJury(_make_config())
        result = jury.evaluate(prompt="Q?", endpoint=_make_endpoint())

        assert (
            result.normalized_composite_score
            == result.composite_score / result.score_scale
        )
        assert 0.0 <= result.normalized_composite_score <= 1.0

    def test_no_custom_score_by_default(self, mock_juror_class, mock_fetch):
        from openjury.jury_engine import OpenJury

        mock_response = AgentResponse(content="Response", id="r1")
        mock_fetch.return_value = _fetch_result(mock_response)

        def make_mock_juror(name):
            m = MagicMock()
            m.name = name
            m.config.weight = 1.0
            m.evaluate.return_value = _make_juror_score(name, 3.0, 3.0)
            return m

        mock_juror_class.side_effect = [
            make_mock_juror("Juror A"),
            make_mock_juror("Juror B"),
        ]

        jury = OpenJury(_make_config())
        result = jury.evaluate(prompt="Q?", endpoint=_make_endpoint())
        assert result.scored_metrics.custom is None
