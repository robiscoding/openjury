"""The conformance fixture is a spec of assertion semantics; hold it to it.

`docs/assertion_conformance.json` is what a reimplementation checks itself
against. These tests fail if OpenJury's behaviour drifts away from the
published file, and if the file stops covering the cases that make it worth
publishing.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest
from pydantic import ValidationError

from openjury.assertions import evaluate_assertions
from openjury.config import AssertionConfig, AssertionType

FIXTURE_PATH = (
    Path(__file__).resolve().parent.parent / "docs" / "assertion_conformance.json"
)

REQUIRED_TAGS = {"casefold", "code_points", "raw_response", "python_re_only"}


def load_fixture() -> Dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


FIXTURE = load_fixture()
CASES: List[Dict[str, Any]] = FIXTURE["cases"]


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_conformance_case_matches_evaluate_assertions(case: Dict[str, Any]) -> None:
    assertion = AssertionConfig.model_validate(case["assertion"])
    (result,) = evaluate_assertions(case["response"], [assertion])
    assert result.passed is case["passed"], case["description"]


def test_fixture_covers_every_assertion_type() -> None:
    covered = {case["assertion"]["type"] for case in CASES}
    missing = {member.value for member in AssertionType} - covered
    assert not missing, f"assertion types with no conformance case: {sorted(missing)}"


def test_fixture_covers_every_parity_hazard() -> None:
    tagged = {tag for case in CASES for tag in case["tags"]}
    assert REQUIRED_TAGS <= tagged


def test_fixture_case_ids_are_unique() -> None:
    ids = [case["id"] for case in CASES]
    assert len(ids) == len(set(ids))


def test_regex_matches_the_raw_response_unlike_contains() -> None:
    """The asymmetry the fixture exists to pin, spelled out."""
    by_id = {case["id"]: case for case in CASES}
    contains_case = by_id["contains-casefold-sharp-s"]
    regex_case = by_id["regex-matches-raw-response"]

    assert contains_case["response"] == regex_case["response"]
    assert contains_case["passed"] is True
    assert regex_case["passed"] is False


@pytest.mark.parametrize("assertion_type", ["equals", "not_equals", "contains"])
def test_empty_string_values_are_rejected(assertion_type: str) -> None:
    """No fixture case carries an empty value because config forbids one."""
    with pytest.raises(ValidationError):
        AssertionConfig.model_validate(
            {"name": "empty", "type": assertion_type, "value": ""}
        )
