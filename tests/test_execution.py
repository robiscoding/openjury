"""Tests for execution options and result types."""

from openjury.execution import (
    EvaluationItem,
    ExecutionOptions,
    FetchMetadata,
    FetchResult,
    ProgressEvent,
    ProgressEventType,
)


def test_execution_options_defaults() -> None:
    opts = ExecutionOptions()
    assert opts.max_juror_workers == 5
    assert opts.max_item_workers == 1
    assert opts.max_outbound_requests == 10
    assert opts.max_agent_response_bytes == 1_048_576
    assert opts.max_sse_event_bytes == 262_144
    assert opts.stream_idle_timeout_s == 30.0
    assert opts.cancel_event is None
    assert opts.on_progress is None
    assert opts.idempotency_key is None
    assert opts.ground_truth is None


def test_evaluation_item_fields() -> None:
    item = EvaluationItem(
        prompt="Hello?",
        item_id="item-1",
        ground_truth="Expected",
        metadata={"source": "test"},
    )
    assert item.prompt == "Hello?"
    assert item.item_id == "item-1"
    assert item.ground_truth == "Expected"
    assert item.metadata == {"source": "test"}


def test_fetch_result_defaults_metadata() -> None:
    from openjury.config import AgentResponse

    result = FetchResult(response=AgentResponse(content="hi"))
    assert result.metadata.stream is False
    assert result.metadata.chunk_count == 0
    assert result.metadata.accumulated_bytes == 0


def test_progress_event_types() -> None:
    event = ProgressEvent(
        type=ProgressEventType.AGENT_CHUNK,
        chunk_count=3,
        accumulated_bytes=120,
    )
    assert event.type == ProgressEventType.AGENT_CHUNK
    assert event.chunk_count == 3


def test_outbound_slot_limits_concurrency() -> None:
    import threading

    opts = ExecutionOptions(max_outbound_requests=1)
    gate = threading.Event()

    def hold_slot() -> None:
        with opts.outbound_slot():
            gate.set()
            threading.Event().wait(timeout=0.2)

    t = threading.Thread(target=hold_slot)
    t.start()
    assert gate.wait(timeout=1.0)

    acquired = threading.Event()

    def try_second() -> None:
        with opts.outbound_slot():
            acquired.set()

    t2 = threading.Thread(target=try_second)
    t2.start()
    t2.join(timeout=0.05)
    assert not acquired.is_set()

    t.join(timeout=1.0)
    t2.join(timeout=1.0)
    assert acquired.wait(timeout=1.0)
