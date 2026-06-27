from unittest.mock import MagicMock, patch

import pytest

from openjury import AgentResponse, OpenJury
from openjury.config import (
    CriterionConfig,
    JurorConfig,
    JurorProvider,
    JuryConfig,
    LLMProviderConfig,
)
from openjury.endpoint_fetcher import AgentEndpoint
from openjury.execution import FetchMetadata, FetchResult
from openjury.output_format import AgentEvalResult
from openjury.scoring import JurorScore


def _fetch_result(response: AgentResponse) -> FetchResult:
    return FetchResult(response=response, metadata=FetchMetadata())


def _score(juror_name, weight=1.0, helpfulness=4.0, accuracy=4.0):
    return JurorScore(
        juror_name=juror_name,
        juror_weight=weight,
        criterion_scores={"helpfulness": helpfulness, "accuracy": accuracy},
        criterion_explanations={"helpfulness": "ok", "accuracy": "ok"},
    )


@patch("openjury.jury_engine.Juror")
class TestOpenJuryInit:
    def test_initialization(self, mock_juror_class, sample_jury_config):
        mock_juror_class.return_value = MagicMock(name="Juror A")
        jury = OpenJury(sample_jury_config)
        assert len(jury.jurors) == 2
        assert jury.config.name == "Test Jury"

    def test_get_summary(self, mock_juror_class, sample_jury_config):
        m = MagicMock()
        m.name = "Juror A"
        m.config.model_name = "gpt-3.5-turbo"
        m.config.weight = 1.0
        mock_juror_class.return_value = m

        jury = OpenJury(sample_jury_config)
        summary = jury.get_summary()

        assert summary["name"] == "Test Jury"
        assert summary["num_jurors"] == 2
        assert summary["num_criteria"] == 2
        assert summary["score_scale"] == 5


@patch("openjury.jury_engine.fetch_agent_response")
@patch("openjury.jury_engine.Juror")
class TestScoreResponse:
    def _setup_mocks(self, mock_juror_class, scores=(4.0, 4.0)):
        mock_response = AgentResponse(content="Agent answer.", id="r1")

        def make_juror(name):
            m = MagicMock()
            m.name = name
            m.config.weight = 1.0
            m.evaluate.return_value = _score(
                name, helpfulness=scores[0], accuracy=scores[1]
            )
            return m

        mock_juror_class.side_effect = [make_juror("A"), make_juror("B")]
        return mock_response

    def test_returns_agent_eval_result(
        self, mock_juror_class, mock_fetch, sample_jury_config
    ):
        mock_resp = self._setup_mocks(mock_juror_class)
        mock_fetch.return_value = _fetch_result(mock_resp)

        jury = OpenJury(sample_jury_config)
        endpoint = AgentEndpoint(url="http://localhost/v1", alias="test")
        result = jury.evaluate(prompt="Q?", endpoint=endpoint)

        assert isinstance(result, AgentEvalResult)
        assert result.jury_name == "Test Jury"

    def test_score_response_is_evaluate_alias(
        self, mock_juror_class, mock_fetch, sample_jury_config
    ):
        mock_resp = self._setup_mocks(mock_juror_class)
        mock_fetch.return_value = _fetch_result(mock_resp)

        jury = OpenJury(sample_jury_config)
        endpoint = AgentEndpoint(url="http://localhost/v1", alias="test")
        result = jury.score_response(prompt="Q?", endpoint=endpoint)

        assert isinstance(result, AgentEvalResult)
        assert result.jury_name == "Test Jury"
        mock_fetch.assert_called_once()

    def test_consistency_result_none_for_single_trial(
        self, mock_juror_class, mock_fetch, sample_jury_config
    ):
        mock_resp = self._setup_mocks(mock_juror_class)
        mock_fetch.return_value = _fetch_result(mock_resp)

        jury = OpenJury(sample_jury_config)
        result = jury.evaluate(
            prompt="Q?",
            endpoint=AgentEndpoint(url="http://localhost/v1"),
        )
        assert result.consistency_result is None

    def test_consistency_result_present_for_multiple_trials(
        self, mock_juror_class, mock_fetch
    ):
        config = JuryConfig(
            name="Jury",
            llm_provider=LLMProviderConfig(
                provider=JurorProvider.OPENAI_COMPATIBLE,
                model_name="m",
                api_key="test-api-key",
            ),
            criteria=[
                CriterionConfig(name="helpfulness", description="H", weight=1.0),
                CriterionConfig(name="accuracy", description="A", weight=2.0),
            ],
            jurors=[
                JurorConfig(name="J1", weight=1.0),
            ],
            score_scale=5,
            num_trials=3,
        )

        mock_response = AgentResponse(content="Answer", id="r1")
        mock_fetch.return_value = _fetch_result(mock_response)

        mock_j = MagicMock()
        mock_j.name = "J1"
        mock_j.config.weight = 1.0
        mock_j.evaluate.return_value = _score("J1")
        mock_juror_class.return_value = mock_j

        jury = OpenJury(config)
        result = jury.evaluate(
            prompt="Q?",
            endpoint=AgentEndpoint(url="http://localhost/v1"),
        )

        assert result.consistency_result is not None
        assert result.consistency_result.num_trials == 3
        assert len(result.trial_results) == 3

    def test_no_response_raises(self, mock_juror_class, mock_fetch, sample_jury_config):
        from openjury.endpoint_fetcher import EndpointFetchError
        from openjury.errors import EndpointErrorCode

        mock_juror_class.return_value = MagicMock(name="J")
        mock_fetch.side_effect = EndpointFetchError(
            "Endpoint returned empty content",
            code=EndpointErrorCode.ENDPOINT_EMPTY_RESPONSE,
        )

        jury = OpenJury(sample_jury_config)
        with pytest.raises(EndpointFetchError):
            jury.evaluate(
                prompt="Q?",
                endpoint=AgentEndpoint(url="http://localhost/v1"),
            )


@patch("openjury.jury_engine.Juror")
class TestScoreExistingResponse:
    def test_scores_without_fetch(self, mock_juror_class, sample_jury_config):
        mock_j = MagicMock()
        mock_j.name = "Juror A"
        mock_j.config.weight = 1.0
        mock_j.evaluate.return_value = _score("Juror A")
        mock_juror_class.side_effect = [mock_j, MagicMock(name="Juror B")]

        jury = OpenJury(sample_jury_config)
        response = AgentResponse(content="pre-fetched answer")
        result = jury.score_existing_response("Q?", response, jurors_to_run=["Juror A"])

        assert isinstance(result, AgentEvalResult)
        assert result.jury_name == "Test Jury"
        assert len(result.juror_scores) == 1
        assert result.juror_failures == []

    def test_partial_juror_failure_surfaces_in_result(
        self, mock_juror_class, sample_jury_config
    ):
        ok = MagicMock()
        ok.name = "Juror A"
        ok.config.weight = 1.0
        ok.evaluate.return_value = _score("Juror A")

        bad = MagicMock()
        bad.name = "Juror B"
        bad.config.weight = 1.0
        bad.evaluate.side_effect = RuntimeError("provider down")

        mock_juror_class.side_effect = [ok, bad]

        jury = OpenJury(sample_jury_config)
        result = jury.score_existing_response("Q?", AgentResponse(content="answer"))

        assert isinstance(result, AgentEvalResult)
        assert len(result.juror_scores) == 1
        assert len(result.juror_failures) == 1

    def test_all_jurors_failed_raises(self, mock_juror_class, sample_jury_config):
        from openjury.errors import EvaluationErrorCode
        from openjury.jury_engine import OpenJuryEvaluationError

        fail_a = MagicMock()
        fail_a.name = "Juror A"
        fail_a.config.weight = 1.0
        fail_a.evaluate.side_effect = RuntimeError("down")

        fail_b = MagicMock()
        fail_b.name = "Juror B"
        fail_b.config.weight = 1.0
        fail_b.evaluate.side_effect = RuntimeError("down")

        mock_juror_class.side_effect = [fail_a, fail_b]
        jury = OpenJury(sample_jury_config)

        with pytest.raises(OpenJuryEvaluationError) as exc_info:
            jury.score_existing_response("Q?", AgentResponse(content="answer"))
        assert exc_info.value.code == EvaluationErrorCode.ALL_JURORS_FAILED
