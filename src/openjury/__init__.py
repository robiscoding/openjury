from typing import Any

from openjury.config import (
    AgentResponse,
    CriterionConfig,
    JurorConfig,
    JurorProvider,
    JuryConfig,
    LLMProviderConfig,
    VotingCriteria,
)
from openjury.endpoint_fetcher import (
    AgentEndpoint,
    fetch_agent_response,
    fetch_response,
)
from openjury.env import ConfigurationError
from openjury.errors import (
    EndpointErrorCode,
    EndpointFetchError,
    EvaluationErrorCode,
    InitializationErrorCode,
    JurorErrorCode,
    JurorException,
    OpenJuryError,
    OpenJuryEvaluationError,
    OpenJuryInitializationError,
)
from openjury.execution import (
    EvaluationItem,
    ExecutionOptions,
    FetchMetadata,
    FetchResult,
    ItemEvalResult,
    JurorFailure,
    ProgressEvent,
    ProgressEventType,
    ScoringResult,
)
from openjury.juror import Juror
from openjury.jury_engine import OpenJury
from openjury.output_format import (
    AgentEvalResult,
    CriterionEvaluation,
    ResultFormatter,
    TrialResult,
    juror_score_to_dict,
    serialize_eval_result,
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
    "JurorProvider",
    "LLMProviderConfig",
    "CriterionConfig",
    "AgentResponse",
    "VotingCriteria",
    # Errors
    "ConfigurationError",
    "OpenJuryError",
    "EndpointFetchError",
    "EndpointErrorCode",
    "JurorException",
    "JurorErrorCode",
    "OpenJuryEvaluationError",
    "OpenJuryInitializationError",
    "EvaluationErrorCode",
    "InitializationErrorCode",
    # Execution
    "ExecutionOptions",
    "ProgressEvent",
    "ProgressEventType",
    "FetchResult",
    "FetchMetadata",
    "EvaluationItem",
    "ItemEvalResult",
    "ScoringResult",
    "JurorFailure",
    # Endpoint fetching
    "AgentEndpoint",
    "fetch_agent_response",
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
    "serialize_eval_result",
    "juror_score_to_dict",
    # CLI (lazy)
    "cli_app",
]


def __getattr__(name: str) -> Any:
    if name == "cli_app":
        from openjury.cli import cli_app as cli

        return cli
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
