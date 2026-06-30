import re
from typing import List, Tuple

from openjury.config import AssertionConfig, AssertionType
from openjury.output_format import AssertionResult


def _normalize(value: str, case_sensitive: bool) -> str:
    return value if case_sensitive else value.casefold()


def evaluate_assertions(
    response_text: str, assertions: List[AssertionConfig]
) -> List[AssertionResult]:
    """Evaluate configured deterministic assertions against a response."""
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
        results.append(
            AssertionResult(
                name=assertion.name,
                type=assertion.type,
                passed=passed,
                expected=value,
                detail=detail,
                required=assertion.required,
                weight=assertion.weight,
            )
        )

    return results


def score_assertions(
    results: List[AssertionResult],
) -> Tuple[float, bool]:
    """Return weighted pass rate and whether every required assertion passed.

    An empty assertion set is treated as fully satisfied.
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
