import json
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class VotingCriteria(str, Enum):
    """Convenience enum of common criterion names. Criterion names are free-form strings;
    these values are provided as a reference for well-known criteria."""

    FACTUALITY = "factuality"
    CLARITY = "clarity"
    REASONING = "reasoning"
    CONCISENESS = "conciseness"
    ORIGINALITY = "originality"
    RELEVANCY = "relevance"
    STYLE = "style"
    CONTEXTUALITY = "contextuality"


class CriterionConfig(BaseModel):
    name: str = Field(..., description="Name of the criterion (free-form string)")
    description: str = Field(
        ..., description="Description of what this criterion evaluates"
    )
    weight: float = Field(
        default=1.0, ge=0.0, description="Weight for this criterion in scoring"
    )
    rubric: Optional[Dict[str, str]] = Field(
        default=None,
        description=(
            "Optional score anchors keyed by score level string (e.g. '1', '3', '5'). "
            "Providing rubric anchors significantly improves inter-rater reliability "
            "across different juror models (G-Eval, Liu et al. 2023)."
        ),
    )

    @field_validator("name", mode="before")
    @classmethod
    def coerce_enum_to_str(cls, v: Any) -> str:
        if isinstance(v, VotingCriteria):
            return v.value
        if isinstance(v, str):
            # Accept enum member names (e.g. "FACTUALITY") by lowercasing
            for member in VotingCriteria:
                if v.upper() == member.name or v.lower() == member.value:
                    return member.value
        return str(v)


class JurorConfig(BaseModel):

    name: str = Field(..., description="Name or identifier for this juror")
    model_name: str = Field(
        default="openrouter/horizon-alpha",
        description="LLM model to use for this juror",
    )
    system_prompt: Optional[str] = Field(
        None, description="Custom system prompt for this juror"
    )
    temperature: float = Field(
        default=0.1, ge=0.0, le=2.0, description="Temperature for response generation"
    )
    weight: float = Field(
        default=1.0, ge=0.0, description="Weight for this juror's vote"
    )


class JuryConfig(BaseModel):

    name: str = Field(..., description="Name for this jury configuration")
    description: Optional[str] = Field(
        None, description="Description of what this jury evaluates"
    )
    criteria: List[CriterionConfig] = Field(
        ..., description="List of evaluation criteria"
    )
    jurors: List[JurorConfig] = Field(..., description="List of juror configurations")
    score_scale: int = Field(
        default=5,
        ge=2,
        le=10,
        description="Global score scale for all criteria (e.g. 5 means scores range 1–5)",
    )
    num_trials: int = Field(
        default=1,
        ge=1,
        le=5,
        description=(
            "Number of times to call the agent per prompt. "
            "num_trials=1 (default): single quality evaluation. "
            "num_trials>1: consistency audit — measures how reliably the agent "
            "produces similar-quality responses. Quality score always comes from trial 1."
        ),
    )
    custom_scoring_function: Optional[str] = Field(
        default=None,
        description=(
            "Name of a ScoringFunction registered via ScoreAggregator.register(). "
            "When set, an additional 'custom' metric is computed alongside the canned metrics."
        ),
    )
    require_explanation: bool = Field(
        default=True, description="Whether jurors must provide explanations"
    )
    max_retries: int = Field(
        default=3, ge=0, description="Max retries for failed juror calls"
    )
    custom_settings: Dict[str, Any] = Field(
        default_factory=dict, description="Additional custom settings"
    )
    evaluation_template: Optional[str] = Field(
        default=None,
        description=(
            "Optional override for the evaluation prompt template. "
            "Must include placeholders: prompt, response, criteria, score_scale, "
            "example_criterion_name, references_section, case_rules_section."
        ),
    )

    def get_total_juror_weight(self) -> float:
        return sum(juror.weight for juror in self.jurors)

    def get_total_criteria_weight(self) -> float:
        return sum(criterion.weight for criterion in self.criteria)

    @staticmethod
    def from_json(json_str: str) -> "JuryConfig":
        return JuryConfig.model_validate_json(json_str)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "JuryConfig":
        return JuryConfig.model_validate(data)

    @staticmethod
    def from_json_file(file_path: str) -> "JuryConfig":
        try:
            with open(file_path, "r") as f:
                config_data = json.load(f)
            return JuryConfig.from_dict(config_data)
        except Exception as e:
            raise ValueError(f"Error loading config from {file_path}: {e}") from e


class AgentResponse(BaseModel):
    id: str = Field(
        default_factory=lambda: f"response_{uuid.uuid4().hex}",
        description="A unique ID of the response",
    )
    alias: Optional[str] = Field(
        None, description="An optional human-readable alias for the response"
    )
    content: str = Field(..., description="The generated text of the response")
    model_name: Optional[str] = Field(
        None, description="The LLM model that generated this response"
    )

    def __str__(self) -> str:
        return self.content

    def get_display_name(self) -> str:
        return self.alias or self.id
