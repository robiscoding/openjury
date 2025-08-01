import pytest

from openjury import JuryConfig, ResponseCandidate, VotingMethod


class TestResponseCandidate:
    def test_response_candidate_creation(self):
        response = ResponseCandidate(
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
        response = ResponseCandidate(
            id="test_response",
            content="This is a test response",
        )
        assert str(response) == "This is a test response"

    def test_response_candidate_display_name(self):
        response_with_alias = ResponseCandidate(
            id="test_response",
            alias="Test Response",
            content="This is a test response",
        )
        assert response_with_alias.get_display_name() == "Test Response"

        response_without_alias = ResponseCandidate(
            id="test_response",
            content="This is a test response",
        )
        assert response_without_alias.get_display_name() == "test_response"


class TestJuryConfig:
    def test_jury_config_creation(self, sample_jury_config):
        assert sample_jury_config.name == "Test Jury"
        assert len(sample_jury_config.criteria) == 2
        assert len(sample_jury_config.jurors) == 2
        assert sample_jury_config.voting_method == VotingMethod.WEIGHTED

    def test_jury_config_weights(self, sample_jury_config):
        total_juror_weight = sample_jury_config.get_total_juror_weight()
        total_criteria_weight = sample_jury_config.get_total_criteria_weight()

        assert total_juror_weight == 3.0
        assert total_criteria_weight == 3.0

    def test_jury_config_serialization(self, sample_jury_config):
        config_dict = sample_jury_config.model_dump()
        assert config_dict["name"] == "Test Jury"
        assert config_dict["voting_method"] == "weighted"

        new_config = JuryConfig.from_dict(config_dict)
        assert new_config.name == sample_jury_config.name
