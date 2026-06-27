"""Execution options and result types for composable evaluation."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterator, List, Optional

from openjury.config import AgentResponse
from openjury.errors import EvaluationErrorCode, OpenJuryEvaluationError

if TYPE_CHECKING:
    from openjury.output_format import AgentEvalResult
    from openjury.scoring import JurorScore


class ProgressEventType(StrEnum):
    AGENT_STARTED = "agent_started"
    AGENT_CHUNK = "agent_chunk"
    AGENT_COMPLETED = "agent_completed"
    JUROR_STARTED = "juror_started"
    JUROR_COMPLETED = "juror_completed"
    ITEM_STARTED = "item_started"
    ITEM_COMPLETED = "item_completed"


@dataclass
class ExecutionOptions:
    max_juror_workers: int = 5
    max_item_workers: int = 1
    max_outbound_requests: int = 10
    max_agent_response_bytes: int = 1_048_576
    max_sse_event_bytes: int = 262_144
    stream_idle_timeout_s: float = 30.0
    cancel_event: threading.Event | None = None
    on_progress: Callable[["ProgressEvent"], None] | None = None
    idempotency_key: str | None = None
    ground_truth: str | None = None
    _outbound_semaphore: threading.Semaphore | None = field(
        default=None, init=False, repr=False
    )

    def check_cancelled(self) -> None:
        """Raise OpenJuryEvaluationError if a cancellation event has been set."""
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise OpenJuryEvaluationError(
                "Evaluation cancelled",
                code=EvaluationErrorCode.EVALUATION_CANCELLED,
            )

    @contextmanager
    def outbound_slot(self) -> Iterator[None]:
        """Limit concurrent outbound HTTP/LLM calls within one evaluation run."""
        if self._outbound_semaphore is None:
            self._outbound_semaphore = threading.Semaphore(self.max_outbound_requests)
        self._outbound_semaphore.acquire()
        try:
            yield
        finally:
            self._outbound_semaphore.release()


@dataclass
class ProgressEvent:
    type: ProgressEventType
    juror_name: str | None = None
    item_index: int | None = None
    item_id: str | None = None
    chunk_count: int | None = None
    accumulated_bytes: int | None = None


@dataclass
class FetchMetadata:
    stream: bool = False
    chunk_count: int = 0
    first_chunk_latency_ms: int | None = None
    total_latency_ms: int | None = None
    accumulated_bytes: int = 0


@dataclass
class FetchResult:
    response: AgentResponse
    metadata: FetchMetadata = field(default_factory=FetchMetadata)


@dataclass
class JurorFailure:
    juror_name: str
    code: str
    message: str


@dataclass
class EvaluationItem:
    """Ephemeral input for one dataset item in a batch evaluation."""

    prompt: str
    item_id: str | None = None
    ground_truth: str | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoringResult:
    """Outcome of scoring an agent response, including partial juror failures."""

    juror_scores: List["JurorScore"] = field(default_factory=list)
    juror_failures: List[JurorFailure] = field(default_factory=list)
    all_jurors_succeeded: bool = True
    result: Optional["AgentEvalResult"] = None


@dataclass
class ItemEvalResult:
    """Result of evaluating one dataset item."""

    item: EvaluationItem
    index: int
    result: Optional["AgentEvalResult"] = None
    error: Optional[Exception] = None
