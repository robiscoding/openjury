#!/usr/bin/env python3
"""
OpenJury Custom Voting Methods Example

This example demonstrates how to implement and use custom voting algorithms
with OpenJury. It shows several different voting strategies and how to
register them for use in jury configurations.

Custom voting methods allow you to implement specialized decision-making logic
beyond the built-in voting methods (majority, average, weighted, ranked, consensus).

Usage:
    export OPENROUTER_API_KEY="your-api-key-here"
    python examples/custom_voting_method/custom_voting.py

This will:
1. Register custom voting methods from the CustomVotingMethods class
2. Test each method with sample responses
3. Compare results across different algorithms

Key Features:
- unanimous_priority: Heavily weights unanimous decisions for high confidence
- confidence_weighted: Considers juror confidence based on score spread
- margin_of_victory: Uses margin between top responses for confidence

Custom voting methods must:
1. Accept a List[JurorEvaluation] parameter
2. Return a VotingResult object with winner, method, and optional custom data
3. Be defined as static methods in a custom class
4. Be passed to JuryConfig.from_json_file() for automatic registration
"""

import logging
import os
import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from openjury import JurorEvaluation, JuryConfig, OpenJury, ResponseCandidate
from openjury.voting import VotingMethod, VotingResult

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CustomVotingMethods:

    @staticmethod
    def unanimous_priority(evaluations: List[JurorEvaluation]) -> VotingResult:
        """
        Custom voting that heavily weights unanimous decisions.
        If all jurors agree on the winner, confidence is boosted.
        """
        response_scores = {}
        response_votes = {}
        max_score = 10

        for evaluation in evaluations:
            for response_id, scores in evaluation.response_scores.items():
                if response_id not in response_scores:
                    response_scores[response_id] = []
                    response_votes[response_id] = 0
                total_score = sum(scores.values())
                response_scores[response_id].append(
                    total_score * evaluation.juror_weight
                )

                max_possible = len(scores) * max_score
                if total_score >= (max_possible * 0.6):
                    response_votes[response_id] += 1
        avg_scores = {
            resp_id: sum(scores) / len(scores)
            for resp_id, scores in response_scores.items()
        }
        best_response = max(avg_scores.keys(), key=lambda x: avg_scores[x])
        unanimous = response_votes[best_response] == len(evaluations)
        base_confidence = avg_scores[best_response] / (len(evaluations) * max_score)
        confidence = 0.95 if unanimous else min(base_confidence, 0.85)

        return VotingResult(
            winner=best_response,
            method=VotingMethod.CUSTOM,
            custom_scores=avg_scores,
            vote_counts=response_votes,
            custom_data={
                "unanimous": unanimous,
                "confidence": confidence,
                "method_name": "unanimous_priority",
            },
        )

    @staticmethod
    def confidence_weighted(evaluations: List[JurorEvaluation]) -> VotingResult:
        """
        Voting method that considers how confident each juror seems to be.
        Jurors with more spread in their scores are considered more confident.
        """
        response_scores = {}
        juror_confidence_weights = {}
        max_score = 5
        for evaluation in evaluations:
            scores_list = []
            for response_id, scores in evaluation.response_scores.items():
                total_score = sum(scores.values())
                scores_list.append(total_score)

                if response_id not in response_scores:
                    response_scores[response_id] = []
                response_scores[response_id].append(
                    (total_score, evaluation.juror_name)
                )
            if len(scores_list) > 1:
                score_spread = max(scores_list) - min(scores_list)
                confidence_weight = min(score_spread / 20.0, 1.0)
            else:
                confidence_weight = 0.5

            juror_confidence_weights[evaluation.juror_name] = (
                confidence_weight * evaluation.juror_weight
            )
        weighted_scores = {}
        for response_id, score_data in response_scores.items():
            total_weighted_score = 0
            total_weight = 0
            for score, juror_name in score_data:
                weight = juror_confidence_weights[juror_name]
                total_weighted_score += score * weight
                total_weight += weight
            weighted_scores[response_id] = (
                total_weighted_score / total_weight if total_weight > 0 else 0
            )
        best_response = max(weighted_scores.keys(), key=lambda x: weighted_scores[x])
        confidence = weighted_scores[best_response] / (len(evaluations) * max_score)

        return VotingResult(
            winner=best_response,
            method=VotingMethod.CUSTOM,
            custom_scores=weighted_scores,
            custom_data={
                "confidence": min(confidence, 0.95),
                "juror_confidence_weights": juror_confidence_weights,
                "method_name": "confidence_weighted",
            },
        )

    @staticmethod
    def margin_of_victory(evaluations: List[JurorEvaluation]) -> VotingResult:
        """
        Voting method that considers the margin between first and second place.
        Larger margins result in higher confidence.
        """
        response_scores = {}
        max_score = 5
        for evaluation in evaluations:
            for response_id, scores in evaluation.response_scores.items():
                if response_id not in response_scores:
                    response_scores[response_id] = []

                total_score = sum(scores.values())
                response_scores[response_id].append(
                    total_score * evaluation.juror_weight
                )

        avg_scores = {
            resp_id: sum(scores) / len(scores)
            for resp_id, scores in response_scores.items()
        }

        sorted_responses = sorted(avg_scores.items(), key=lambda x: x[1], reverse=True)
        if len(sorted_responses) < 2:
            return VotingResult(
                winner=sorted_responses[0][0],
                method=VotingMethod.CUSTOM,
                custom_scores=avg_scores,
                custom_data={
                    "confidence": 0.5,
                    "margin": 0,
                    "method_name": "margin_of_victory",
                },
            )

        winner, winner_score = sorted_responses[0]
        _, runner_up_score = sorted_responses[1]
        margin = winner_score - runner_up_score
        max_possible_margin = len(evaluations) * max_score
        confidence = min(0.5 + (margin / max_possible_margin), 0.95)

        return VotingResult(
            winner=winner,
            method=VotingMethod.CUSTOM,
            custom_scores=avg_scores,
            custom_data={
                "confidence": confidence,
                "margin": margin,
                "method_name": "margin_of_victory",
            },
        )


def main():
    assert os.getenv(
        "OPENROUTER_API_KEY"
    ), "OPENROUTER_API_KEY environment variable is required"

    logger.info("🗳️  OpenJury Custom Voting Methods Demo")
    logger.info("=" * 50)

    config = JuryConfig.from_json_file(
        f"{Path(__file__).parent}/config.json", CustomVotingMethods
    )

    prompt = "I'm 35 and just starting to invest. I have $10,000 saved. Should I put it into a high-yield savings account, index funds, or something else? I'm looking for a low-risk option with long-term growth."
    responses = [
        ResponseCandidate(
            id="1",
            model="gpt-4",
            content="Given your age and goal of long-term growth with low risk, index funds are often a great starting point. They offer broad market exposure, relatively low fees, and tend to grow steadily over time. A high-yield savings account is very safe but offers lower returns, typically below inflation. A reasonable approach might be to split your funds — keep 3-6 months of expenses in a high-yield savings account as an emergency fund, and invest the rest in a diversified index fund (like one tracking the S&P 500). This balances safety and growth. As always, it's a good idea to consult with a financial advisor to tailor this to your personal situation.",
        ),
        ResponseCandidate(
            id="2",
            model="claude",
            content="Your preference for low risk and long-term growth aligns well with index funds, particularly those that track large, diversified markets like the S&P 500 or total stock market indexes. These tend to outperform savings accounts over the long term, despite short-term volatility. However, it's wise to assess your emergency savings first. If you don't already have a cash buffer, you may want to keep part of your savings in a high-yield savings account to cover 3-6 months of living expenses. Overall, index funds offer a strong blend of growth potential and relatively low risk if held over many years.",
        ),
        ResponseCandidate(
            id="3",
            model="mixtral",
            content="A high-yield savings account is the safest, but the returns are low. Index funds carry more risk but can give better returns over time. If you want low risk, go with the savings account. If you're okay with some risk for growth, choose index funds.",
        ),
        ResponseCandidate(
            id="4",
            content="If you want the lowest risk, a high-yield savings account keeps your money safe but won't grow much over time. Index funds offer more growth potential but come with market ups and downs. For a balanced approach, you could keep some money in savings for emergencies and put the rest into a broad index fund for long-term growth. Always make sure you're comfortable with the level of risk you choose.",
        ),
        ResponseCandidate(
            id="5",
            content="Great question! For low risk and steady long-term growth, index funds are often recommended because they spread your investment across many companies, reducing risk compared to picking individual stocks. High-yield savings accounts are extremely safe, but their returns may not keep up with inflation over time. Many financial advisors suggest building an emergency fund in a savings account and investing the rest in index funds. Before making a decision, consider your timeline, goals, and how much risk you’re comfortable with.",
        ),
    ]

    voting_methods = ["unanimous_priority", "confidence_weighted", "margin_of_victory"]
    results = {}
    for method in voting_methods:
        logger.info(f"\n🔄 Testing voting method: {method}")
        try:
            config = JuryConfig.from_json_file(
                f"{Path(__file__).parent}/config.json", CustomVotingMethods
            )
            config.custom_voting_function = method
            jury = OpenJury(config)
            verdict = jury.evaluate(prompt=prompt, responses=responses)
            results[method] = {
                "winner": verdict.final_verdict.winner,
                "confidence": verdict.final_verdict.confidence,
                "voting_details": verdict.final_verdict.voting_details,
                "success": True,
            }
            logger.info(f"  ✅ Winner: {verdict.final_verdict.winner}")
            logger.info(f"  📊 Confidence: {verdict.final_verdict.confidence:.2%}")
        except Exception as e:
            logger.error(f"  ❌ Failed: {e}")
            results[method] = {"success": False, "error": str(e)}

    logger.info(f"\n📊 VOTING METHOD COMPARISON")
    logger.info("=" * 50)

    for method, result in results.items():
        if result.get("success", False):
            logger.info(
                f"{method:20} | Winner: {result['winner']:12} | Confidence: {result['confidence']:>6.1%}"
            )
        else:
            logger.error(
                f"{method:20} | FAILED: {result.get('error', 'Unknown error')}"
            )
    successful_results = {k: v for k, v in results.items() if v.get("success", False)}

    if successful_results:
        logger.info(f"\n🔍 ANALYSIS")
        logger.info("-" * 30)
        winner_counts = {}
        for result in successful_results.values():
            winner = result["winner"]
            winner_counts[winner] = winner_counts.get(winner, 0) + 1
        logger.info("Winner consensus:")
        for winner, count in winner_counts.items():
            percentage = (count / len(successful_results)) * 100
            logger.info(
                f"  {winner}: {count}/{len(successful_results)} methods ({percentage:.1f}%)"
            )
        confidences = [result["confidence"] for result in successful_results.values()]
        avg_confidence = sum(confidences) / len(confidences)
        logger.info(f"\nAverage confidence: {avg_confidence:.2%}")
        logger.info(
            f"Confidence range: {min(confidences):.2%} - {max(confidences):.2%}"
        )
    logger.info(f"\n✅ Custom voting methods demo complete!")


if __name__ == "__main__":
    main()
