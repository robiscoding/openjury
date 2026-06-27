import pytest

from openjury import AgentResponse, JuryConfig
from openjury.config import CriterionConfig, VotingCriteria


class TestAgentResponse:
    def test_response_candidate_creation(self):
        response = AgentResponse(
            id="test_response",
            alias="Test Response",
            content="This is a test response",
            model_name="gpt-4",
        )
        assert response.id == "test_response"
        assert response.alias == "Test Response"
        assert response.content == "This is a test response"
        assert response.model_name == "gpt-4"

    def test_response_candidate_str_method(self):
        response = AgentResponse(id="test_response", content="This is a test response")
        assert str(response) == "This is a test response"

    def test_response_candidate_display_name(self):
        with_alias = AgentResponse(
            id="test_response", alias="Test Response", content="body"
        )
        assert with_alias.get_display_name() == "Test Response"

        without_alias = AgentResponse(id="test_response", content="body")
        assert without_alias.get_display_name() == "test_response"


class TestCriterionConfig:
    def test_freeform_name(self):
        c = CriterionConfig(
            name="policy_adherence", description="Does it follow policy?", weight=2.0
        )
        assert c.name == "policy_adherence"

    def test_enum_name_coerced_to_str(self):
        c = CriterionConfig(name=VotingCriteria.FACTUALITY, description="d", weight=1.0)
        assert c.name == "factuality"
        assert isinstance(c.name, str)

    def test_enum_name_string_coerced(self):
        c = CriterionConfig(name="FACTUALITY", description="d", weight=1.0)
        assert c.name == "factuality"

    def test_rubric_stored(self):
        rubric = {"1": "Bad", "3": "Ok", "5": "Great"}
        c = CriterionConfig(name="clarity", description="d", weight=1.0, rubric=rubric)
        assert c.rubric == rubric

    def test_rubric_optional(self):
        c = CriterionConfig(name="clarity", description="d", weight=1.0)
        assert c.rubric is None


class TestJuryConfig:
    def test_jury_config_creation(self, sample_jury_config):
        assert sample_jury_config.name == "Test Jury"
        assert len(sample_jury_config.criteria) == 2
        assert len(sample_jury_config.jurors) == 2
        assert sample_jury_config.score_scale == 5

    def test_jury_config_weights(self, sample_jury_config):
        assert sample_jury_config.get_total_juror_weight() == 3.0
        assert sample_jury_config.get_total_criteria_weight() == 3.0

    def test_jury_config_serialization(self, sample_jury_config):
        config_dict = sample_jury_config.model_dump()
        assert config_dict["name"] == "Test Jury"
        assert "score_scale" in config_dict

        new_config = JuryConfig.from_dict(config_dict)
        assert new_config.name == sample_jury_config.name

    def test_default_num_trials(self, sample_jury_config):
        assert sample_jury_config.num_trials == 1

    def test_score_scale_bounds(self):
        config = JuryConfig(
            name="X",
            criteria=[CriterionConfig(name="c", description="d", weight=1.0)],
            jurors=[],
            score_scale=10,
        )
        assert config.score_scale == 10
