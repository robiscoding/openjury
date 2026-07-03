"""Tests for batch-level aggregation metrics."""

from openjury.batch_summary import aggregate_batch_results
from openjury.execution import EvalItemStatus, EvaluationItem, ItemEvalResult
from openjury.output_format import AgentEvalResult, CriterionEvaluation
from openjury.scoring import JurorScore, ScoredMetrics


def _metrics(weighted_mean: float, agreement: float = 0.9) -> ScoredMetrics:
    return ScoredMetrics(
        weighted_mean=weighted_mean,
        mean=weighted_mean,
        median=weighted_mean,
        min_score=weighted_mean,
        max_score=weighted_mean,
        harmonic_mean=weighted_mean,
        weakest_link=weighted_mean,
        juror_agreement=agreement,
    )


def _result(
    composite: float,
    *,
    passed: bool = True,
    agreement: float = 0.9,
    quality_threshold: float | None = 4.0,
    contested: bool = False,
) -> AgentEvalResult:
    criteria = {
        "factuality": CriterionEvaluation(
            weighted_mean_score=composite,
            min_juror_score=composite - 1,
            max_juror_score=composite,
            juror_agreement=agreement,
            weight=2.0,
            explanations={},
        ),
        "clarity": CriterionEvaluation(
            weighted_mean_score=composite - 0.5,
            min_juror_score=composite - 1,
            max_juror_score=composite,
            juror_agreement=agreement,
            weight=1.0,
            explanations={},
        ),
    }
    lowest_name = min(criteria, key=lambda name: criteria[name].weighted_mean_score)
    return AgentEvalResult(
        jury_name="Test",
        prompt="Q",
        score_scale=5,
        composite_score=composite,
        normalized_composite_score=composite / 5,
        scored_metrics=_metrics(composite, agreement),
        criteria_evaluations=criteria,
        juror_scores=[
            JurorScore(
                juror_name="Juror A",
                juror_weight=1.0,
                criterion_scores={
                    "factuality": composite,
                    "clarity": composite - 0.5,
                },
                latency_ms=100,
            )
        ],
        passed=passed,
        quality_passed=passed,
        assertion_threshold_met=True,
        quality_threshold=quality_threshold,
        lowest_criterion=lowest_name,
        lowest_criterion_score=criteria[lowest_name].weighted_mean_score,
        contested=contested,
    )


def _scored_item(composite: float, **kwargs: object) -> ItemEvalResult:
    return ItemEvalResult(
        item=EvaluationItem(prompt="Q", item_id=f"item-{composite}"),
        index=0,
        result=_result(composite, **kwargs),
        status=EvalItemStatus.SCORED,
        evaluation_duration_ms=10,
    )


def test_pass_rate_uses_scored_items_only() -> None:
    items = [
        _scored_item(4.5, passed=True),
        _scored_item(3.0, passed=False),
        ItemEvalResult(
            item=EvaluationItem(prompt="fail"),
            index=2,
            status=EvalItemStatus.AGENT_FAILED,
            error_code="endpoint_timeout",
            error_message="timeout",
            error_stage="agent",
        ),
    ]
    summary = aggregate_batch_results(items, score_scale=5)
    assert summary.scored_item_count == 2
    assert summary.passed_count == 1
    assert summary.pass_rate == 0.5
    assert summary.coverage.agent_failures == 1
    assert summary.coverage.successfully_scored == 2


def test_score_distribution_percentiles() -> None:
    items = [_scored_item(float(score)) for score in [1, 2, 3, 4, 5]]
    summary = aggregate_batch_results(items, score_scale=5, score_min=1)
    assert summary.score_distribution.mean == 3.0
    assert summary.score_distribution.median == 3.0
    assert summary.score_distribution.min == 1.0
    assert summary.score_distribution.max == 5.0
    assert summary.score_distribution.p10 == 1.4
    assert len(summary.score_distribution.histogram) == 5
    assert summary.score_distribution.histogram[0].count == 1


def test_contested_count() -> None:
    items = [
        _scored_item(4.0, contested=False),
        _scored_item(4.0, contested=True),
    ]
    summary = aggregate_batch_results(items, score_scale=5, contested_threshold=0.6)
    assert summary.contested_count == 1


def test_juror_summary_includes_latency_and_tendency() -> None:
    items = [_scored_item(4.0), _scored_item(3.0)]
    summary = aggregate_batch_results(items, score_scale=5)
    assert len(summary.jurors) == 1
    juror = summary.jurors[0]
    assert juror.juror_name == "Juror A"
    assert juror.mean_latency_ms == 100.0
    assert juror.failure_count == 0


def test_criterion_pass_rate_uses_quality_threshold() -> None:
    items = [
        _scored_item(4.5, quality_threshold=4.0),
        _scored_item(3.0, quality_threshold=4.0),
    ]
    summary = aggregate_batch_results(items, score_scale=5)
    factuality = next(c for c in summary.criteria if c.criterion == "factuality")
    assert factuality.pass_rate == 0.5
