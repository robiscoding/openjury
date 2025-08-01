import pytest

from openjury import JurorEvaluation, VotingMethod
from openjury.voting import VotingAggregator, VotingResult


class TestVotingAggregator:
    def test_majority_vote(self):
        evaluations = [
            JurorEvaluation(
                juror_name="Juror1",
                response_scores={
                    "response_1": {"factuality": 5.0, "clarity": 4.0},
                    "response_2": {"factuality": 3.0, "clarity": 3.0},
                },
                juror_weight=1.0,
            ),
            JurorEvaluation(
                juror_name="Juror2",
                response_scores={
                    "response_1": {"factuality": 4.0, "clarity": 5.0},
                    "response_2": {"factuality": 2.0, "clarity": 2.0},
                },
                juror_weight=1.0,
            ),
        ]

        result = VotingAggregator.majority_vote(evaluations)

        assert result.winner == "response_1"
        assert result.method == VotingMethod.MAJORITY
        assert result.vote_counts == {"response_1": 2}

    def test_average_vote(self):
        evaluations = [
            JurorEvaluation(
                juror_name="Juror1",
                response_scores={
                    "response_1": {"factuality": 5.0, "clarity": 4.0},
                    "response_2": {"factuality": 3.0, "clarity": 3.0},
                },
                juror_weight=1.0,
            ),
            JurorEvaluation(
                juror_name="Juror2",
                response_scores={
                    "response_1": {"factuality": 3.0, "clarity": 3.0},
                    "response_2": {"factuality": 4.0, "clarity": 4.0},
                },
                juror_weight=1.0,
            ),
        ]

        result = VotingAggregator.average_vote(evaluations)

        assert result.method == VotingMethod.AVERAGE
        assert result.winner == "response_1"
        assert result.average_scores is not None
        assert "response_1" in result.average_scores
        assert "response_2" in result.average_scores

    def test_weighted_vote(self):
        evaluations = [
            JurorEvaluation(
                juror_name="Expert",
                response_scores={
                    "response_1": {"factuality": 5.0, "clarity": 4.0},
                    "response_2": {"factuality": 3.0, "clarity": 3.0},
                },
                juror_weight=2.0,
            ),
            JurorEvaluation(
                juror_name="Novice",
                response_scores={
                    "response_1": {"factuality": 2.0, "clarity": 2.0},
                    "response_2": {"factuality": 5.0, "clarity": 5.0},
                },
                juror_weight=1.0,
            ),
        ]

        result = VotingAggregator.weighted_vote(evaluations)

        assert result.method == VotingMethod.WEIGHTED
        assert result.winner in ["response_1", "response_2"]
        assert result.weighted_scores is not None
        assert "response_1" in result.weighted_scores
        assert "response_2" in result.weighted_scores

    def test_ranked_vote(self):
        evaluations = [
            JurorEvaluation(
                juror_name="Juror1",
                response_scores={
                    "response_1": {"factuality": 5.0, "clarity": 4.0},
                    "response_2": {"factuality": 3.0, "clarity": 3.0},
                },
                juror_weight=1.0,
            ),
            JurorEvaluation(
                juror_name="Juror2",
                response_scores={
                    "response_1": {"factuality": 4.0, "clarity": 5.0},
                    "response_2": {"factuality": 2.0, "clarity": 2.0},
                },
                juror_weight=1.0,
            ),
        ]

        result = VotingAggregator.ranked_vote(evaluations)
        assert result.method == VotingMethod.RANKED
        assert result.winner == "response_1"
        assert result.ranked_scores is not None
        assert "response_1" in result.ranked_scores
        assert "response_2" in result.ranked_scores

    def test_consensus_vote(self):
        evaluations = [
            JurorEvaluation(
                juror_name="Juror1",
                response_scores={
                    "response_1": {"factuality": 5.0, "clarity": 4.0},
                    "response_2": {"factuality": 3.0, "clarity": 3.0},
                },
                juror_weight=1.0,
            ),
            JurorEvaluation(
                juror_name="Juror2",
                response_scores={
                    "response_1": {"factuality": 4.0, "clarity": 5.0},
                    "response_2": {"factuality": 2.0, "clarity": 2.0},
                },
                juror_weight=1.0,
            ),
        ]

        result = VotingAggregator.consensus_vote(evaluations)
        assert result.method == VotingMethod.CONSENSUS
        assert result.winner == "response_1"
        assert result.consensus_scores is not None

    def test_aggregate_with_all_methods(self):
        evaluations = [
            JurorEvaluation(
                juror_name="Juror1",
                response_scores={
                    "response_1": {"factuality": 5.0, "clarity": 4.0},
                    "response_2": {"factuality": 3.0, "clarity": 3.0},
                },
                juror_weight=1.0,
            )
        ]

        for method in [
            VotingMethod.MAJORITY,
            VotingMethod.AVERAGE,
            VotingMethod.WEIGHTED,
            VotingMethod.RANKED,
            VotingMethod.CONSENSUS,
        ]:
            result = VotingAggregator.aggregate(evaluations, method)
            assert result.method == method
            assert result.winner in ["response_1", "response_2"]


def test_end_to_end_mock_evaluation():
    test_evaluations = [
        JurorEvaluation(
            juror_name="TestJuror",
            response_scores={
                "response_1": {"quality": 5.0},
                "response_2": {"quality": 3.0},
            },
            juror_weight=1.0,
        )
    ]

    result = VotingAggregator.aggregate(test_evaluations, VotingMethod.MAJORITY)
    assert result.winner == "response_1"
    assert result.method == VotingMethod.MAJORITY
    assert isinstance(result.vote_counts, dict)
    assert "response_1" in result.vote_counts
