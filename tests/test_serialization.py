"""Tests for AgentEvalResult JSON serialization."""

import json

from openjury.execution import JurorFailure
from openjury.output_format import (
    AgentEvalResult,
    CriterionEvaluation,
    TrialResult,
    serialize_eval_result,
)
from openjury.scoring import JurorScore, ScoredMetrics, TokenUsage


def _sample_result() -> AgentEvalResult:
    juror_scores = [
        JurorScore(
            juror_name="Juror A",
            juror_weight=1.0,
            criterion_scores={"helpfulness": 4.0},
            criterion_explanations={"helpfulness": "Good"},
        )
    ]
    metrics = ScoredMetrics(
        weighted_mean=4.0,
        mean=4.0,
        median=4.0,
        min_score=4.0,
        max_score=4.0,
        harmonic_mean=4.0,
        weakest_link=4.0,
        juror_agreement=1.0,
    )
    trial = TrialResult(
        trial_number=1,
        response_text="Answer text",
        scored_metrics=metrics,
        criteria_evaluations={
            "helpfulness": CriterionEvaluation(
                weighted_mean_score=4.0,
                min_juror_score=4.0,
                max_juror_score=4.0,
                juror_agreement=1.0,
                weight=1.0,
                explanations={"Juror A": "Good"},
            )
        },
        juror_scores=juror_scores,
    )
    return AgentEvalResult(
        jury_name="Test Jury",
        prompt="Question?",
        endpoint_alias="agent-a",
        score_scale=5,
        composite_score=4.0,
        normalized_composite_score=0.8,
        scored_metrics=metrics,
        criteria_evaluations=trial.criteria_evaluations,
        juror_scores=juror_scores,
        trial_results=[trial],
    )


def test_serialize_eval_result_is_json_serializable() -> None:
    payload = serialize_eval_result(_sample_result())
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)
    assert decoded["jury_name"] == "Test Jury"
    assert decoded["composite_score"] == 4.0
    assert decoded["assertion_score"] == 1.0
    assert decoded["assertions_passed"] is True
    assert decoded["passed"] is True


def test_serialize_eval_result_includes_juror_scores() -> None:
    payload = serialize_eval_result(_sample_result())
    assert payload["juror_scores"] == [
        {
            "juror_name": "Juror A",
            "juror_weight": 1.0,
            "criterion_scores": {"helpfulness": 4.0},
            "criterion_explanations": {"helpfulness": "Good"},
        }
    ]


def test_serialize_eval_result_includes_trial_juror_scores() -> None:
    payload = serialize_eval_result(_sample_result())
    trial = payload["trial_results"][0]
    assert trial["juror_scores"] == [
        {
            "juror_name": "Juror A",
            "juror_weight": 1.0,
            "criterion_scores": {"helpfulness": 4.0},
            "criterion_explanations": {"helpfulness": "Good"},
        }
    ]


def _result_with_usage() -> AgentEvalResult:
    result = _sample_result()
    usage = TokenUsage(
        prompt_tokens=1150,
        completion_tokens=250,
        total_tokens=1400,
        cached_tokens=128,
        cost=0.00027,
        model="openai/gpt-oss-20b",
    )
    result.juror_scores[0].usage = usage
    result.juror_failures = [
        JurorFailure(
            juror_name="Juror B",
            code="juror_missing_criteria",
            message="missing scores",
            usage=TokenUsage(prompt_tokens=1100, completion_tokens=40),
        )
    ]
    return result


def test_serialize_eval_result_includes_token_usage() -> None:
    payload = serialize_eval_result(_result_with_usage())
    assert payload["juror_scores"][0]["usage"] == {
        "prompt_tokens": 1150,
        "completion_tokens": 250,
        "total_tokens": 1400,
        "cached_tokens": 128,
        "cost": 0.00027,
        "model": "openai/gpt-oss-20b",
    }


def test_serialize_eval_result_includes_failed_juror_usage() -> None:
    payload = serialize_eval_result(_result_with_usage())
    failure = payload["juror_failures"][0]
    assert failure["usage"]["prompt_tokens"] == 1100
    assert failure["usage"]["completion_tokens"] == 40


def test_serialized_usage_stays_json_encodable() -> None:
    decoded = json.loads(json.dumps(serialize_eval_result(_result_with_usage())))
    assert decoded["juror_scores"][0]["usage"]["cost"] == 0.00027


def test_juror_scores_omit_usage_key_when_unreported() -> None:
    payload = serialize_eval_result(_sample_result())
    assert "usage" not in payload["juror_scores"][0]
