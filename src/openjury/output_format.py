from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from openjury.config import JuryConfig
from openjury.voting import JurorEvaluation, VotingMethod, VotingResult


class CriterionScore(BaseModel):
    score: float
    explanation: str
    max_score: int


class ResponseEvaluation(BaseModel):
    response_id: str
    response_text: str
    scores: Dict[str, CriterionScore]
    total_score: float
    average_score: float
    overall_comment: Optional[str] = None


class JurorVerdict(BaseModel):
    juror_name: str
    juror_weight: float
    evaluations: List[ResponseEvaluation]
    timestamp: datetime


class FinalVerdict(BaseModel):
    winner: str
    winner_margin: Optional[float] = None
    voting_method: str
    voting_details: Dict[str, Any]
    confidence: Optional[float] = None


class Verdict(BaseModel):
    jury_name: str
    jury_description: Optional[str]
    original_prompt: str
    timestamp: datetime = datetime.now()
    responses: Dict[str, str]
    juror_verdicts: List[JurorVerdict]
    final_verdict: FinalVerdict
    summary: Dict[str, Any]


class VerdictFormatter:
    @staticmethod
    def format_juror_evaluation(
        evaluation: JurorEvaluation,
        responses: Dict[str, str],
        criteria_configs: Dict[str, Any],
        explanations: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> JurorVerdict:
        response_evals = []
        for response_id, response_text in responses.items():
            if response_id in evaluation.response_scores:
                criterion_scores = {}
                total_score = 0
                count = 0

                for criterion_name, score in evaluation.response_scores[
                    response_id
                ].items():
                    max_score = criteria_configs.get(criterion_name, {}).get(
                        "max_score", 5
                    )
                    explanation = ""

                    if explanations and response_id in explanations:
                        explanation = explanations[response_id].get(criterion_name, "")

                    criterion_scores[criterion_name] = CriterionScore(
                        score=score, explanation=explanation, max_score=max_score
                    )
                    total_score += score
                    count += 1

                avg_score = total_score / count if count > 0 else 0

                response_evals.append(
                    ResponseEvaluation(
                        response_id=response_id,
                        response_text=response_text,
                        scores=criterion_scores,
                        total_score=total_score,
                        average_score=avg_score,
                    )
                )

        return JurorVerdict(
            juror_name=evaluation.juror_name,
            juror_weight=evaluation.juror_weight,
            evaluations=response_evals,
            timestamp=datetime.now(),
        )

    @staticmethod
    def calculate_confidence(
        voting_result: VotingResult, juror_verdicts: List[JurorVerdict]
    ) -> float:
        if voting_result.method == VotingMethod.MAJORITY:
            vote_counts = voting_result.vote_counts
            total_votes = sum(vote_counts.values())
            winner_votes = vote_counts.get(voting_result.winner, 0)
            return winner_votes / total_votes if total_votes > 0 else 0.0

        elif voting_result.method == VotingMethod.AVERAGE:
            scores = voting_result.average_scores
            if len(scores) < 2:
                return 1.0
            sorted_scores = sorted(scores.values(), reverse=True)
            winner_score = sorted_scores[0]
            runner_up_score = sorted_scores[1] if len(sorted_scores) > 1 else 0
            max_possible_gap = winner_score
            actual_gap = winner_score - runner_up_score
            return (
                min(actual_gap / max_possible_gap, 1.0) if max_possible_gap > 0 else 1.0
            )

        elif voting_result.method == VotingMethod.WEIGHTED:
            scores = voting_result.weighted_scores
            if len(scores) < 2:
                return 1.0

            sorted_scores = sorted(scores.values(), reverse=True)
            winner_score = sorted_scores[0]
            runner_up_score = sorted_scores[1] if len(sorted_scores) > 1 else 0

            # Normalize confidence based on score gap
            max_possible_gap = winner_score
            actual_gap = winner_score - runner_up_score
            return (
                min(actual_gap / max_possible_gap, 1.0) if max_possible_gap > 0 else 1.0
            )

        elif voting_result.method == VotingMethod.RANKED:
            scores = voting_result.ranked_scores
            if len(scores) < 2:
                return 1.0

            sorted_scores = sorted(scores.values(), reverse=True)
            winner_score = sorted_scores[0]
            runner_up_score = sorted_scores[1] if len(sorted_scores) > 1 else 0

            max_possible_gap = winner_score
            actual_gap = winner_score - runner_up_score
            return (
                min(actual_gap / max_possible_gap, 1.0) if max_possible_gap > 0 else 1.0
            )

        elif voting_result.method == VotingMethod.CONSENSUS:
            scores = voting_result.consensus_scores
            if len(scores) < 2:
                return 1.0

            sorted_scores = sorted(scores.values(), reverse=True)
            winner_score = sorted_scores[0]
            runner_up_score = sorted_scores[1] if len(sorted_scores) > 1 else 0

            max_possible_gap = winner_score
            actual_gap = winner_score - runner_up_score
            return (
                min(actual_gap / max_possible_gap, 1.0) if max_possible_gap > 0 else 1.0
            )

        elif voting_result.method == VotingMethod.CUSTOM:
            scores = voting_result.custom_scores
            if scores and len(scores) >= 2:
                sorted_scores = sorted(scores.values(), reverse=True)
                winner_score = sorted_scores[0]
                runner_up_score = sorted_scores[1]
                max_possible_gap = winner_score
                actual_gap = winner_score - runner_up_score
                return (
                    min(actual_gap / max_possible_gap, 1.0)
                    if max_possible_gap > 0
                    else 1.0
                )
            else:
                return 0.75

        else:
            raise ValueError(f"Unknown voting method: {voting_result.method}")

    @classmethod
    def create_verdict(
        cls,
        jury_config: JuryConfig,
        original_prompt: str,
        responses: Dict[str, str],
        juror_evaluations: List[JurorEvaluation],
        voting_result: VotingResult,
        explanations: Optional[Dict[str, Dict[str, Dict[str, str]]]] = None,
    ) -> Verdict:
        criteria_configs = {
            criterion.name: {
                "max_score": criterion.max_score,
                "weight": criterion.weight,
            }
            for criterion in jury_config.criteria
        }

        juror_verdicts = []
        for evaluation in juror_evaluations:
            juror_explanations = (
                explanations.get(evaluation.juror_name) if explanations else None
            )
            verdict = cls.format_juror_evaluation(
                evaluation, responses, criteria_configs, juror_explanations
            )
            juror_verdicts.append(verdict)

        confidence = cls.calculate_confidence(voting_result, juror_verdicts)
        winner_margin = None
        if voting_result.method == VotingMethod.AVERAGE:
            scores = voting_result.average_scores
            if len(scores) >= 2:
                sorted_scores = sorted(scores.values(), reverse=True)
                winner_margin = sorted_scores[0] - sorted_scores[1]
        elif voting_result.method == VotingMethod.WEIGHTED:
            scores = voting_result.weighted_scores
            if len(scores) >= 2:
                sorted_scores = sorted(scores.values(), reverse=True)
                winner_margin = sorted_scores[0] - sorted_scores[1]
        elif voting_result.method == VotingMethod.RANKED:
            scores = voting_result.ranked_scores
            if len(scores) >= 2:
                sorted_scores = sorted(scores.values(), reverse=True)
                winner_margin = sorted_scores[0] - sorted_scores[1]
        elif voting_result.method == VotingMethod.CONSENSUS:
            scores = voting_result.consensus_scores
            if len(scores) >= 2:
                sorted_scores = sorted(scores.values(), reverse=True)
                winner_margin = sorted_scores[0] - sorted_scores[1]
        elif voting_result.method == VotingMethod.CUSTOM:
            scores = voting_result.custom_scores
            if scores and len(scores) >= 2:
                sorted_scores = sorted(scores.values(), reverse=True)
                winner_margin = sorted_scores[0] - sorted_scores[1]

        final_verdict = FinalVerdict(
            winner=voting_result.winner,
            winner_margin=winner_margin,
            voting_method=voting_result.method,
            voting_details=voting_result.model_dump(),
            confidence=confidence,
        )

        summary = {
            "total_jurors": len(juror_evaluations),
            "total_responses": len(responses),
            "total_criteria": len(jury_config.criteria),
            "voting_method": voting_result.method,
            "confidence": confidence,
            "unanimous": confidence == 1.0,
        }

        return Verdict(
            jury_name=jury_config.name,
            jury_description=jury_config.description,
            original_prompt=original_prompt,
            responses=responses,
            juror_verdicts=juror_verdicts,
            final_verdict=final_verdict,
            summary=summary,
        )
