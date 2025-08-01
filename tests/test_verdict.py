import pytest

from openjury import JurorEvaluation, Verdict, VotingMethod
from openjury.output_format import VerdictFormatter
from openjury.voting import VotingAggregator, VotingResult


class TestVerdictFormatter:
    def test_create_verdict(self, sample_jury_config):
        evaluations = [
            JurorEvaluation(
                juror_name="TestJuror",
                response_scores={
                    "response_1": {"factuality": 5.0, "clarity": 4.0},
                    "response_2": {"factuality": 3.0, "clarity": 3.0},
                },
                juror_weight=1.0,
            )
        ]

        voting_result = VotingAggregator.majority_vote(evaluations)
        responses = {"response_1": "First response", "response_2": "Second response"}
        explanations = {
            "TestJuror": {
                "response_1": {"factuality": "Good facts", "clarity": "Clear"},
                "response_2": {"factuality": "Poor facts", "clarity": "Unclear"},
            }
        }

        verdict = VerdictFormatter.create_verdict(
            jury_config=sample_jury_config,
            original_prompt="Test prompt",
            responses=responses,
            juror_evaluations=evaluations,
            voting_result=voting_result,
            explanations=explanations,
        )

        assert isinstance(verdict, Verdict)
        assert verdict.jury_name == "Test Jury"
        assert verdict.original_prompt == "Test prompt"
        assert verdict.final_verdict.winner == "response_1"
        assert len(verdict.juror_verdicts) == 1
        assert verdict.summary["total_jurors"] == 1
        assert verdict.summary["total_responses"] == 2

    def test_calculate_confidence_majority(self):
        voting_result = VotingResult(
            winner="response_1",
            method=VotingMethod.MAJORITY,
            vote_counts={"response_1": 3, "response_2": 1},
        )

        confidence = VerdictFormatter.calculate_confidence(voting_result, [])
        # 3 responses, 4 points possible = 0.75
        assert confidence == 0.75

    def test_calculate_confidence_average(self):
        voting_result = VotingResult(
            winner="response_1",
            method=VotingMethod.AVERAGE,
            average_scores={"response_1": 8.0, "response_2": 6.0},
        )

        confidence = VerdictFormatter.calculate_confidence(voting_result, [])
        # 8 - 6 = 2, 8 points possible = 0.25
        assert confidence == 0.25
