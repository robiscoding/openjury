import json
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class VotingMethod(str, Enum):

    # Most jurors vote for same winner; simple and fast
    MAJORITY = "majority"

    # Average score per response across all jurors; balance, ties possible
    AVERAGE = "average"

    # Jurors have weights, highest weighted score wins; some jurors matter more
    WEIGHTED = "weighted"

    # Response are ranked, ranks are averaged; handles subjective cases well
    RANKED = "ranked"

    # Only pick a winner if majority AND scores align; conservative, high-confidence mode
    CONSENSUS = "consensus"

    # Custom user-defined voting/scoring function
    CUSTOM = "custom"


class VotingCriteria(str, Enum):

    # Truthfulness relative to known facts
    FACTUALITY = "factuality"

    # Is it easy to understand?
    CLARITY = "clarity"

    # Is the logic sound and well supported?
    REASONING = "reasoning"

    # Avoids fluff or repetition
    CONCISENESS = "conciseness"

    # Original and creative
    ORIGINALITY = "originality"

    # Relevant to the prompt
    RELEVANCY = "relevance"

    # Style and tone
    STYLE = "style"

    # Contextual and relevant to the prompt
    CONTEXTUALITY = "contextuality"


class CriterionConfig(BaseModel):

    name: VotingCriteria = Field(
        default=VotingCriteria.FACTUALITY, description="Name of the criterion"
    )
    description: str = Field(
        ..., description="Description of what this criterion evaluates"
    )
    weight: float = Field(
        default=1.0, ge=0.0, description="Weight for this criterion in scoring"
    )
    max_score: int = Field(
        default=5, ge=1, description="Maximum score for this criterion"
    )
    custom: bool = Field(
        default=False, description="Whether this criterion is a custom voting method"
    )


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
    voting_method: VotingMethod = Field(
        default=VotingMethod.MAJORITY, description="Method for aggregating votes"
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
    custom_voting_function: Optional[str] = Field(
        default=None,
        description="Name of custom voting function when using CUSTOM voting method",
    )

    def get_total_juror_weight(self) -> float:
        return sum(juror.weight for juror in self.jurors)

    def get_total_criteria_weight(self) -> float:
        return sum(criterion.weight for criterion in self.criteria)

    @staticmethod
    def from_json(
        json_str: str, custom_voting_class: Optional[Any] = None
    ) -> "JuryConfig":
        config = JuryConfig.model_validate_json(json_str)
        config._register_custom_methods(custom_voting_class)
        return config

    @staticmethod
    def from_dict(
        data: Dict[str, Any], custom_voting_class: Optional[Any] = None
    ) -> "JuryConfig":
        config = JuryConfig.model_validate(data)
        config._register_custom_methods(custom_voting_class)
        return config

    @staticmethod
    def from_json_file(
        file_path: str, custom_voting_class: Optional[Any] = None
    ) -> "JuryConfig":
        try:
            with open(file_path, "r") as f:
                config_data = json.load(f)
            return JuryConfig.from_dict(config_data, custom_voting_class)
        except Exception as e:
            print(f"Error loading config from {file_path}: {e}")
            raise

    def _register_custom_methods(self, custom_voting_class: Optional[Any]) -> None:
        """Automatically register custom voting methods when using custom voting."""
        from openjury.voting import VotingAggregator

        if self.voting_method == VotingMethod.CUSTOM and not custom_voting_class:
            raise ValueError(
                "Custom voting method selected but no custom voting class provided"
            )

        if self.voting_method != VotingMethod.CUSTOM or not custom_voting_class:
            return

        # When using custom voting, the caller needs to provide a class with static methods
        # that implement the custom voting logic.
        # This will register all static methods from the providedcustom voting class
        for attr_name in dir(custom_voting_class):
            if attr_name.startswith("_"):
                continue
            attr = getattr(custom_voting_class, attr_name)
            if callable(attr):
                try:
                    VotingAggregator.register_custom_function(attr_name, attr)
                    print(f"Registered custom voting method: {attr_name}")
                except Exception as e:
                    print(
                        f"Warning: Failed to register custom method '{attr_name}': {e}"
                    )


class ResponseCandidate(BaseModel):
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
