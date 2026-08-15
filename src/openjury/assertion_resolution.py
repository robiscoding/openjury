"""Resolve global, profile, and inline assertions for a dataset item."""

from __future__ import annotations

import re
from typing import Mapping, Sequence

from openjury.config import (
    AssertionConfig,
    AssertionType,
    JuryConfig,
    ResolvedAssertion,
)

_TEMPLATE_PATTERN = re.compile(r"\{\{(\w+)\}\}")


def _substitute_template_value(
    value: str | list[str] | int,
    variables: Mapping[str, str],
) -> str | list[str] | int:
    if isinstance(value, int):
        return value

    def replace_in_string(text: str) -> str:
        def replacer(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in variables:
                raise ValueError(
                    f"Unknown template variable {key!r}; provide it in dataset variables"
                )
            return variables[key]

        return _TEMPLATE_PATTERN.sub(replacer, text)

    if isinstance(value, list):
        return [replace_in_string(item) for item in value]
    return replace_in_string(value)


def _apply_variables(
    assertions: Sequence[ResolvedAssertion],
    variables: Mapping[str, str],
) -> list[ResolvedAssertion]:
    resolved: list[ResolvedAssertion] = []
    for assertion in assertions:
        substituted = _substitute_template_value(assertion.value, variables)
        if assertion.type in {AssertionType.MIN_LENGTH, AssertionType.MAX_LENGTH}:
            if not isinstance(substituted, int):
                raise ValueError(
                    f"Assertion {assertion.name!r} requires an integer value after "
                    "template substitution"
                )
        elif isinstance(substituted, int):
            raise ValueError(
                f"Assertion {assertion.name!r} requires a string or list value after "
                "template substitution"
            )
        resolved.append(assertion.model_copy(update={"value": substituted}))
    return resolved


def resolve_item_assertions(
    config: JuryConfig,
    *,
    profile_ids: Sequence[str],
    inline_assertions: Sequence[AssertionConfig] | None = None,
    variables: Mapping[str, str] | None = None,
    item_assertion_threshold: float | None = None,
    item_quality_threshold: float | None = None,
) -> tuple[list[ResolvedAssertion], float | None, float | None]:
    """Assemble checks and thresholds for one evaluation item.

    Check order: global_assertions → selected profile checks → inline row checks.
    Threshold precedence: item override → single profile → assertion_policy defaults.

    Every returned check carries the ``scope`` (and ``profile_id``) it came from,
    so a result can be read back without the config that produced it.

    Resolution is idempotent. A check handed in that already carries a scope keeps
    it, and ``global_assertions`` are not applied a second time to a list that
    already contains them — batch callers resolve a case up front and then pass
    the result back through ``evaluate()``, which would otherwise weigh every
    global check twice.
    """
    vars_map = variables or {}
    unknown_ids = [
        profile_id
        for profile_id in profile_ids
        if profile_id not in config.assertion_profiles
    ]
    if unknown_ids:
        raise ValueError(f"Unknown assertion_profile_ids {unknown_ids}")

    supplied = list(inline_assertions or [])
    globals_already_applied = any(
        isinstance(check, ResolvedAssertion) and check.scope == "global"
        for check in supplied
    )

    checks: list[ResolvedAssertion] = []
    if not globals_already_applied:
        checks.extend(
            ResolvedAssertion.from_assertion(check, "global")
            for check in config.global_assertions
        )
    for profile_id in profile_ids:
        checks.extend(
            ResolvedAssertion.from_assertion(check, "profile", profile_id)
            for check in config.assertion_profiles[profile_id].checks
        )
    checks.extend(
        check
        if isinstance(check, ResolvedAssertion)
        else ResolvedAssertion.from_assertion(check, "inline")
        for check in supplied
    )

    checks = _apply_variables(checks, vars_map)

    assertion_threshold = item_assertion_threshold
    quality_threshold = item_quality_threshold

    if len(profile_ids) == 1:
        profile = config.assertion_profiles[profile_ids[0]]
        if assertion_threshold is None:
            assertion_threshold = profile.assertion_threshold
        if quality_threshold is None:
            quality_threshold = profile.quality_threshold

    if assertion_threshold is None:
        assertion_threshold = config.assertion_policy.assertion_threshold
    if quality_threshold is None:
        quality_threshold = config.assertion_policy.quality_threshold

    return checks, assertion_threshold, quality_threshold
