import pytest

from openjury.assertion_resolution import resolve_item_assertions
from openjury.config import (
    AssertionConfig,
    AssertionPolicyDefaults,
    AssertionProfileConfig,
    JuryConfig,
)


def _base_config(**overrides) -> JuryConfig:
    data = {
        "name": "Test",
        "criteria": [{"name": "helpfulness", "description": "H"}],
        "jurors": [{"name": "Juror A"}],
        "llm_provider": {
            "provider": "openai_compatible",
            "model_name": "gpt-4o-mini",
            "api_key": "test",
        },
    }
    data.update(overrides)
    return JuryConfig.model_validate(data)


def test_resolve_order_global_profile_inline():
    config = _base_config(
        global_assertions=[{"name": "global", "type": "contains", "value": "g"}],
        assertion_profiles={
            "contract": {
                "checks": [{"name": "profile", "type": "contains", "value": "p"}]
            }
        },
    )
    checks, _, _ = resolve_item_assertions(
        config,
        profile_ids=["contract"],
        inline_assertions=[AssertionConfig(name="inline", type="contains", value="i")],
    )
    assert [check.name for check in checks] == ["global", "profile", "inline"]


def test_resolve_globals_only_without_profiles():
    config = _base_config(
        global_assertions=[{"name": "global", "type": "contains", "value": "g"}]
    )
    checks, _, _ = resolve_item_assertions(config, profile_ids=[])
    assert len(checks) == 1
    assert checks[0].name == "global"


def test_threshold_precedence_item_profile_policy():
    config = _base_config(
        assertion_policy={
            "assertion_threshold": 0.5,
            "quality_threshold": 2.0,
        },
        assertion_profiles={
            "contract": {
                "checks": [{"name": "ok", "type": "contains", "value": "ok"}],
                "assertion_threshold": 0.8,
                "quality_threshold": 3.0,
            }
        },
    )
    _, at, qt = resolve_item_assertions(config, profile_ids=["contract"])
    assert at == 0.8
    assert qt == 3.0

    _, at, qt = resolve_item_assertions(
        config,
        profile_ids=["contract"],
        item_assertion_threshold=0.95,
    )
    assert at == 0.95
    assert qt == 3.0

    _, at, qt = resolve_item_assertions(
        config,
        profile_ids=[],
        item_quality_threshold=4.5,
    )
    assert at == 0.5
    assert qt == 4.5


def test_template_substitution_in_string_and_list_values():
    config = _base_config(
        assertion_profiles={
            "order": {
                "checks": [
                    {
                        "name": "order number",
                        "type": "contains",
                        "value": "order #{{order_number}}",
                    },
                    {
                        "name": "states",
                        "type": "contains_any",
                        "value": ["{{state_a}}", "{{state_b}}"],
                    },
                ]
            }
        },
    )
    checks, _, _ = resolve_item_assertions(
        config,
        profile_ids=["order"],
        variables={"order_number": "12345", "state_a": "shipped", "state_b": "delayed"},
    )
    assert checks[0].value == "order #12345"
    assert checks[1].value == ["shipped", "delayed"]


def test_unknown_template_variable_raises():
    config = _base_config(
        assertion_profiles={
            "order": {
                "checks": [
                    {
                        "name": "order number",
                        "type": "contains",
                        "value": "order #{{order_number}}",
                    }
                ]
            }
        },
    )
    with pytest.raises(ValueError, match="Unknown template variable"):
        resolve_item_assertions(config, profile_ids=["order"], variables={})


def test_unknown_profile_id_raises():
    config = _base_config()
    with pytest.raises(ValueError, match="Unknown assertion_profile_ids"):
        resolve_item_assertions(config, profile_ids=["missing"])
