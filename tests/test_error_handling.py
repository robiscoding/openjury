import pytest

from openjury import JurorEvaluation, VotingMethod
from openjury.voting import VotingAggregator


class TestErrorHandling:
    def test_voting_with_empty_evaluations(self):
        with pytest.raises(ValueError, match="No evaluations provided"):
            VotingAggregator.majority_vote([])

        with pytest.raises(ValueError, match="No evaluations provided"):
            VotingAggregator.average_vote([])

        with pytest.raises(ValueError, match="No evaluations provided"):
            VotingAggregator.weighted_vote([])

    def test_voting_with_no_responses(self):
        evaluations = [
            JurorEvaluation(juror_name="Juror1", response_scores={}, juror_weight=1.0)
        ]

        with pytest.raises(ValueError, match="No responses found"):
            VotingAggregator.majority_vote(evaluations)

    def test_custom_vote_with_unregistered_function(self):
        evaluations = [
            JurorEvaluation(
                juror_name="Juror1",
                response_scores={"response_1": {"factuality": 5.0}},
                juror_weight=1.0,
            )
        ]

        with pytest.raises(
            ValueError, match="Custom function 'nonexistent' not registered"
        ):
            VotingAggregator.custom_vote(evaluations, "nonexistent")

    def test_aggregate_with_custom_method_missing_function_name(self):
        evaluations = [
            JurorEvaluation(
                juror_name="Juror1",
                response_scores={"response_1": {"factuality": 5.0}},
                juror_weight=1.0,
            )
        ]

        with pytest.raises(ValueError, match="custom_function_name required"):
            VotingAggregator.aggregate(evaluations, VotingMethod.CUSTOM)
