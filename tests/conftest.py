import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from openjury.config import (
    AgentResponse,
    CriterionConfig,
    JurorConfig,
    JurorProvider,
    JuryConfig,
    LLMProviderConfig,
)


@pytest.fixture
def sample_criteria():
    return [
        CriterionConfig(
            name="factuality",
            description="How accurate is the response?",
            weight=2.0,
            rubric={
                "1": "Multiple factual errors",
                "3": "Mostly accurate with minor issues",
                "5": "Completely accurate",
            },
        ),
        CriterionConfig(
            name="clarity",
            description="How clear and understandable is the response?",
            weight=1.0,
        ),
    ]


@pytest.fixture
def sample_llm_provider():
    return LLMProviderConfig(
        provider=JurorProvider.OPENAI_COMPATIBLE,
        model_name="gpt-3.5-turbo",
        api_key="test-api-key",
    )


@pytest.fixture
def sample_jurors():
    return [
        JurorConfig(name="Expert Juror", weight=2.0),
        JurorConfig(name="General Juror", weight=1.0),
    ]


@pytest.fixture
def sample_jury_config(sample_criteria, sample_jurors, sample_llm_provider):
    return JuryConfig(
        name="Test Jury",
        description="A test jury for unit tests",
        llm_provider=sample_llm_provider,
        criteria=sample_criteria,
        jurors=sample_jurors,
        score_scale=5,
    )


@pytest.fixture
def sample_response():
    return AgentResponse(
        id="response_1",
        content="This is the agent response to the prompt.",
        model_name="gpt-4o",
    )


@pytest.fixture
def sample_prompt():
    return "Write a helpful response to demonstrate the system."
