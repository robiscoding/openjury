from typing import Any

from openjury.assertion_resolution import resolve_item_assertions
from openjury.assertions import evaluate_assertions, score_assertions
from openjury.batch_summary import (
    BatchEvalResult,
    BatchRunSummary,
    CriterionRunSummary,
    ExecutionCoverage,
    JurorRunSummary,
    ScoreBucket,
    ScoreDistribution,
    aggregate_batch_results,
)
from openjury.config import (
    AgentResponse,
    AssertionConfig,
    AssertionPolicyDefaults,
    AssertionProfileConfig,
    AssertionType,
    CriterionConfig,
    DatasetItemConfig,
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
    ErrorStage,
    EvalItemStatus,
    EvaluationItem,
    ExecutionOptions,
    FetchMetadata,
    FetchResult,
    ItemEvalResult,
    JurorFailure,
    ProgressEvent,
    ProgressEventType,
    ScoringResult,
    classify_item_error,
)
from openjury.juror import Juror
from openjury.jury_engine import OpenJury
from openjury.output_format import (
    AgentEvalResult,
    AssertionResult,
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

__version__ = "0.5.0"
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
    "AssertionConfig",
    "AssertionProfileConfig",
    "AssertionPolicyDefaults",
    "DatasetItemConfig",
    "AssertionType",
    "resolve_item_assertions",
    "evaluate_assertions",
    "score_assertions",
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
    "EvalItemStatus",
    "ErrorStage",
    "classify_item_error",
    # Batch summary
    "BatchEvalResult",
    "BatchRunSummary",
    "CriterionRunSummary",
    "ExecutionCoverage",
    "JurorRunSummary",
    "ScoreBucket",
    "ScoreDistribution",
    "aggregate_batch_results",
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
    "AssertionResult",
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
