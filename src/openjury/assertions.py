"""Evaluate deterministic checks against an agent response.

Semantics that a reimplementation in another language will get wrong unless it
is deliberate about them. `docs/assertion_conformance.json` pins all of them as
data; regenerate it with `python scripts/export_assertion_conformance.py`.

- Case-insensitive matching uses `str.casefold()`, not a plain lowercase.
  Casefold is more aggressive: `ß` folds to `ss`, `ﬁ` to `fi`, final sigma `ς`
  to `σ`. It is locale-independent, so Turkish dotless `ı` does not fold
  together with `I`.
- `min_length` / `max_length` count what `len()` counts: Unicode code points.
  An astral character such as an emoji costs 1, not the 2 UTF-16 units a
  JavaScript `.length` would report.
- `regex` matches the **raw** response, not the case-normalized one — unlike
  every other type. With `case_sensitive=false` it applies `re.IGNORECASE`
  instead, which is not equivalent to casefolding both sides.
- `regex` patterns are Python `re`. Other regex dialects do not accept the same
  language (inline flags such as `(?i)`, `\\Z`, named-group syntax), so a port
  cannot match this type in general and should treat it as advisory.
"""

import re
from typing import List, Optional, Tuple

from openjury.config import (
    AssertionConfig,
    AssertionScope,
    AssertionType,
    ResolvedAssertion,
)
from openjury.output_format import AssertionResult


def _normalize(value: str, case_sensitive: bool) -> str:
    return value if case_sensitive else value.casefold()


def _origin(assertion: AssertionConfig) -> Tuple[AssertionScope, Optional[str]]:
    """Return the (scope, profile_id) of a check.

    Assertions handed straight to this function rather than through
    `resolve_item_assertions` carry no origin; they applied to whatever the
    caller passed, which is what 'global' means.
    """
    if isinstance(assertion, ResolvedAssertion):
        return assertion.scope, assertion.profile_id
    return "global", None


def evaluate_assertions(
    response_text: str, assertions: List[AssertionConfig]
) -> List[AssertionResult]:
    """Evaluate configured deterministic assertions against a response.

    See the module docstring for the matching semantics each type commits to.
    """
    results: List[AssertionResult] = []

    for assertion in assertions:
        value = assertion.value
        normalized_response = _normalize(response_text, assertion.case_sensitive)

        if assertion.type in {
            AssertionType.CONTAINS,
            AssertionType.NOT_CONTAINS,
            AssertionType.EQUALS,
            AssertionType.NOT_EQUALS,
            AssertionType.STARTS_WITH,
            AssertionType.ENDS_WITH,
        }:
            assert isinstance(value, str)
            normalized_value = _normalize(value, assertion.case_sensitive)
            if assertion.type == AssertionType.CONTAINS:
                passed = normalized_value in normalized_response
            elif assertion.type == AssertionType.NOT_CONTAINS:
                passed = normalized_value not in normalized_response
            elif assertion.type == AssertionType.EQUALS:
                passed = normalized_response == normalized_value
            elif assertion.type == AssertionType.NOT_EQUALS:
                passed = normalized_response != normalized_value
            elif assertion.type == AssertionType.STARTS_WITH:
                passed = normalized_response.startswith(normalized_value)
            else:
                passed = normalized_response.endswith(normalized_value)
        elif assertion.type in {
            AssertionType.CONTAINS_ANY,
            AssertionType.CONTAINS_ALL,
        }:
            assert isinstance(value, list)
            matches = [
                _normalize(item, assertion.case_sensitive) in normalized_response
                for item in value
            ]
            passed = (
                any(matches)
                if assertion.type == AssertionType.CONTAINS_ANY
                else all(matches)
            )
        elif assertion.type == AssertionType.REGEX:
            assert isinstance(value, str)
            flags = 0 if assertion.case_sensitive else re.IGNORECASE
            passed = re.search(value, response_text, flags) is not None
        elif assertion.type == AssertionType.MIN_LENGTH:
            assert isinstance(value, int)
            passed = len(response_text) >= value
        else:
            assert assertion.type == AssertionType.MAX_LENGTH
            assert isinstance(value, int)
            passed = len(response_text) <= value

        detail = (
            f"{assertion.type.value} assertion passed for {value!r}"
            if passed
            else f"{assertion.type.value} assertion failed for {value!r}"
        )
        scope, profile_id = _origin(assertion)
        results.append(
            AssertionResult(
                name=assertion.name,
                type=assertion.type,
                passed=passed,
                expected=value,
                detail=detail,
                required=assertion.required,
                weight=assertion.weight,
                scope=scope,
                profile_id=profile_id,
            )
        )

    return results


def score_assertions(
    results: List[AssertionResult],
) -> Tuple[float, bool]:
    """Return weighted pass rate and whether every required assertion passed.

    An empty assertion set is treated as fully satisfied.

    The returned flag is only half of the assertion verdict. It answers "did
    every check marked `required=True` pass?" and nothing else. A configured
    `assertion_threshold` is applied separately against the returned pass rate
    and surfaces as `AgentEvalResult.assertion_threshold_met`; a consumer that
    reads only `assertions_passed` silently ignores it.
    """
    if not results:
        return 1.0, True

    total_weight = sum(result.weight for result in results)
    if total_weight <= 0:
        raise ValueError("Assertion result weights must sum to a positive value")

    passed_weight = sum(result.weight for result in results if result.passed)
    assertion_score = passed_weight / total_weight
    assertions_passed = all(result.passed for result in results if result.required)
    return assertion_score, assertions_passed
