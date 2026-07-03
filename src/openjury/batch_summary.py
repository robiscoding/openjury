"""Batch-level aggregation for multi-item evaluation runs."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Sequence

from pydantic import BaseModel, Field

from openjury.execution import EvalItemStatus, ItemEvalResult
from openjury.output_format import AgentEvalResult


class ScoreBucket(BaseModel):
    label: str
    count: int
    lower: float
    upper: float


class ScoreDistribution(BaseModel):
    mean: float
    median: float
    p10: float
    min: float
    max: float
    histogram: List[ScoreBucket] = Field(default_factory=list)


class ExecutionCoverage(BaseModel):
    dataset_items: int
    successfully_scored: int
    agent_failures: int
    all_jurors_failed: int
    cancelled: int
    partial_juror_failure_items: int
    error_breakdown: Dict[str, int] = Field(default_factory=dict)


class CriterionRunSummary(BaseModel):
    criterion: str
    mean_score: float
    pass_rate: float
    mean_agreement: float
    min_score: float
    p10_score: float


class JurorRunSummary(BaseModel):
    juror_name: str
    mean_score: float
    scoring_tendency: float
    panel_agreement: float
    failure_count: int
    mean_latency_ms: Optional[float] = None


class BatchRunSummary(BaseModel):
    """Aggregate metrics across a batch evaluation run."""

    mean_composite_score: float
    scored_item_count: int
    pass_rate: float
    passed_count: int
    mean_juror_agreement: float
    contested_count: int
    contested_threshold: float
    duration_ms: Optional[int] = None
    score_distribution: ScoreDistribution
    coverage: ExecutionCoverage
    criteria: List[CriterionRunSummary] = Field(default_factory=list)
    jurors: List[JurorRunSummary] = Field(default_factory=list)


@dataclass
class BatchEvalResult:
    items: List[ItemEvalResult]
    summary: BatchRunSummary
    started_at: datetime
    finished_at: datetime
    duration_ms: int


def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * p / 100.0
    lower_index = int(k)
    upper_index = min(lower_index + 1, len(sorted_vals) - 1)
    if lower_index == upper_index:
        return sorted_vals[lower_index]
    fraction = k - lower_index
    return (
        sorted_vals[lower_index]
        + (sorted_vals[upper_index] - sorted_vals[lower_index]) * fraction
    )


def _build_histogram(
    scores: List[float], score_min: int, score_scale: int
) -> List[ScoreBucket]:
    if score_min == score_scale:
        count = sum(1 for score in scores if int(round(score)) == score_scale)
        return [
            ScoreBucket(
                label=str(score_scale),
                count=count,
                lower=float(score_scale),
                upper=float(score_scale),
            )
        ]

    buckets: List[ScoreBucket] = []
    for bucket in range(score_min, score_scale + 1):
        if bucket < score_scale:
            lower = float(bucket)
            upper = float(bucket) + 0.999
            label = str(bucket)
            count = sum(1 for score in scores if lower <= score < bucket + 1)
        else:
            lower = float(bucket)
            upper = float(bucket)
            label = str(bucket)
            count = sum(1 for score in scores if score >= bucket)
        buckets.append(ScoreBucket(label=label, count=count, lower=lower, upper=upper))
    return buckets


def _juror_weighted_total(result: AgentEvalResult, juror_name: str) -> Optional[float]:
    total_weight = sum(c.weight for c in result.criteria_evaluations.values())
    if total_weight <= 0:
        return None
    juror = next(
        (js for js in result.juror_scores if js.juror_name == juror_name), None
    )
    if juror is None:
        return None
    total = 0.0
    for criterion_name, criterion_eval in result.criteria_evaluations.items():
        total += juror.criterion_scores.get(criterion_name, 0.0) * criterion_eval.weight
    return total / total_weight


def _panel_agreement_for_juror(result: AgentEvalResult, juror_name: str) -> float:
    juror = next(
        (js for js in result.juror_scores if js.juror_name == juror_name), None
    )
    if juror is None or not result.criteria_evaluations:
        return 1.0
    scale = max(result.score_scale, 1)
    agreements: List[float] = []
    for criterion_name, criterion_eval in result.criteria_evaluations.items():
        juror_score = juror.criterion_scores.get(criterion_name, 0.0)
        deviation = abs(juror_score - criterion_eval.weighted_mean_score) / scale
        agreements.append(max(0.0, 1.0 - deviation))
    return statistics.mean(agreements) if agreements else 1.0


def aggregate_batch_results(
    items: Sequence[ItemEvalResult],
    *,
    score_scale: int,
    score_min: int = 1,
    contested_threshold: float = 0.6,
    quality_threshold: Optional[float] = None,
    duration_ms: Optional[int] = None,
) -> BatchRunSummary:
    """Aggregate per-item results into run-level dashboard metrics."""
    scored_items = [item for item in items if item.status == EvalItemStatus.SCORED]
    composite_scores = [
        item.result.composite_score for item in scored_items if item.result is not None
    ]

    passed_count = sum(
        1 for item in scored_items if item.result is not None and item.result.passed
    )
    scored_count = len(scored_items)
    pass_rate = passed_count / scored_count if scored_count else 0.0
    mean_composite = statistics.mean(composite_scores) if composite_scores else 0.0

    agreement_values = [
        item.result.scored_metrics.juror_agreement
        for item in scored_items
        if item.result is not None
    ]
    mean_agreement = statistics.mean(agreement_values) if agreement_values else 0.0
    contested_count = sum(
        1 for item in scored_items if item.result is not None and item.result.contested
    )

    distribution = ScoreDistribution(
        mean=mean_composite,
        median=statistics.median(composite_scores) if composite_scores else 0.0,
        p10=_percentile(composite_scores, 10.0),
        min=min(composite_scores) if composite_scores else 0.0,
        max=max(composite_scores) if composite_scores else 0.0,
        histogram=_build_histogram(composite_scores, score_min, score_scale),
    )

    error_breakdown: Dict[str, int] = {}
    for item in items:
        if item.status == EvalItemStatus.SCORED:
            continue
        code = item.error_code or "evaluation_error"
        error_breakdown[code] = error_breakdown.get(code, 0) + 1

    coverage = ExecutionCoverage(
        dataset_items=len(items),
        successfully_scored=scored_count,
        agent_failures=sum(
            1 for item in items if item.status == EvalItemStatus.AGENT_FAILED
        ),
        all_jurors_failed=sum(
            1 for item in items if item.status == EvalItemStatus.ALL_JURORS_FAILED
        ),
        cancelled=sum(1 for item in items if item.status == EvalItemStatus.CANCELLED),
        partial_juror_failure_items=sum(
            1
            for item in scored_items
            if item.result is not None and item.result.juror_failures
        ),
        error_breakdown=error_breakdown,
    )

    criterion_names = sorted(
        {
            criterion_name
            for item in scored_items
            if item.result is not None
            for criterion_name in item.result.criteria_evaluations
        }
    )
    criteria_summaries: List[CriterionRunSummary] = []
    for criterion_name in criterion_names:
        criterion_scores: List[float] = []
        criterion_agreements: List[float] = []
        passed_for_criterion = 0
        for item in scored_items:
            if item.result is None:
                continue
            criterion_eval = item.result.criteria_evaluations.get(criterion_name)
            if criterion_eval is None:
                continue
            criterion_scores.append(criterion_eval.weighted_mean_score)
            criterion_agreements.append(criterion_eval.juror_agreement)
            threshold = item.result.quality_threshold
            if threshold is None:
                threshold = quality_threshold
            if threshold is None or criterion_eval.weighted_mean_score >= threshold:
                passed_for_criterion += 1
        criteria_summaries.append(
            CriterionRunSummary(
                criterion=criterion_name,
                mean_score=(
                    statistics.mean(criterion_scores) if criterion_scores else 0.0
                ),
                pass_rate=(
                    passed_for_criterion / len(criterion_scores)
                    if criterion_scores
                    else 0.0
                ),
                mean_agreement=(
                    statistics.mean(criterion_agreements)
                    if criterion_agreements
                    else 0.0
                ),
                min_score=min(criterion_scores) if criterion_scores else 0.0,
                p10_score=_percentile(criterion_scores, 10.0),
            )
        )

    juror_names = sorted(
        {
            js.juror_name
            for item in scored_items
            if item.result is not None
            for js in item.result.juror_scores
        }
    )
    juror_failures: Dict[str, int] = {}
    for item in scored_items:
        if item.result is None:
            continue
        for failure in item.result.juror_failures:
            juror_failures[failure.juror_name] = (
                juror_failures.get(failure.juror_name, 0) + 1
            )

    juror_summaries: List[JurorRunSummary] = []
    for juror_name in juror_names:
        juror_totals: List[float] = []
        panel_totals: List[float] = []
        panel_agreements: List[float] = []
        latencies: List[int] = []
        for item in scored_items:
            if item.result is None:
                continue
            total = _juror_weighted_total(item.result, juror_name)
            if total is not None:
                juror_totals.append(total)
                panel_totals.append(item.result.composite_score)
                panel_agreements.append(
                    _panel_agreement_for_juror(item.result, juror_name)
                )
            juror_score = next(
                (js for js in item.result.juror_scores if js.juror_name == juror_name),
                None,
            )
            if juror_score is not None and juror_score.latency_ms is not None:
                latencies.append(juror_score.latency_ms)
        juror_mean = statistics.mean(juror_totals) if juror_totals else 0.0
        panel_mean = statistics.mean(panel_totals) if panel_totals else 0.0
        juror_summaries.append(
            JurorRunSummary(
                juror_name=juror_name,
                mean_score=juror_mean,
                scoring_tendency=juror_mean - panel_mean,
                panel_agreement=(
                    statistics.mean(panel_agreements) if panel_agreements else 0.0
                ),
                failure_count=juror_failures.get(juror_name, 0),
                mean_latency_ms=(statistics.mean(latencies) if latencies else None),
            )
        )

    return BatchRunSummary(
        mean_composite_score=mean_composite,
        scored_item_count=scored_count,
        pass_rate=pass_rate,
        passed_count=passed_count,
        mean_juror_agreement=mean_agreement,
        contested_count=contested_count,
        contested_threshold=contested_threshold,
        duration_ms=duration_ms,
        score_distribution=distribution,
        coverage=coverage,
        criteria=criteria_summaries,
        jurors=juror_summaries,
    )
