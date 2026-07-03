import pytest
from pydantic import ValidationError

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

    def test_rubric_accepts_and_normalizes_inclusive_ranges(self):
        c = CriterionConfig(
            name="tone",
            description="d",
            rubric={" 1 - 2 ": "Poor", "3-4": "Acceptable", "5": "Excellent"},
        )
        assert c.rubric == {
            "1-2": "Poor",
            "3-4": "Acceptable",
            "5": "Excellent",
        }

    @pytest.mark.parametrize("key", ["1,2", "1.5-2.5", "one", "4-2", "1-2-3"])
    def test_rubric_rejects_invalid_range_syntax(self, key):
        with pytest.raises(ValueError, match="rubric"):
            CriterionConfig(
                name="tone",
                description="d",
                rubric={key: "Description"},
            )

    def test_rubric_rejects_empty_descriptions(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            CriterionConfig(
                name="tone",
                description="d",
                rubric={"1-5": "  "},
            )


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

    def test_range_rubric_must_cover_score_scale(self, sample_jury_config):
        sample_jury_config.criteria = [
            CriterionConfig(
                name="tone",
                description="d",
                rubric={"1-2": "Poor", "4-5": "Good"},
            )
        ]
        with pytest.raises(ValueError, match=r"missing \[3\]"):
            JuryConfig.model_validate(sample_jury_config.model_dump())

    def test_range_rubric_rejects_overlaps(self, sample_jury_config):
        sample_jury_config.criteria = [
            CriterionConfig(
                name="tone",
                description="d",
                rubric={"1-3": "Poor", "3-4": "Okay", "5": "Good"},
            )
        ]
        with pytest.raises(ValueError, match="overlap"):
            JuryConfig.model_validate(sample_jury_config.model_dump())

    def test_rubric_rejects_scores_outside_scale(self, sample_jury_config):
        sample_jury_config.criteria = [
            CriterionConfig(
                name="tone",
                description="d",
                rubric={"1": "Poor", "6": "Impossible"},
            )
        ]
        with pytest.raises(ValueError, match="outside"):
            JuryConfig.model_validate(sample_jury_config.model_dump())

    def test_sparse_exact_rubric_remains_supported(self, sample_jury_config):
        sample_jury_config.criteria = [
            CriterionConfig(
                name="tone",
                description="d",
                rubric={"1": "Poor", "3": "Okay", "5": "Good"},
            )
        ]
        config = JuryConfig.model_validate(sample_jury_config.model_dump())
        assert config.criteria[0].rubric == {"1": "Poor", "3": "Okay", "5": "Good"}

    def test_zero_based_range_rubric(self, sample_jury_config):
        sample_jury_config.score_min = 0
        sample_jury_config.criteria = [
            CriterionConfig(
                name="tone",
                description="d",
                rubric={"0-2": "Poor", "3-4": "Okay", "5": "Good"},
            )
        ]
        config = JuryConfig.model_validate(sample_jury_config.model_dump())
        assert config.score_min == 0

    def test_inline_dataset_references_assertion_policy(
        self, sample_criteria, sample_jurors, sample_llm_provider
    ):
        config = JuryConfig(
            name="Dataset jury",
            llm_provider=sample_llm_provider,
            criteria=sample_criteria,
            jurors=sample_jurors,
            assertions={
                "citation_contract": {
                    "checks": [
                        {
                            "name": "has citation",
                            "type": "contains",
                            "value": "https://",
                        }
                    ],
                    "assertion_threshold": 1.0,
                    "quality_threshold": 4.0,
                }
            },
            dataset=[
                {
                    "id": "case-1",
                    "input": "Answer with a source",
                    "ground_truth": "A sourced answer",
                    "assertion_ids": ["citation_contract"],
                }
            ],
        )

        assert config.dataset[0].input == "Answer with a source"
        assert config.assertions["citation_contract"].checks[0].name == "has citation"

    def test_dataset_rejects_unknown_assertion_id(
        self, sample_criteria, sample_jurors, sample_llm_provider
    ):
        with pytest.raises(ValidationError, match="unknown assertion_id"):
            JuryConfig(
                name="Dataset jury",
                llm_provider=sample_llm_provider,
                criteria=sample_criteria,
                jurors=sample_jurors,
                dataset=[
                    {
                        "id": "case-1",
                        "input": "Hello",
                        "assertion_ids": ["missing"],
                    }
                ],
            )

    def test_dataset_ids_must_be_unique(
        self, sample_criteria, sample_jurors, sample_llm_provider
    ):
        with pytest.raises(ValidationError, match="must be unique"):
            JuryConfig(
                name="Dataset jury",
                llm_provider=sample_llm_provider,
                criteria=sample_criteria,
                jurors=sample_jurors,
                dataset=[
                    {"id": "duplicate", "input": "First"},
                    {"id": "duplicate", "input": "Second"},
                ],
            )

    def test_dataset_item_accepts_legacy_singular_assertion_id(
        self, sample_criteria, sample_jurors, sample_llm_provider
    ):
        config = JuryConfig(
            name="Dataset jury",
            llm_provider=sample_llm_provider,
            criteria=sample_criteria,
            jurors=sample_jurors,
            assertions={
                "contract": {
                    "checks": [{"name": "ok", "type": "contains", "value": "ok"}]
                }
            },
            dataset=[
                {
                    "id": "case-1",
                    "input": "Hello",
                    "assertion_id": "contract",
                }
            ],
        )

        assert config.dataset[0].assertion_ids == ["contract"]

    def test_dataset_item_rejects_duplicate_assertion_ids(
        self, sample_criteria, sample_jurors, sample_llm_provider
    ):
        with pytest.raises(ValidationError, match="cannot contain duplicates"):
            JuryConfig(
                name="Dataset jury",
                llm_provider=sample_llm_provider,
                criteria=sample_criteria,
                jurors=sample_jurors,
                assertions={
                    "contract": {
                        "checks": [{"name": "ok", "type": "contains", "value": "ok"}]
                    }
                },
                dataset=[
                    {
                        "id": "case-1",
                        "input": "Hello",
                        "assertion_ids": ["contract", "contract"],
                    }
                ],
            )

    def test_legacy_assertion_list_becomes_default_policy(
        self, sample_criteria, sample_jurors, sample_llm_provider
    ):
        config = JuryConfig(
            name="Legacy",
            llm_provider=sample_llm_provider,
            criteria=sample_criteria,
            jurors=sample_jurors,
            assertions=[{"name": "legacy", "type": "contains", "value": "ok"}],
        )

        assert config.assertions["default"].checks[0].name == "legacy"
