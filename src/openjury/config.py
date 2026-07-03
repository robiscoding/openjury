import json
import re
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator

_RUBRIC_KEY_PATTERN = re.compile(r"^\s*(\d+)\s*(?:-\s*(\d+)\s*)?$")


def parse_rubric_key(key: str) -> tuple[int, int]:
    """Parse an exact score or inclusive score range from a rubric key."""
    match = _RUBRIC_KEY_PATTERN.fullmatch(key)
    if match is None:
        raise ValueError(
            f"Invalid rubric key {key!r}; use an integer score such as '3' "
            "or an inclusive range such as '1-2'"
        )
    start = int(match.group(1))
    end = int(match.group(2) or start)
    if start > end:
        raise ValueError(
            f"Invalid rubric range {key!r}; range start cannot exceed range end"
        )
    return start, end


class JurorProvider(str, Enum):
    OPENAI_COMPATIBLE = "openai_compatible"
    ANTHROPIC = "anthropic"


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


class AssertionType(str, Enum):
    """Deterministic checks that can be applied to an agent response."""

    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    CONTAINS_ANY = "contains_any"
    CONTAINS_ALL = "contains_all"
    REGEX = "regex"
    MIN_LENGTH = "min_length"
    MAX_LENGTH = "max_length"


class AssertionConfig(BaseModel):
    name: str = Field(..., description="Name or identifier for this assertion")
    type: AssertionType = Field(..., description="Type of deterministic assertion")
    value: Union[str, List[str], int] = Field(
        ...,
        description=(
            "Expected string, list of strings for contains_any/contains_all, "
            "or non-negative integer for min_length/max_length"
        ),
    )
    case_sensitive: bool = Field(
        default=True,
        description="Whether string matching should preserve case",
    )
    required: bool = Field(
        default=True,
        description="Whether this assertion must pass for assertions_passed to be true",
    )
    weight: float = Field(
        default=1.0,
        gt=0.0,
        description="Relative weight used to calculate assertion_score",
    )

    @model_validator(mode="after")
    def validate_value_for_type(self) -> "AssertionConfig":
        list_types = {AssertionType.CONTAINS_ANY, AssertionType.CONTAINS_ALL}
        length_types = {AssertionType.MIN_LENGTH, AssertionType.MAX_LENGTH}

        if self.type in list_types:
            if (
                not isinstance(self.value, list)
                or not self.value
                or any(not item for item in self.value)
            ):
                raise ValueError(
                    f"{self.type.value} requires a non-empty list of non-empty strings"
                )
        elif self.type in length_types:
            if (
                not isinstance(self.value, int)
                or isinstance(self.value, bool)
                or self.value < 0
            ):
                raise ValueError(
                    f"{self.type.value} requires a non-negative integer value"
                )
        elif not isinstance(self.value, str) or not self.value:
            raise ValueError(f"{self.type.value} requires a non-empty string value")

        if self.type == AssertionType.REGEX:
            flags = 0 if self.case_sensitive else re.IGNORECASE
            assert isinstance(self.value, str)
            try:
                re.compile(self.value, flags)
            except re.error as exc:
                raise ValueError(f"Invalid regex pattern: {exc}") from exc

        return self


class AssertionPolicyConfig(BaseModel):
    """A reusable group of deterministic checks and pass thresholds."""

    checks: List[AssertionConfig] = Field(
        ..., min_length=1, description="Assertions evaluated as one reusable policy"
    )
    assertion_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    quality_threshold: Optional[float] = Field(default=None, ge=0.0)


class DatasetItemConfig(BaseModel):
    """One row in an inline config dataset."""

    id: str = Field(..., min_length=1, description="Stable dataset row identifier")
    input: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("input", "prompt"),
        description="Prompt sent to the agent; accepts 'prompt' as an input alias",
    )
    ground_truth: Optional[str] = None
    assertion_ids: List[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_assertion_ids(cls, value: Any) -> Any:
        if isinstance(value, dict) and "assertion_ids" not in value:
            assertion_id = value.get("assertion_id")
            if assertion_id is not None:
                return {**value, "assertion_ids": [assertion_id]}
        return value

    @model_validator(mode="after")
    def validate_assertion_ids(self) -> "DatasetItemConfig":
        if any(not assertion_id for assertion_id in self.assertion_ids):
            raise ValueError("assertion_ids cannot contain empty strings")
        if len(self.assertion_ids) != len(set(self.assertion_ids)):
            raise ValueError("assertion_ids cannot contain duplicates")
        return self


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
            "Optional score anchors keyed by an exact score or inclusive range "
            "(e.g. '1', '2-3', '4-5'). "
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

    @field_validator("rubric")
    @classmethod
    def validate_rubric_syntax(
        cls, rubric: Optional[Dict[str, str]]
    ) -> Optional[Dict[str, str]]:
        if rubric is None:
            return None
        if not rubric:
            raise ValueError("rubric cannot be empty")

        normalized: Dict[str, str] = {}
        for key, description in rubric.items():
            start, end = parse_rubric_key(key)
            normalized_key = str(start) if start == end else f"{start}-{end}"
            if normalized_key in normalized:
                raise ValueError(
                    f"Duplicate rubric interval after normalization: {normalized_key!r}"
                )
            if not description.strip():
                raise ValueError(
                    f"Rubric description for {normalized_key!r} cannot be empty"
                )
            normalized[normalized_key] = description
        return normalized


class LLMProviderConfig(BaseModel):
    provider: JurorProvider = Field(
        ...,
        description=(
            "LLM provider. 'openai_compatible' works with OpenAI, OpenRouter, xAI, "
            "Gemini, Ollama, vLLM, or any OpenAI-compatible endpoint. "
            "'anthropic' uses the Anthropic API directly (requires openjury[anthropic])."
        ),
    )
    model_name: str = Field(..., description="LLM model identifier for this provider")
    api_key: str = Field(
        ...,
        description="API key for this provider. Supports ${ENV_VAR} interpolation.",
    )
    base_url: Optional[str] = Field(
        default=None,
        description=(
            "Optional base URL for openai_compatible providers. "
            "Supports ${ENV_VAR} interpolation. Not used for anthropic."
        ),
    )


class JurorConfig(BaseModel):

    name: str = Field(..., description="Name or identifier for this juror")
    model_name: Optional[str] = Field(
        default=None,
        description=(
            "LLM model override. Must be set together with api_key and provider "
            "to override the jury-level llm_provider."
        ),
    )
    provider: Optional[JurorProvider] = Field(
        default=None,
        description=(
            "LLM provider override. Must be set together with model_name and api_key."
        ),
    )
    api_key: Optional[str] = Field(
        default=None,
        description=(
            "API key override. Must be set together with model_name and provider. "
            "Supports ${ENV_VAR} interpolation."
        ),
    )
    base_url: Optional[str] = Field(
        default=None,
        description=(
            "Optional base URL when this juror fully overrides llm_provider. "
            "Supports ${ENV_VAR} interpolation. Not used for anthropic."
        ),
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

    @model_validator(mode="after")
    def validate_provider_override(self) -> "JurorConfig":
        override_fields = (self.model_name, self.api_key, self.provider)
        set_count = sum(1 for value in override_fields if value is not None)
        if set_count not in (0, 3):
            raise ValueError(
                f"Juror '{self.name}' must set model_name, api_key, and provider "
                "together to override llm_provider, or omit all three to inherit "
                "the jury-level llm_provider."
            )
        return self


class JuryConfig(BaseModel):

    name: str = Field(..., description="Name for this jury configuration")
    description: Optional[str] = Field(
        None, description="Description of what this jury evaluates"
    )
    llm_provider: Optional[LLMProviderConfig] = Field(
        default=None,
        description=(
            "Default LLM provider settings for jurors that do not fully override "
            "with their own model_name, api_key, and provider."
        ),
    )
    criteria: List[CriterionConfig] = Field(
        ..., description="List of evaluation criteria"
    )
    assertions: Dict[str, AssertionPolicyConfig] = Field(
        default_factory=dict,
        description=(
            "Reusable assertion policies keyed by IDs referenced from dataset rows. "
            "Legacy assertion lists are normalized to a policy named 'default'."
        ),
    )
    dataset: List[DatasetItemConfig] = Field(
        default_factory=list,
        description="Inline dataset represented as an array of JSON row objects",
    )
    assertion_threshold: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Legacy default assertion threshold. New configs should set this on "
            "each named AssertionPolicyConfig."
        ),
    )
    quality_threshold: Optional[float] = Field(
        default=None,
        ge=0.0,
        description=(
            "Legacy default quality threshold. New configs should set this on "
            "each named AssertionPolicyConfig."
        ),
    )
    jurors: List[JurorConfig] = Field(..., description="List of juror configurations")
    score_scale: int = Field(
        default=5,
        ge=2,
        le=10,
        description="Global maximum score for all criteria",
    )
    score_min: int = Field(
        default=1,
        ge=0,
        le=1,
        description="Global minimum score; set to 0 to enable zero scores",
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
    evaluation_template: Optional[str] = Field(
        default=None,
        description=(
            "Optional override for the evaluation prompt template. "
            "Must include placeholders: prompt, response, criteria, score_min, "
            "score_scale, example_criterion_name, references_section, "
            "case_rules_section."
        ),
    )

    @field_validator("assertions", mode="before")
    @classmethod
    def normalize_assertion_registry(cls, value: Any) -> Any:
        if isinstance(value, list):
            if not value:
                return {}
            return {"default": {"checks": value}}
        return value

    @model_validator(mode="after")
    def validate_quality_threshold(self) -> "JuryConfig":
        if (
            self.quality_threshold is not None
            and self.quality_threshold > self.score_scale
        ):
            raise ValueError(
                "quality_threshold cannot be greater than score_scale "
                f"({self.score_scale})"
            )
        for policy_id, policy in self.assertions.items():
            if (
                policy.quality_threshold is not None
                and policy.quality_threshold > self.score_scale
            ):
                raise ValueError(
                    f"assertions.{policy_id}.quality_threshold cannot be greater "
                    f"than score_scale ({self.score_scale})"
                )

        for criterion in self.criteria:
            if criterion.rubric is None:
                continue
            intervals = [
                (*parse_rubric_key(key), key) for key in criterion.rubric.keys()
            ]
            covered_scores: set[int] = set()
            uses_range = any(start != end for start, end, _ in intervals)
            for start, end, key in intervals:
                if start < self.score_min or end > self.score_scale:
                    raise ValueError(
                        f"Criterion {criterion.name!r} rubric key {key!r} is outside "
                        f"the configured score scale "
                        f"{self.score_min}-{self.score_scale}"
                    )
                interval_scores = set(range(start, end + 1))
                overlap = covered_scores & interval_scores
                if overlap:
                    raise ValueError(
                        f"Criterion {criterion.name!r} rubric intervals overlap at "
                        f"score(s) {sorted(overlap)}"
                    )
                covered_scores.update(interval_scores)
            if uses_range:
                expected_scores = set(range(self.score_min, self.score_scale + 1))
                missing_scores = sorted(expected_scores - covered_scores)
                if missing_scores:
                    raise ValueError(
                        f"Criterion {criterion.name!r} range rubric must cover every "
                        f"score from {self.score_min}-{self.score_scale}; "
                        f"missing {missing_scores}"
                    )

        item_ids = [item.id for item in self.dataset]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("dataset item ids must be unique")
        for item in self.dataset:
            unknown_ids = [
                assertion_id
                for assertion_id in item.assertion_ids
                if assertion_id not in self.assertions
            ]
            if unknown_ids:
                raise ValueError(
                    f"Dataset item '{item.id}' references unknown assertion_ids "
                    f"{unknown_ids}"
                )
        return self

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


def resolve_juror_llm_config(
    juror: JurorConfig,
    jury_llm_provider: Optional[LLMProviderConfig],
) -> LLMProviderConfig:
    """Resolve the effective LLM provider config for a juror.

    Jurors either inherit the full jury-level llm_provider or override it by setting
    model_name, api_key, and provider together. Partial overrides are invalid.
    """
    from openjury.env import ConfigurationError

    if (
        juror.model_name is not None
        and juror.api_key is not None
        and juror.provider is not None
    ):
        return LLMProviderConfig(
            provider=juror.provider,
            model_name=juror.model_name,
            api_key=juror.api_key,
            base_url=juror.base_url,
        )

    if jury_llm_provider is None:
        raise ConfigurationError(
            f"Juror '{juror.name}' has no LLM provider configuration. "
            "Set llm_provider on JuryConfig or provide model_name, api_key, and "
            "provider on the juror."
        )

    return jury_llm_provider
