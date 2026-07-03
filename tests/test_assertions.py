import pytest
from pydantic import ValidationError

from openjury.assertions import evaluate_assertions, score_assertions
from openjury.config import AssertionConfig, AssertionType, JuryConfig
from openjury.output_format import AssertionResult


@pytest.mark.parametrize(
    ("assertion_type", "value", "response", "passed"),
    [
        ("contains", "refund", "Request a refund.", True),
        ("not_contains", "error", "Request a refund.", True),
        ("equals", "done", "done", True),
        ("not_equals", "failed", "done", True),
        ("starts_with", "Answer:", "Answer: 42", True),
        ("ends_with", "42", "Answer: 42", True),
        ("contains_any", ["red", "blue"], "The car is blue.", True),
        ("contains_all", ["car", "blue"], "The car is blue.", True),
        ("regex", r"\b\d{2}\b", "Answer: 42", True),
        ("min_length", 3, "abc", True),
        ("max_length", 3, "abc", True),
        ("contains_all", ["car", "red"], "The car is blue.", False),
        ("min_length", 4, "abc", False),
        ("max_length", 2, "abc", False),
    ],
)
def test_assertion_types(
    assertion_type: str,
    value: str | list[str] | int,
    response: str,
    passed: bool,
) -> None:
    assertion = AssertionConfig(
        name="check",
        type=assertion_type,
        value=value,
    )

    result = evaluate_assertions(response, [assertion])

    assert result[0].passed is passed
    assert result[0].expected == value


@pytest.mark.parametrize(
    ("assertion_type", "value"),
    [
        ("contains", "Hello"),
        ("equals", "HELLO THERE"),
        ("starts_with", "Hello"),
        ("ends_with", "THERE"),
        ("contains_any", ["missing", "HELLO"]),
        ("contains_all", ["HELLO", "THERE"]),
        ("regex", r"^HELLO"),
    ],
)
def test_string_assertions_can_ignore_case(
    assertion_type: str, value: str | list[str]
) -> None:
    assertion = AssertionConfig(
        name="case insensitive",
        type=assertion_type,
        value=value,
        case_sensitive=False,
    )

    result = evaluate_assertions("hello there", [assertion])

    assert result[0].passed is True


@pytest.mark.parametrize(
    ("assertion_type", "value"),
    [
        ("contains", ""),
        ("contains_any", []),
        ("contains_all", [""]),
        ("min_length", -1),
        ("max_length", "10"),
        ("regex", "["),
    ],
)
def test_invalid_assertion_values_are_rejected(
    assertion_type: str, value: str | list[str] | int
) -> None:
    with pytest.raises(ValidationError):
        AssertionConfig(name="invalid", type=assertion_type, value=value)


def test_assertions_default_to_empty(
    sample_criteria, sample_jurors, sample_llm_provider
) -> None:
    config = JuryConfig(
        name="No assertions",
        llm_provider=sample_llm_provider,
        criteria=sample_criteria,
        jurors=sample_jurors,
    )

    assert config.global_assertions == []
    assert config.assertion_profiles == {}
    assert config.assertion_policy.assertion_threshold is None
    assert config.assertion_policy.quality_threshold is None


def test_assertion_score_is_weighted_and_required_policy_is_separate() -> None:
    assertions = [
        AssertionConfig(
            name="required contract",
            type="contains",
            value="CONF-",
            required=True,
            weight=2.0,
        ),
        AssertionConfig(
            name="optional courtesy",
            type="contains",
            value="thank you",
            required=False,
            weight=1.0,
        ),
    ]

    results = evaluate_assertions("thank you", assertions)
    assertion_score, assertions_passed = score_assertions(results)

    assert assertion_score == pytest.approx(1 / 3)
    assert assertions_passed is False
    assert results[0].required is True
    assert results[0].weight == 2.0


def test_no_assertions_are_fully_satisfied() -> None:
    assert score_assertions([]) == (1.0, True)


@pytest.mark.parametrize("weight", [0, -1])
def test_assertion_weight_must_be_positive(weight: float) -> None:
    with pytest.raises(ValidationError):
        AssertionConfig(
            name="invalid weight",
            type="contains",
            value="ok",
            weight=weight,
        )


@pytest.mark.parametrize("weight", [0, -1])
def test_assertion_result_weight_must_be_positive(weight: float) -> None:
    with pytest.raises(ValidationError):
        AssertionResult(
            name="invalid weight",
            type="contains",
            passed=True,
            expected="ok",
            detail="manually constructed result",
            weight=weight,
        )


def test_score_assertions_rejects_non_positive_total_weight() -> None:
    result = AssertionResult.model_construct(
        name="invalid weight",
        type=AssertionType.CONTAINS,
        passed=True,
        expected="ok",
        detail="validation bypassed",
        weight=0,
    )

    with pytest.raises(
        ValueError, match="Assertion result weights must sum to a positive value"
    ):
        score_assertions([result])


def test_quality_threshold_cannot_exceed_score_scale(
    sample_criteria, sample_jurors, sample_llm_provider
) -> None:
    with pytest.raises(ValidationError):
        JuryConfig(
            name="Invalid threshold",
            llm_provider=sample_llm_provider,
            criteria=sample_criteria,
            jurors=sample_jurors,
            score_scale=5,
            assertion_policy={"quality_threshold": 5.1},
        )


def test_assertion_type_enum_lists_all_supported_types() -> None:
    assert {assertion_type.value for assertion_type in AssertionType} == {
        "contains",
        "not_contains",
        "equals",
        "not_equals",
        "starts_with",
        "ends_with",
        "contains_any",
        "contains_all",
        "regex",
        "min_length",
        "max_length",
    }
