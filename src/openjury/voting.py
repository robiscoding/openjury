import statistics
from collections import Counter
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel

from openjury.config import VotingMethod


class VotingResult(BaseModel):
    winner: str
    vote_counts: Optional[Dict[str, int]] = None
    method: VotingMethod
    average_scores: Optional[Dict[str, float]] = None
    weighted_scores: Optional[Dict[str, float]] = None
    ranked_scores: Optional[Dict[str, float]] = None
    consensus_scores: Optional[Dict[str, float]] = None
    custom_scores: Optional[Dict[str, float]] = None
    custom_data: Optional[Dict[str, Any]] = None


class JurorEvaluation:
    def __init__(
        self,
        juror_name: str,
        response_scores: Dict[str, Dict[str, float]],
        juror_weight: float = 1.0,
    ):
        self.juror_name = juror_name
        self.response_scores = response_scores
        self.juror_weight = juror_weight


class VotingAggregator:
    _custom_functions: Dict[str, Callable[[List[JurorEvaluation]], VotingResult]] = {}

    @staticmethod
    def majority_vote(evaluations: List[JurorEvaluation]) -> VotingResult:
        if not evaluations:
            raise ValueError("No evaluations provided")
        response_ids = set()
        for evaluation in evaluations:
            response_ids.update(evaluation.response_scores.keys())
        response_ids = list(response_ids)
        if not response_ids:
            raise ValueError("No responses found in evaluations")
        juror_votes = []
        for evaluation in evaluations:
            response_totals = {}
            for response_id in response_ids:
                if response_id in evaluation.response_scores:
                    total_score = sum(evaluation.response_scores[response_id].values())
                    response_totals[response_id] = total_score
                else:
                    response_totals[response_id] = 0
            winner = max(response_totals.items(), key=lambda x: x[1])[0]
            juror_votes.append(winner)
        vote_counts = Counter(juror_votes)
        winner = vote_counts.most_common(1)[0][0]

        return VotingResult(
            winner=winner, vote_counts=dict(vote_counts), method=VotingMethod.MAJORITY
        )

    @staticmethod
    def average_vote(evaluations: List[JurorEvaluation]) -> VotingResult:
        if not evaluations:
            raise ValueError("No evaluations provided")
        response_ids = set()
        for evaluation in evaluations:
            response_ids.update(evaluation.response_scores.keys())
        response_ids = list(response_ids)

        if not response_ids:
            raise ValueError("No responses found in evaluations")

        response_averages = {}
        for response_id in response_ids:
            all_scores = []
            for evaluation in evaluations:
                if response_id in evaluation.response_scores:
                    total_score = sum(evaluation.response_scores[response_id].values())
                    all_scores.append(total_score)
                else:
                    all_scores.append(0)
            response_averages[response_id] = statistics.mean(all_scores)
        winner = max(response_averages.items(), key=lambda x: x[1])[0]

        return VotingResult(
            winner=winner, method=VotingMethod.AVERAGE, average_scores=response_averages
        )

    @staticmethod
    def weighted_vote(evaluations: List[JurorEvaluation]) -> VotingResult:

        if not evaluations:
            raise ValueError("No evaluations provided")

        response_ids = set()
        for evaluation in evaluations:
            response_ids.update(evaluation.response_scores.keys())

        response_ids = list(response_ids)
        if not response_ids:
            raise ValueError("No responses found in evaluations")

        response_weighted_scores = {}
        total_weight = sum(evaluation.juror_weight for evaluation in evaluations)
        for response_id in response_ids:
            weighted_score = 0
            for evaluation in evaluations:
                if response_id in evaluation.response_scores:
                    total_score = sum(evaluation.response_scores[response_id].values())
                    weighted_score += total_score * evaluation.juror_weight
            response_weighted_scores[response_id] = (
                weighted_score / total_weight if total_weight > 0 else 0
            )

        winner = max(response_weighted_scores.items(), key=lambda x: x[1])[0]

        return VotingResult(
            winner=winner,
            method=VotingMethod.WEIGHTED,
            weighted_scores=response_weighted_scores,
        )

    @staticmethod
    def ranked_vote(evaluations: List[JurorEvaluation]) -> VotingResult:
        if not evaluations:
            raise ValueError("No evaluations provided")
        response_ids = set()
        for evaluation in evaluations:
            response_ids.update(evaluation.response_scores.keys())

        response_ids = list(response_ids)
        if not response_ids:
            raise ValueError("No responses found in evaluations")

        response_ranks = {}
        for response_id in response_ids:
            all_scores = []
            for evaluation in evaluations:
                if response_id in evaluation.response_scores:
                    total_score = sum(evaluation.response_scores[response_id].values())
                    all_scores.append(total_score)
                else:
                    all_scores.append(0)
            response_ranks[response_id] = statistics.mean(all_scores)
        winner = max(response_ranks.items(), key=lambda x: x[1])[0]
        return VotingResult(
            winner=winner, method=VotingMethod.RANKED, ranked_scores=response_ranks
        )

    @staticmethod
    def consensus_vote(evaluations: List[JurorEvaluation]) -> VotingResult:
        if not evaluations:
            raise ValueError("No evaluations provided")
        response_ids = set()
        for evaluation in evaluations:
            response_ids.update(evaluation.response_scores.keys())

        response_ids = list(response_ids)
        if not response_ids:
            raise ValueError("No responses found in evaluations")

        response_consensus = {}
        for response_id in response_ids:
            all_scores = []
            for evaluation in evaluations:
                if response_id in evaluation.response_scores:
                    total_score = sum(evaluation.response_scores[response_id].values())
                    all_scores.append(total_score)
                else:
                    all_scores.append(0)
            response_consensus[response_id] = statistics.mean(all_scores)
        winner = max(response_consensus.items(), key=lambda x: x[1])[0]
        return VotingResult(
            winner=winner,
            method=VotingMethod.CONSENSUS,
            consensus_scores=response_consensus,
        )

    @classmethod
    def register_custom_function(
        cls, name: str, function: Callable[[List[JurorEvaluation]], VotingResult]
    ) -> None:
        cls._custom_functions[name] = function

    @classmethod
    def unregister_custom_function(cls, name: str) -> None:
        cls._custom_functions.pop(name, None)

    @classmethod
    def get_custom_functions(cls) -> List[str]:
        return list(cls._custom_functions.keys())

    @classmethod
    def custom_vote(
        cls, evaluations: List[JurorEvaluation], function_name: str
    ) -> VotingResult:
        if function_name not in cls._custom_functions:
            raise ValueError(f"Custom function '{function_name}' not registered")

        function = cls._custom_functions[function_name]
        result = function(evaluations)

        if not isinstance(result, VotingResult):
            raise ValueError(
                f"Custom function '{function_name}' must return a VotingResult object"
            )

        return result

    @classmethod
    def aggregate(
        cls,
        evaluations: List[JurorEvaluation],
        method: VotingMethod,
        custom_function_name: Optional[str] = None,
    ) -> VotingResult:
        if method == VotingMethod.MAJORITY:
            return cls.majority_vote(evaluations)
        elif method == VotingMethod.AVERAGE:
            return cls.average_vote(evaluations)
        elif method == VotingMethod.WEIGHTED:
            return cls.weighted_vote(evaluations)
        elif method == VotingMethod.RANKED:
            return cls.ranked_vote(evaluations)
        elif method == VotingMethod.CONSENSUS:
            return cls.consensus_vote(evaluations)
        elif method == VotingMethod.CUSTOM:
            if not custom_function_name:
                raise ValueError(
                    "custom_function_name required for CUSTOM voting method"
                )
            return cls.custom_vote(evaluations, custom_function_name)
