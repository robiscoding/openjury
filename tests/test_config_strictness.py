"""Unknown config fields are rejected, not silently dropped.

An ignored field is an evaluation that quietly measures less than the author
asked for — the worst failure mode for a library whose job is saying whether
something passed.
"""

import pytest
from pydantic import ValidationError

from openjury.config import (
    AssertionConfig,
    AssertionPolicyDefaults,
    AssertionProfileConfig,
    CriterionConfig,
    DatasetItemConfig,
    JurorConfig,
    JuryConfig,
    LLMProviderConfig,
)

BASE_CONFIG = {
    "name": "Test",
    "criteria": [{"name": "helpfulness", "description": "H"}],
    "jurors": [{"name": "Juror A"}],
    "llm_provider": {
        "provider": "openai_compatible",
        "model_name": "gpt-4o-mini",
        "api_key": "test",
    },
}


def _config(**overrides) -> dict:
    return {**BASE_CONFIG, **overrides}


@pytest.mark.parametrize(
    "model,payload",
    [
        (
            AssertionConfig,
            {"name": "a", "type": "contains", "value": "x", "applies_to": "all"},
        ),
        (AssertionPolicyDefaults, {"assertion_threshold": 0.5, "threshold": 0.5}),
        (
            AssertionProfileConfig,
            {
                "checks": [{"name": "a", "type": "contains", "value": "x"}],
                "assertions": [],
            },
        ),
        (
            DatasetItemConfig,
            {"id": "row-1", "input": "hi", "expected_output": "hello"},
        ),
        (CriterionConfig, {"name": "c", "description": "d", "index": 0}),
        (JurorConfig, {"name": "j", "temp": 0.2}),
        (
            LLMProviderConfig,
            {
                "provider": "openai_compatible",
                "model_name": "gpt-4o-mini",
                "api_key": "test",
                "organization": "acme",
            },
        ),
    ],
)
def test_unknown_field_is_rejected(model, payload) -> None:
    with pytest.raises(ValidationError) as exc_info:
        model.model_validate(payload)
    assert "extra_forbidden" in str(exc_info.value)


def test_jury_config_rejects_unknown_top_level_field() -> None:
    with pytest.raises(ValidationError) as exc_info:
        JuryConfig.model_validate(_config(parallel_execution=True))
    assert "extra_forbidden" in str(exc_info.value)


def test_jury_config_rejects_unknown_nested_field() -> None:
    with pytest.raises(ValidationError) as exc_info:
        JuryConfig.model_validate(
            _config(
                global_assertions=[
                    {
                        "name": "disclaimer",
                        "type": "contains",
                        "value": "not advice",
                        "applies_to": ["row-1"],
                    }
                ]
            )
        )
    assert "extra_forbidden" in str(exc_info.value)


def test_assertions_is_accepted_as_an_alias_for_global_assertions() -> None:
    config = JuryConfig.model_validate(
        _config(
            assertions=[{"name": "disclaimer", "type": "contains", "value": "advice"}]
        )
    )
    assert [check.name for check in config.global_assertions] == ["disclaimer"]


def test_global_assertions_still_populates_by_field_name() -> None:
    config = JuryConfig.model_validate(
        _config(
            global_assertions=[
                {"name": "disclaimer", "type": "contains", "value": "advice"}
            ]
        )
    )
    assert [check.name for check in config.global_assertions] == ["disclaimer"]


def test_serialized_config_round_trips() -> None:
    """Dumping and revalidating must not trip over the alias or over forbid."""
    config = JuryConfig.model_validate(
        _config(
            global_assertions=[
                {"name": "disclaimer", "type": "contains", "value": "advice"}
            ],
            dataset=[{"id": "row-1", "input": "hi", "assertion_profile_ids": []}],
        )
    )
    assert JuryConfig.model_validate(config.model_dump(mode="json")) == config


def test_singular_assertion_profile_id_alias_survives_forbid() -> None:
    item = DatasetItemConfig.model_validate(
        {"id": "row-1", "input": "hi", "assertion_profile_id": "contract"}
    )
    assert item.assertion_profile_ids == ["contract"]
