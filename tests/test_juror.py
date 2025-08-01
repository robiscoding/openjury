from unittest.mock import Mock, patch

import pytest

from openjury import Juror, ResponseCandidate


@patch("openjury.juror.ChatOpenAI")
class TestJurorIntegration:
    def test_juror_initialization(self, mock_llm_class, sample_jurors):
        mock_llm = Mock()
        mock_llm_class.return_value = mock_llm

        juror_config = sample_jurors[0]
        juror = Juror(juror_config)

        assert juror.name == "Expert Juror"
        assert juror.config.model_name == "gpt-3.5-turbo"
        mock_llm_class.assert_called_once()

    def test_juror_evaluation_success(
        self,
        mock_llm_class,
        sample_jurors,
        sample_criteria,
        sample_responses,
        sample_prompt,
    ):
        mock_llm = Mock()
        mock_response = Mock()
        mock_response.content = """
        ```json
        {
          "evaluations": [
            {
              "response_id": "response_1",
              "scores": {
                "FACTUALITY": {"score": 4, "explanation": "Good factuality"},
                "CLARITY": {"score": 5, "explanation": "Very clear"}
              }
            },
            {
              "response_id": "response_2", 
              "scores": {
                "FACTUALITY": {"score": 3, "explanation": "Fair factuality"},
                "CLARITY": {"score": 4, "explanation": "Mostly clear"}
              }
            }
          ]
        }
        ```
        """
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        juror = Juror(sample_jurors[0])
        scores, explanations = juror.evaluate(
            prompt=sample_prompt, responses=sample_responses, criteria=sample_criteria
        )

        assert "response_1" in scores
        assert "response_2" in scores
        assert scores["response_1"]["FACTUALITY"] == 4.0
        assert scores["response_1"]["CLARITY"] == 5.0
        assert explanations["response_1"]["FACTUALITY"] == "Good factuality"

    def test_juror_evaluation_robust_parsing(
        self,
        mock_llm_class,
        sample_jurors,
        sample_criteria,
        sample_responses,
        sample_prompt,
    ):
        mock_llm = Mock()
        mock_response = Mock()
        mock_response.content = """
        ```json
        {
          "evaluations": [
            {
              "response_id": "response_1",
              "scores": {
                "VotingCriteria.FACTUALITY": {"score": 4, "explanation": "Good factuality"},
                "VotingCriteria.CLARITY": {"score": 5, "explanation": "Very clear"}
              }
            },
            {
              "response_id": "response_2", 
              "scores": {
                "VotingCriteria.FACTUALITY": {"score": 3, "explanation": "Fair factuality"},
                "VotingCriteria.CLARITY": {"score": 4, "explanation": "Mostly clear"}
              }
            }
          ]
        }
        ```
        """
        mock_llm.invoke.return_value = mock_response
        mock_llm_class.return_value = mock_llm

        juror = Juror(sample_jurors[0])
        scores, explanations = juror.evaluate(
            prompt=sample_prompt, responses=sample_responses, criteria=sample_criteria
        )

        assert "response_1" in scores
        assert "response_2" in scores
        assert scores["response_1"]["FACTUALITY"] == 4.0
        assert scores["response_1"]["CLARITY"] == 5.0
        assert explanations["response_1"]["FACTUALITY"] == "Good factuality"

        mock_response.content = """
        ```json
        {
          "evaluations": [
            {
              "response_id": "response_1",
              "scores": {
                "FACTUALITY": {"score": 3, "explanation": "Plain format factuality"},
                "CLARITY": {"score": 4, "explanation": "Plain format clarity"}
              }
            }
          ]
        }
        ```
        """
        mock_llm.invoke.return_value = mock_response

        scores2, explanations2 = juror.evaluate(
            prompt=sample_prompt,
            responses=[ResponseCandidate(id="response_1", content="response")],
            criteria=sample_criteria,
        )

        assert scores2["response_1"]["FACTUALITY"] == 3.0
        assert scores2["response_1"]["CLARITY"] == 4.0
        assert explanations2["response_1"]["FACTUALITY"] == "Plain format factuality"
