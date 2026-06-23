from typing import Any

from openjury.config import (
    AgentResponse,
    CriterionConfig,
    JurorConfig,
    JuryConfig,
    VotingCriteria,
)
from openjury.endpoint_fetcher import AgentEndpoint, EndpointFetchError
from openjury.juror import Juror
from openjury.jury_engine import OpenJury
from openjury.output_format import (
    AgentEvalResult,
    CriterionEvaluation,
    ResultFormatter,
    TrialResult,
)
from openjury.scoring import (
    ConsistencyResult,
    JurorScore,
    ScoreAggregator,
    ScoredMetrics,
    ScoringFunction,
)

__version__ = "0.2.0"
__all__ = [
    # Core engine
    "OpenJury",
    "Juror",
    # Config models
    "JuryConfig",
    "JurorConfig",
    "CriterionConfig",
    "AgentResponse",
    "VotingCriteria",
    # Endpoint fetching
    "AgentEndpoint",
    "EndpointFetchError",
    # Scoring
    "ScoreAggregator",
    "ScoredMetrics",
    "JurorScore",
    "ScoringFunction",
    "ConsistencyResult",
    # Output
    "AgentEvalResult",
    "CriterionEvaluation",
    "TrialResult",
    "ResultFormatter",
    # CLI (lazy)
    "cli_app",
]


def __getattr__(name: str) -> Any:
    if name == "cli_app":
        from openjury.cli import cli_app as cli

        return cli
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
