"""Scoring aggregation for agent evaluation."""

import statistics
import warnings
from dataclasses import dataclass, field
from typing import Callable, ClassVar, Dict, List, Optional

from pydantic import BaseModel

from openjury.config import CriterionConfig

ScoringFunction = Callable[[List["JurorScore"], List[CriterionConfig]], float]


@dataclass
class JurorScore:
    juror_name: str
    juror_weight: float
    criterion_scores: Dict[str, float] = field(default_factory=dict)
    criterion_explanations: Dict[str, str] = field(default_factory=dict)


class ScoredMetrics(BaseModel):
    """All canned scoring metrics for one evaluation trial. All values are on the
    score_scale axis (e.g. 1-5). Only normalized value is in AgentEvalResult."""

    weighted_mean: float
    mean: float
    median: float
    min_score: float
    max_score: float
    harmonic_mean: float
    weakest_link: float
    juror_agreement: float
    custom: Optional[float] = None


class ConsistencyResult(BaseModel):
    """Populated only when num_trials > 1. Measures agent reliability, not quality.

    The primary signal is score_std — low std means the agent produces consistently
    similar responses; high std means the agent is unpredictable at this prompt.
    score_mean is informational only and is NOT the composite quality score.
    """

    num_trials: int
    trial_composite_scores: List[float]
    score_std: float
    score_mean: float
    score_min: float
    score_max: float
    interpretation: str


def _criterion_agreement(scores: List[float]) -> float:
    """Juror agreement for one criterion: 1 − CoV, clamped to [0, 1].

    Returns 1.0 (perfect agreement) when there is only one juror or the mean is zero.
    """
    if len(scores) <= 1:
        return 1.0
    mean_c = statistics.mean(scores)
    if mean_c <= 0:
        return 1.0
    cov = statistics.stdev(scores) / mean_c
    return max(0.0, min(1.0, 1.0 - cov))


class ScoreAggregator:
    _custom_functions: ClassVar[Dict[str, ScoringFunction]] = {}

    @classmethod
    def register(cls, name: str, fn: ScoringFunction) -> None:
        """Register a global custom scoring function by name.

        Deprecated: pass custom_scoring_functions={'name': fn} to OpenJury() instead.
        The global registry is kept for backward compatibility.
        """
        warnings.warn(
            "ScoreAggregator.register() is deprecated. "
            "Pass custom_scoring_functions={'name': fn} to OpenJury() instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        cls._custom_functions[name] = fn

    @classmethod
    def unregister(cls, name: str) -> None:
        """Remove a globally registered custom scoring function."""
        cls._custom_functions.pop(name, None)

    @classmethod
    def list_custom(cls) -> List[str]:
        return list(cls._custom_functions.keys())

    @classmethod
    def compute_all(
        cls,
        juror_scores: List[JurorScore],
        criteria: List[CriterionConfig],
        custom_fn: Optional[ScoringFunction] = None,
    ) -> ScoredMetrics:
        if not juror_scores:
            raise ValueError("No juror scores provided")
        if not criteria:
            raise ValueError("No criteria provided")

        total_crit_weight = sum(c.weight for c in criteria)
        total_juror_weight = sum(js.juror_weight for js in juror_scores)

        # weighted_mean: for each criterion, weighted avg of juror scores by juror weight;
        # then criteria-weight-avg across criteria
        crit_weighted_avg: Dict[str, float] = {}
        for c in criteria:
            w_sum = sum(
                js.criterion_scores.get(c.name, 0.0) * js.juror_weight
                for js in juror_scores
            )
            crit_weighted_avg[c.name] = (
                w_sum / total_juror_weight if total_juror_weight else 0.0
            )

        weighted_mean = (
            sum(crit_weighted_avg[c.name] * c.weight for c in criteria)
            / total_crit_weight
            if total_crit_weight
            else 0.0
        )

        # mean: unweighted over all (juror, criterion) pairs
        all_raw: List[float] = [
            js.criterion_scores.get(c.name, 0.0)
            for js in juror_scores
            for c in criteria
        ]
        mean = statistics.mean(all_raw) if all_raw else 0.0

        # per-juror criteria-weighted totals (used for median/min/max)
        juror_totals: List[float] = [
            (
                (
                    sum(
                        js.criterion_scores.get(c.name, 0.0) * c.weight
                        for c in criteria
                    )
                    / total_crit_weight
                )
                if total_crit_weight
                else 0.0
            )
            for js in juror_scores
        ]

        median = statistics.median(juror_totals)
        min_score = min(juror_totals)
        max_score = max(juror_totals)

        # harmonic_mean: per-criterion harmonic mean of juror scores; then criteria-weight-avg
        crit_harmonic: Dict[str, float] = {}
        for c in criteria:
            scores_for_crit = [
                js.criterion_scores.get(c.name, 0.0) for js in juror_scores
            ]
            safe = [max(s, 0.001) for s in scores_for_crit]
            crit_harmonic[c.name] = len(safe) / sum(1.0 / s for s in safe)
        harmonic_mean = (
            sum(crit_harmonic[c.name] * c.weight for c in criteria) / total_crit_weight
            if total_crit_weight
            else 0.0
        )

        # weakest_link: the worst-performing criterion by weighted juror consensus.
        # Uses the already-computed crit_weighted_avg so weights are applied once and
        # consistently. The minimum identifies the criterion pulling the score down most.
        weakest_link = min(crit_weighted_avg.values()) if crit_weighted_avg else 0.0

        # juror_agreement: mean per-criterion agreement, each in [0, 1]
        crit_agreements = [
            _criterion_agreement(
                [js.criterion_scores.get(c.name, 0.0) for js in juror_scores]
            )
            for c in criteria
        ]
        juror_agreement = statistics.mean(crit_agreements) if crit_agreements else 1.0

        custom_score: Optional[float] = None
        if custom_fn is not None:
            custom_score = custom_fn(juror_scores, criteria)

        return ScoredMetrics(
            weighted_mean=weighted_mean,
            mean=mean,
            median=median,
            min_score=min_score,
            max_score=max_score,
            harmonic_mean=harmonic_mean,
            weakest_link=weakest_link,
            juror_agreement=juror_agreement,
            custom=custom_score,
        )

    @classmethod
    def compute_consistency(
        cls, trial_composite_scores: List[float]
    ) -> ConsistencyResult:
        n = len(trial_composite_scores)
        if n < 2:
            raise ValueError(
                "compute_consistency requires at least 2 trial scores; "
                f"got {n}. Use num_trials > 1 in JuryConfig."
            )
        score_std = statistics.stdev(trial_composite_scores)
        score_mean = statistics.mean(trial_composite_scores)
        score_min = min(trial_composite_scores)
        score_max = max(trial_composite_scores)

        if score_std < 0.1:
            interpretation = (
                f"low variance (std={score_std:.2f}) — agent responds consistently"
            )
        elif score_std < 0.3:
            interpretation = (
                f"moderate variance (std={score_std:.2f}) — agent responses vary "
                "noticeably; consider reviewing temperature settings"
            )
        else:
            interpretation = (
                f"high variance (std={score_std:.2f}) — agent responses are "
                "unpredictable; review temperature or prompt stability"
            )

        return ConsistencyResult(
            num_trials=n,
            trial_composite_scores=trial_composite_scores,
            score_std=score_std,
            score_mean=score_mean,
            score_min=score_min,
            score_max=score_max,
            interpretation=interpretation,
        )
