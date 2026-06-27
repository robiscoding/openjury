from unittest.mock import MagicMock, Mock, patch

import pytest

from openjury import AgentResponse, Juror
from openjury.scoring import JurorScore


def _mock_openai_response(content: str) -> MagicMock:
    """Build a mock openai ChatCompletion response with the given message content."""
    mock_choice = MagicMock()
    mock_choice.message.content = content
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    return mock_resp


@patch("openjury.juror.OpenAI")
class TestJurorIntegration:
    def test_juror_initialization(
        self, mock_openai_class, sample_jurors, sample_llm_provider
    ):
        mock_openai_class.return_value = MagicMock()
        juror = Juror(sample_jurors[0], jury_llm_provider=sample_llm_provider)
        assert juror.name == "Expert Juror"
        assert juror.llm_config.model_name == "gpt-3.5-turbo"
        mock_openai_class.assert_called_once()

    def test_juror_evaluate_returns_juror_score(
        self,
        mock_openai_class,
        sample_jurors,
        sample_llm_provider,
        sample_criteria,
        sample_response,
        sample_prompt,
    ):
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response(
            '{"scores": {"factuality": {"score": 4, "explanation": "Good facts"}, '
            '"clarity": {"score": 5, "explanation": "Very clear"}}}'
        )
        mock_openai_class.return_value = mock_client

        juror = Juror(sample_jurors[0], jury_llm_provider=sample_llm_provider)
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
        self, mock_openai_class, sample_jurors, sample_llm_provider, sample_prompt
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
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response(
            '{"scores": {"helpfulness": {"score": 5, "explanation": "Very helpful"}}}'
        )
        mock_openai_class.return_value = mock_client

        juror = Juror(sample_jurors[0], jury_llm_provider=sample_llm_provider)
        result = juror.evaluate(
            prompt=sample_prompt,
            response=AgentResponse(content="Helpful response", id="r1"),
            criteria=criteria_with_rubric,
        )

        assert isinstance(result, JurorScore)
        assert result.criterion_scores["helpfulness"] == 5.0

    def test_juror_evaluate_fallback_parse_raises(
        self,
        mock_openai_class,
        sample_jurors,
        sample_llm_provider,
        sample_criteria,
        sample_prompt,
    ):
        from openjury.errors import JurorErrorCode
        from openjury.juror import JurorException

        mock_client = MagicMock()
        # Non-JSON response — should raise rather than silently assign garbage scores
        mock_client.chat.completions.create.return_value = _mock_openai_response(
            "factuality: 3\nclarity: 4\n"
        )
        mock_openai_class.return_value = mock_client

        juror = Juror(sample_jurors[0], jury_llm_provider=sample_llm_provider)
        with pytest.raises(JurorException) as exc_info:
            juror.evaluate(
                prompt=sample_prompt,
                response=AgentResponse(content="Some response", id="r1"),
                criteria=sample_criteria,
                max_retries=1,
            )
        assert exc_info.value.code == JurorErrorCode.JUROR_PARSE_ERROR

    def test_juror_evaluate_missing_criteria_raises(
        self,
        mock_openai_class,
        sample_jurors,
        sample_llm_provider,
        sample_criteria,
        sample_prompt,
    ):
        from openjury.juror import JurorException

        mock_client = MagicMock()
        # Only returns one criterion, missing the other
        mock_client.chat.completions.create.return_value = _mock_openai_response(
            '{"scores": {"factuality": {"score": 4, "explanation": "ok"}}}'
        )
        mock_openai_class.return_value = mock_client

        juror = Juror(sample_jurors[0], jury_llm_provider=sample_llm_provider)
        with pytest.raises(JurorException):
            juror.evaluate(
                prompt=sample_prompt,
                response=AgentResponse(content="Response", id="r1"),
                criteria=sample_criteria,
                max_retries=1,
            )
