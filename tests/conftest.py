import os
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from openjury import (
    CriterionConfig,
    JurorConfig,
    JuryConfig,
    ResponseCandidate,
    VotingCriteria,
    VotingMethod,
)


@pytest.fixture(autouse=True)
def setup_test_env():
    os.environ["OPENROUTER_API_KEY"] = "test-api-key"
    os.environ["LLM_PROVIDER"] = "openrouter"
    yield
    # Cleanup is not needed since tests run in isolation


@pytest.fixture
def sample_criteria():
    return [
        CriterionConfig(
            name=VotingCriteria.FACTUALITY,
            description="How accurate is the response?",
            weight=2.0,
            max_score=5,
        ),
        CriterionConfig(
            name=VotingCriteria.CLARITY,
            description="How clear and understandable is the response?",
            weight=1.0,
            max_score=5,
        ),
    ]


@pytest.fixture
def sample_jurors():
    return [
        JurorConfig(name="Expert Juror", model_name="gpt-3.5-turbo", weight=2.0),
        JurorConfig(name="General Juror", model_name="gpt-3.5-turbo", weight=1.0),
    ]


@pytest.fixture
def sample_jury_config(sample_criteria, sample_jurors):
    return JuryConfig(
        name="Test Jury",
        description="A test jury for unit tests",
        criteria=sample_criteria,
        jurors=sample_jurors,
        voting_method=VotingMethod.WEIGHTED,
    )


@pytest.fixture
def sample_responses():
    return [
        ResponseCandidate(
            id="response_1",
            content="This is the first response to the prompt.",
        ),
        ResponseCandidate(
            id="response_2",
            content="This is the second response, which might be different.",
        ),
    ]


@pytest.fixture
def sample_response_candidates():
    return [
        ResponseCandidate(
            id="response_1",
            alias="gpt-4o-response",
            content="This is the first response to the prompt.",
            model_name="gpt-4o",
        ),
        ResponseCandidate(
            id="response_2",
            alias="claude-3.5-response",
            content="This is the second response, which might be different.",
            model_name="claude-3.5-sonnet",
        ),
    ]


@pytest.fixture
def sample_prompt():
    return "Write a helpful response to demonstrate the system."


@pytest.fixture
def mock_juror_evaluations():
    """Factory fixture for creating mock juror evaluations."""

    def _create_evaluations(scores_data):
        from openjury import JurorEvaluation

        evaluations = []
        for juror_name, response_scores in scores_data.items():
            evaluations.append(
                JurorEvaluation(
                    juror_name=juror_name,
                    response_scores=response_scores,
                    juror_weight=1.0,
                )
            )
        return evaluations

    return _create_evaluations


@pytest.fixture
def mock_voting_result():
    """Factory fixture for creating mock voting results."""

    def _create_result(winner, method, **kwargs):
        from openjury.voting import VotingResult

        return VotingResult(winner=winner, method=method, **kwargs)

    return _create_result
