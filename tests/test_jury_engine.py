from unittest.mock import Mock, patch

import pytest

from openjury import OpenJury, ResponseCandidate, Verdict


@patch("openjury.jury_engine.Juror")
class TestOpenJuryIntegration:
    def test_openjury_initialization(self, mock_juror_class, sample_jury_config):
        mock_juror = Mock()
        mock_juror.name = "Test Juror"
        mock_juror_class.return_value = mock_juror

        jury = OpenJury(sample_jury_config)

        assert len(jury.jurors) == 2
        assert jury.config.name == "Test Jury"

    def test_get_summary(self, mock_juror_class, sample_jury_config):
        mock_juror = Mock()
        mock_juror.name = "Test Juror"
        mock_juror.config.model_name = "gpt-3.5-turbo"
        mock_juror.config.weight = 1.0
        mock_juror_class.return_value = mock_juror

        jury = OpenJury(sample_jury_config)
        summary = jury.get_summary()

        assert summary["name"] == "Test Jury"
        assert summary["num_jurors"] == 2
        assert summary["num_criteria"] == 2
        assert summary["voting_method"] == "weighted"


@patch("openjury.jury_engine.Juror")
class TestOpenJuryEvaluation:
    def test_evaluate_with_response_candidates(
        self,
        mock_juror_class,
        sample_jury_config,
        sample_response_candidates,
        sample_prompt,
    ):
        mock_juror = Mock()
        mock_juror.name = "Test Juror"
        mock_juror.config.weight = 1.0
        mock_juror.evaluate.return_value = (
            {"response_1": {"factuality": 5.0, "clarity": 4.0}},
            {"response_1": {"factuality": "Good", "clarity": "Clear"}},
        )
        mock_juror_class.return_value = mock_juror

        jury = OpenJury(sample_jury_config)
        verdict = jury.evaluate(
            prompt=sample_prompt, responses=sample_response_candidates
        )

        assert isinstance(verdict, Verdict)
        assert verdict.final_verdict.winner == "response_1"
        assert len(verdict.responses) == 2
        assert "response_1" in verdict.responses
        assert "response_2" in verdict.responses

    def test_evaluate_returns_verdict(self, mock_juror_class, sample_jury_config):
        mock_juror = Mock()
        mock_juror.name = "TestJuror"
        mock_juror.config.weight = 1.0
        mock_juror.evaluate.return_value = (
            {"response_1": {"factuality": 5.0, "clarity": 4.0}},
            {"response_1": {"factuality": "Good", "clarity": "Clear"}},
        )
        mock_juror_class.return_value = mock_juror

        jury = OpenJury(sample_jury_config)

        result = jury.evaluate(
            prompt="Test prompt",
            responses=[ResponseCandidate(id="response_1", content="First response")],
        )

        assert isinstance(result, Verdict)
        assert result.jury_name == "Test Jury"
        assert result.final_verdict.winner == "response_1"

    def test_evaluate_with_response_ids(self, mock_juror_class, sample_jury_config):
        mock_juror = Mock()
        mock_juror.name = "TestJuror"
        mock_juror.config.weight = 1.0
        mock_juror.evaluate.return_value = (
            {"custom_1": {"factuality": 5.0}, "custom_2": {"factuality": 3.0}},
            {"custom_1": {"factuality": "Good"}, "custom_2": {"factuality": "Poor"}},
        )
        mock_juror_class.return_value = mock_juror

        jury = OpenJury(sample_jury_config)

        result = jury.evaluate(
            prompt="Test prompt",
            responses=[
                ResponseCandidate(id="custom_1", content="First response"),
                ResponseCandidate(id="custom_2", content="Second response"),
            ],
            response_ids=["custom_1", "custom_2"],
        )

        assert isinstance(result, Verdict)
        assert "custom_1" in result.responses
        assert "custom_2" in result.responses

    def test_evaluate_error_handling(self, mock_juror_class, sample_jury_config):
        jury = OpenJury(sample_jury_config)

        with pytest.raises(Exception):
            jury.evaluate(prompt="Test", responses=[])

        with pytest.raises(Exception):
            jury.evaluate(
                prompt="Test",
                responses=["response1", "response2"],
                response_ids=["id1"],
            )
