import pytest

from openjury import JurorEvaluation, VotingMethod
from openjury.voting import VotingAggregator, VotingResult


class TestNewVotingMethods:
    def test_custom_vote_registration(self):
        def custom_function(evaluations):
            from openjury.voting import VotingResult

            return VotingResult(
                winner="response_1",
                method=VotingMethod.CUSTOM,
                custom_scores={"response_1": 10.0, "response_2": 5.0},
            )

        VotingAggregator.register_custom_function("test_custom", custom_function)
        assert "test_custom" in VotingAggregator.get_custom_functions()

        evaluations = [
            JurorEvaluation(
                juror_name="Juror1",
                response_scores={
                    "response_1": {"factuality": 3.0},
                    "response_2": {"factuality": 5.0},
                },
                juror_weight=1.0,
            )
        ]

        result = VotingAggregator.custom_vote(evaluations, "test_custom")
        assert result.method == VotingMethod.CUSTOM
        assert result.winner == "response_1"

        VotingAggregator.unregister_custom_function("test_custom")
        assert "test_custom" not in VotingAggregator.get_custom_functions()


class TestCustomVotingIntegration:
    def test_custom_voting_config_loading(self):
        """Test that custom voting configurations load correctly."""
        config_data = {
            "name": "Custom Test Jury",
            "description": "A test jury with custom voting",
            "criteria": [
                {
                    "name": "factuality",
                    "description": "How accurate is the response?",
                    "weight": 1.0,
                    "max_score": 5,
                }
            ],
            "jurors": [
                {
                    "name": "Test Juror",
                    "model_name": "gpt-3.5-turbo",
                    "weight": 1.0,
                }
            ],
            "voting_method": "custom",
            "custom_voting_function": "test_custom_method",
        }

        class TestCustomVoting:
            @staticmethod
            def test_custom_method(evaluations):
                return VotingResult(
                    winner="response_1",
                    method=VotingMethod.CUSTOM,
                    custom_scores={"response_1": 5.0, "response_2": 3.0},
                )

        from openjury import JuryConfig

        config = JuryConfig.from_dict(config_data, TestCustomVoting)

        assert config.voting_method == VotingMethod.CUSTOM
        assert config.custom_voting_function == "test_custom_method"
        assert "test_custom_method" in VotingAggregator.get_custom_functions()

        VotingAggregator.unregister_custom_function("test_custom_method")

    def test_custom_voting_execution(self):
        """Test that custom voting methods execute correctly."""

        class TestCustomVoting:
            @staticmethod
            def simple_winner(evaluations):
                return VotingResult(
                    winner="response_1",
                    method=VotingMethod.CUSTOM,
                    custom_scores={"response_1": 10.0, "response_2": 5.0},
                    custom_data={"method_name": "simple_winner"},
                )

        VotingAggregator.register_custom_function(
            "simple_winner", TestCustomVoting.simple_winner
        )

        evaluations = [
            JurorEvaluation(
                juror_name="TestJuror",
                response_scores={
                    "response_1": {"factuality": 3.0},
                    "response_2": {"factuality": 5.0},
                },
                juror_weight=1.0,
            )
        ]

        result = VotingAggregator.aggregate(
            evaluations, VotingMethod.CUSTOM, custom_function_name="simple_winner"
        )

        assert result.method == VotingMethod.CUSTOM
        assert result.winner == "response_1"
        assert result.custom_scores == {"response_1": 10.0, "response_2": 5.0}
        assert result.custom_data["method_name"] == "simple_winner"

        VotingAggregator.unregister_custom_function("simple_winner")

    def test_custom_voting_error_handling(self):
        """Test error handling for custom voting methods."""

        class BadCustomVoting:
            @staticmethod
            def bad_method(evaluations):
                return {"winner": "response_1"}

        VotingAggregator.register_custom_function(
            "bad_method", BadCustomVoting.bad_method
        )

        evaluations = [
            JurorEvaluation(
                juror_name="TestJuror",
                response_scores={"response_1": {"factuality": 5.0}},
                juror_weight=1.0,
            )
        ]

        with pytest.raises(ValueError, match="must return a VotingResult object"):
            VotingAggregator.aggregate(
                evaluations, VotingMethod.CUSTOM, custom_function_name="bad_method"
            )

        VotingAggregator.unregister_custom_function("bad_method")

    def test_config_custom_voting_without_class_fails(self):
        """Test that custom voting config without a custom class fails."""
        config_data = {
            "name": "Custom Test Jury",
            "criteria": [
                {
                    "name": "factuality",
                    "description": "Test",
                    "weight": 1.0,
                    "max_score": 5,
                }
            ],
            "jurors": [
                {"name": "Test Juror", "model_name": "gpt-3.5-turbo", "weight": 1.0}
            ],
            "voting_method": "custom",
            "custom_voting_function": "test_method",
        }

        from openjury import JuryConfig

        with pytest.raises(
            ValueError,
            match="Custom voting method selected but no custom voting class provided",
        ):
            JuryConfig.from_dict(config_data, None)
