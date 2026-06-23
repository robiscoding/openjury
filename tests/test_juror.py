from unittest.mock import Mock, patch

import pytest

from openjury import AgentResponse, Juror
from openjury.scoring import JurorScore


@patch("openjury.juror.ChatOpenAI")
class TestJurorIntegration:
    def test_juror_initialization(self, mock_llm_class, sample_jurors):
        mock_llm_class.return_value = Mock()
        juror = Juror(sample_jurors[0])
        assert juror.name == "Expert Juror"
        assert juror.config.model_name == "gpt-3.5-turbo"
        mock_llm_class.assert_called_once()

    def test_juror_evaluate_returns_juror_score(
        self,
        mock_llm_class,
        sample_jurors,
        sample_criteria,
        sample_response,
        sample_prompt,
    ):
        mock_llm = Mock()
        mock_llm.invoke.return_value = Mock(
            content='{"scores": {"factuality": {"score": 4, "explanation": "Good facts"}, "clarity": {"score": 5, "explanation": "Very clear"}}}'
        )
        mock_llm_class.return_value = mock_llm

        juror = Juror(sample_jurors[0])
        result = juror.evaluate(
            prompt=sample_prompt,
            response=sample_response,
            criteria=sample_criteria,
        )

        assert isinstance(result, JurorScore)
        assert result.juror_name == "Expert Juror"
        assert result.criterion_scores["factuality"] == 4.0
        assert result.criterion_scores["clarity"] == 5.0
        assert result.criterion_explanations["factuality"] == "Good facts"

    def test_juror_evaluate_with_rubric_criteria(
        self, mock_llm_class, sample_jurors, sample_prompt
    ):
        from openjury.config import CriterionConfig

        criteria_with_rubric = [
            CriterionConfig(
                name="helpfulness",
                description="Is it helpful?",
                weight=1.0,
                rubric={
                    "1": "Not helpful at all",
                    "3": "Somewhat helpful",
                    "5": "Extremely helpful",
                },
            )
        ]
        mock_llm = Mock()
        mock_llm.invoke.return_value = Mock(
            content='{"scores": {"helpfulness": {"score": 5, "explanation": "Very helpful"}}}'
        )
        mock_llm_class.return_value = mock_llm

        juror = Juror(sample_jurors[0])
        result = juror.evaluate(
            prompt=sample_prompt,
            response=AgentResponse(content="Helpful response", id="r1"),
            criteria=criteria_with_rubric,
        )

        assert isinstance(result, JurorScore)
        assert result.criterion_scores["helpfulness"] == 5.0

    def test_juror_evaluate_fallback_parse(
        self, mock_llm_class, sample_jurors, sample_criteria, sample_prompt
    ):
        mock_llm = Mock()
        # Non-JSON response — fallback parser should fill scores
        mock_llm.invoke.return_value = Mock(content="factuality: 3\nclarity: 4\n")
        mock_llm_class.return_value = mock_llm

        juror = Juror(sample_jurors[0])
        result = juror.evaluate(
            prompt=sample_prompt,
            response=AgentResponse(content="Some response", id="r1"),
            criteria=sample_criteria,
        )

        assert isinstance(result, JurorScore)
        # Fallback should produce scores for all criteria
        assert "factuality" in result.criterion_scores
        assert "clarity" in result.criterion_scores

    def test_juror_evaluate_missing_criteria_raises(
        self, mock_llm_class, sample_jurors, sample_criteria, sample_prompt
    ):
        from openjury.juror import JurorException

        mock_llm = Mock()
        # Only returns one criterion, missing the other
        mock_llm.invoke.return_value = Mock(
            content='{"scores": {"factuality": {"score": 4, "explanation": "ok"}}}'
        )
        mock_llm_class.return_value = mock_llm

        juror = Juror(sample_jurors[0])
        with pytest.raises(JurorException):
            juror.evaluate(
                prompt=sample_prompt,
                response=AgentResponse(content="Response", id="r1"),
                criteria=sample_criteria,
                max_retries=1,
            )
