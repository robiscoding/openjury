"""Tests for AgentEvalResult JSON serialization."""

import json

from openjury.output_format import (
    AgentEvalResult,
    CriterionEvaluation,
    TrialResult,
    serialize_eval_result,
)
from openjury.scoring import JurorScore, ScoredMetrics


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
