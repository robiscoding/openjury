from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from openjury.config import AssertionType
from openjury.execution import FetchMetadata, JurorFailure
from openjury.scoring import ConsistencyResult, JurorScore, ScoredMetrics


def juror_score_to_dict(juror_score: JurorScore) -> Dict[str, Any]:
    return {
        "juror_name": juror_score.juror_name,
        "juror_weight": juror_score.juror_weight,
        "criterion_scores": juror_score.criterion_scores,
        "criterion_explanations": juror_score.criterion_explanations,
    }


def serialize_eval_result(result: "AgentEvalResult") -> Dict[str, Any]:
    """Serialize AgentEvalResult to a JSON-compatible dict."""
    import dataclasses

    raw = result.model_dump(mode="json")
    raw["juror_scores"] = [juror_score_to_dict(js) for js in result.juror_scores]
    for i, trial in enumerate(result.trial_results):
        raw["trial_results"][i]["juror_scores"] = [
            juror_score_to_dict(js) for js in trial.juror_scores
        ]
    if result.fetch_metadata is not None:
        raw["fetch_metadata"] = dataclasses.asdict(result.fetch_metadata)
    if result.juror_failures:
        raw["juror_failures"] = [
            dataclasses.asdict(failure) for failure in result.juror_failures
        ]
    return raw


class CriterionEvaluation(BaseModel):
    """Aggregated evaluation result for a single criterion across all jurors."""

    weighted_mean_score: float
    min_juror_score: float
    max_juror_score: float
    juror_agreement: float
    weight: float
    explanations: Dict[str, str] = Field(default_factory=dict)


class AssertionResult(BaseModel):
    """Result of one deterministic assertion against an agent response."""

    name: str
    type: AssertionType
    passed: bool
    expected: Union[str, List[str], int]
    detail: str
    required: bool = True
    weight: float = Field(default=1.0, gt=0.0)


class TrialResult(BaseModel):
    """Scores for one trial (one agent response to the prompt)."""

    trial_number: int
    response_text: str
    scored_metrics: ScoredMetrics
    criteria_evaluations: Dict[str, CriterionEvaluation] = Field(default_factory=dict)
    juror_scores: List[JurorScore] = Field(default_factory=list)
    assertion_results: List[AssertionResult] = Field(default_factory=list)
    assertion_score: float = 1.0
    assertions_passed: bool = True

    model_config = {"arbitrary_types_allowed": True}


class AgentEvalResult(BaseModel):
    """Primary output of an agent evaluation. Quality score always comes from trial 1.
    If num_trials > 1, consistency_result is populated with reliability metrics."""

    jury_name: str
    prompt: str
    endpoint_alias: Optional[str] = None
    model_name: Optional[str] = None
    score_min: int = 1
    score_scale: int

    composite_score: float
    normalized_composite_score: float
    scored_metrics: ScoredMetrics
    criteria_evaluations: Dict[str, CriterionEvaluation] = Field(default_factory=dict)
    juror_scores: List[JurorScore] = Field(default_factory=list)
    assertion_results: List[AssertionResult] = Field(default_factory=list)
    assertion_score: float = 1.0
    assertions_passed: bool = True
    passed: bool = True

    consistency_result: Optional[ConsistencyResult] = None
    trial_results: List[TrialResult] = Field(default_factory=list)

    fetch_metadata: Optional[FetchMetadata] = None
    juror_failures: List[JurorFailure] = Field(default_factory=list)

    timestamp: datetime = Field(default_factory=datetime.now)

    model_config = {"arbitrary_types_allowed": True}


class ResultFormatter:
    @staticmethod
    def format_result(result: AgentEvalResult) -> str:
        scale = result.score_scale
        lines: List[str] = [
            f"╔══ Quality Evaluation  (scale: 1–{scale}) ══",
            f"  Jury:              {result.jury_name}",
            f"  Endpoint:          {result.endpoint_alias or 'n/a'}",
            f"  Model:             {result.model_name or 'n/a'}",
            "",
            f"  composite_score:   {result.composite_score:.2f} / {scale}  "
            f"({result.normalized_composite_score:.3f} normalized)",
            f"  assertion_score:   {result.assertion_score:.3f}",
            f"  assertions_passed: {str(result.assertions_passed).lower()}",
            f"  passed:             {str(result.passed).lower()}",
            "",
            "  Scoring Metrics:",
        ]

        m = result.scored_metrics
        metrics_rows = [
            ("weighted_mean", m.weighted_mean),
            ("mean", m.mean),
            ("median", m.median),
            ("min_score", m.min_score),
            ("max_score", m.max_score),
            ("harmonic_mean", m.harmonic_mean),
            ("weakest_link", m.weakest_link),
            ("juror_agreement (0–1)", m.juror_agreement),
        ]
        if m.custom is not None:
            metrics_rows.append(("custom", m.custom))

        for label, value in metrics_rows:
            lines.append(f"    {label:<28} {value:.3f}")

        if result.criteria_evaluations:
            lines.append("")
            lines.append("  Criteria Breakdown:")
            for cname, ce in result.criteria_evaluations.items():
                lines.append(
                    f"    {cname} (weight {ce.weight:.1f}):  "
                    f"{ce.weighted_mean_score:.2f}  "
                    f"[agreement: {ce.juror_agreement:.2f}  "
                    f"min: {ce.min_juror_score:.1f}  "
                    f"max: {ce.max_juror_score:.1f}]"
                )
                for juror_name, expl in ce.explanations.items():
                    snippet = expl[:100].replace("\n", " ")
                    lines.append(f'      {juror_name}: "{snippet}"')

        if result.assertion_results:
            lines.append("")
            lines.append("  Assertions:")
            for assertion in result.assertion_results:
                status = "PASS" if assertion.passed else "FAIL"
                policy = "required" if assertion.required else "optional"
                lines.append(
                    f"    [{status}] {assertion.name} "
                    f"({policy}, weight {assertion.weight:g}): {assertion.detail}"
                )

        if result.consistency_result is not None:
            cr = result.consistency_result
            lines.append("")
            lines.append("  ── Consistency Audit ──")
            lines.append(f"  trials:      {cr.num_trials}")
            lines.append(
                f"  score_std:   {cr.score_std:.3f}  "
                f"(mean: {cr.score_mean:.2f}  "
                f"min: {cr.score_min:.2f}  "
                f"max: {cr.score_max:.2f})"
            )
            scores_str = ", ".join(f"{s:.2f}" for s in cr.trial_composite_scores)
            lines.append(f"  trial scores: [{scores_str}]")
            lines.append(f"  {cr.interpretation}")

        lines.append("╚══")
        return "\n".join(lines)
