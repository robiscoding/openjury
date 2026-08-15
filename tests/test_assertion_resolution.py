import pytest

from openjury.assertion_resolution import resolve_item_assertions
from openjury.config import (
    AssertionConfig,
    AssertionPolicyDefaults,
    AssertionProfileConfig,
    JuryConfig,
    ResolvedAssertion,
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


def test_resolved_checks_carry_their_scope():
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
    assert [(check.scope, check.profile_id) for check in checks] == [
        ("global", None),
        ("profile", "contract"),
        ("inline", None),
    ]


def test_scope_survives_template_substitution():
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
    checks, _, _ = resolve_item_assertions(
        config, profile_ids=["order"], variables={"order_number": "12345"}
    )
    assert checks[0].value == "order #12345"
    assert checks[0].scope == "profile"
    assert checks[0].profile_id == "order"


def test_an_already_resolved_check_keeps_its_scope():
    config = _base_config()
    resolved = ResolvedAssertion.from_assertion(
        AssertionConfig(name="contract", type="contains", value="c"),
        "profile",
        "contract",
    )
    checks, _, _ = resolve_item_assertions(
        config, profile_ids=[], inline_assertions=[resolved]
    )
    assert (checks[0].scope, checks[0].profile_id) == ("profile", "contract")


def test_resolution_is_idempotent_for_globals():
    """Batch callers resolve up front and pass the result back through evaluate()."""
    config = _base_config(
        global_assertions=[{"name": "global", "type": "contains", "value": "g"}]
    )
    once, _, _ = resolve_item_assertions(config, profile_ids=[])
    twice, _, _ = resolve_item_assertions(
        config, profile_ids=[], inline_assertions=once
    )

    assert [check.name for check in twice] == ["global"]
    assert twice == once


def test_raw_checks_still_supplement_globals():
    config = _base_config(
        global_assertions=[{"name": "global", "type": "contains", "value": "g"}]
    )
    checks, _, _ = resolve_item_assertions(
        config,
        profile_ids=[],
        inline_assertions=[AssertionConfig(name="inline", type="contains", value="i")],
    )
    assert [(check.name, check.scope) for check in checks] == [
        ("global", "global"),
        ("inline", "inline"),
    ]
