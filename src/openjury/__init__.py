"""OpenJury: A modular framework for evaluating multiple model outputs using LLM-based jurors."""

from openjury.config import (
    CriterionConfig,
    JurorConfig,
    JuryConfig,
    ResponseCandidate,
    VotingCriteria,
)
from openjury.juror import Juror
from openjury.jury_engine import OpenJury
from openjury.output_format import Verdict, VerdictFormatter
from openjury.voting import (
    JurorEvaluation,
    VotingAggregator,
    VotingMethod,
    VotingResult,
)

__version__ = "0.1.0"
__all__ = [
    "OpenJury",
    "Juror",
    "JurorConfig",
    "JuryConfig",
    "CriterionConfig",
    "VerdictFormatter",
    "Verdict",
    "VotingMethod",
    "VotingAggregator",
    "JurorEvaluation",
    "VotingResult",
    "VotingCriteria",
    "ResponseCandidate",
]
