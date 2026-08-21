"""Tests for the in-process asynchronous event bus."""

import asyncio
import logging
from datetime import UTC

import pytest

from app.events.bus import EventBus
from app.events.event import Event


class SampleEvent(Event):
    value: int


class OtherEvent(Event):
    value: int


def test_event_metadata() -> None:
    event = SampleEvent(source="test-src", value=42)
    assert event.event_type == "SampleEvent"
    assert event.timestamp.tzinfo == UTC
    assert event.payload == {"value": 42}
    other = SampleEvent(source="test-src", value=1)
    assert event.event_id != other.event_id


def test_event_type_override() -> None:
    event = Event(source="test-src", event_type="custom")
    assert event.event_type == "custom"


@pytest.mark.asyncio
async def test_multiple_subscribers() -> None:
    bus = EventBus()
    first: list[Event] = []
    second: list[Event] = []

    async def record_first(event: Event) -> None:
        first.append(event)

    async def record_second(event: Event) -> None:
        second.append(event)

    bus.subscribe("SampleEvent", record_first)
    bus.subscribe("SampleEvent", record_second)
    event = SampleEvent(source="test-src", value=1)
    await bus.publish(event)
    await bus.drain()

    assert first == [event]
    assert second == [event]


@pytest.mark.asyncio
async def test_unsubscribe() -> None:
    bus = EventBus()
    kept: list[Event] = []
    removed: list[Event] = []

    async def record_kept(event: Event) -> None:
        kept.append(event)

    async def record_removed(event: Event) -> None:
        removed.append(event)

    bus.subscribe("SampleEvent", record_kept)
    bus.subscribe("SampleEvent", record_removed)
    assert bus.unsubscribe("SampleEvent", record_removed) is True
    assert bus.unsubscribe("SampleEvent", record_removed) is False
    assert bus.unsubscribe("OtherEvent", record_kept) is False

    await bus.publish(SampleEvent(source="test-src", value=1))
    await bus.drain()

    assert len(kept) == 1
    assert removed == []


@pytest.mark.asyncio
async def test_unsubscribe_all() -> None:
    bus = EventBus()
    received: list[Event] = []

    async def record(event: Event) -> None:
        received.append(event)

    bus.subscribe("SampleEvent", record)
    bus.subscribe("OtherEvent", record)
    assert bus.unsubscribe_all(record) == 2
    await bus.publish(SampleEvent(source="test-src", value=1))
    await bus.publish(OtherEvent(source="test-src", value=2))
    await bus.drain()
    assert received == []


@pytest.mark.asyncio
async def test_subscribe_deduplicates_same_handler() -> None:
    bus = EventBus()
    count = 0

    async def record(event: Event) -> None:
        nonlocal count
        count += 1

    bus.subscribe("SampleEvent", record)
    bus.subscribe("SampleEvent", record)
    assert bus.subscriber_count("SampleEvent") == 1
    await bus.publish(SampleEvent(source="test-src", value=1))
    await bus.drain()
    assert count == 1


@pytest.mark.asyncio
async def test_handler_exception_is_isolated(caplog: pytest.LogCaptureFixture) -> None:
    bus = EventBus()
    received: list[Event] = []

    async def boom(event: Event) -> None:
        raise RuntimeError("handler bug")

    async def safe(event: Event) -> None:
        received.append(event)

    bus.subscribe("SampleEvent", boom)
    bus.subscribe("SampleEvent", safe)
    event = SampleEvent(source="test-src", value=1)
    await bus.publish(event)
    await bus.drain()

    assert received == [event]
    assert any("failed" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_concurrent_publish() -> None:
    bus = EventBus()
    counts = {"first": 0, "second": 0}

    async def count_first(event: Event) -> None:
        counts["first"] += 1

    async def count_second(event: Event) -> None:
        counts["second"] += 1

    bus.subscribe("SampleEvent", count_first)
    bus.subscribe("SampleEvent", count_second)

    publishers = 3
    events_per_publisher = 20
    expected = publishers * events_per_publisher

    async def publish_many() -> None:
        for _ in range(events_per_publisher):
            await bus.publish(SampleEvent(source="test-src", value=1))

    await asyncio.gather(*(publish_many() for _ in range(publishers)))
    await bus.drain()

    assert counts["first"] == expected
    assert counts["second"] == expected


@pytest.mark.asyncio
async def test_publish_tracks_pending_until_drained() -> None:
    bus = EventBus()
    done = asyncio.Event()

    async def slow_handler(event: Event) -> None:
        await asyncio.sleep(0.05)
        done.set()

    bus.subscribe("SampleEvent", slow_handler)
    await bus.publish(SampleEvent(source="test-src", value=1))
    assert bus.pending_count == 1
    await bus.drain()
    assert bus.pending_count == 0
    assert done.is_set()


@pytest.mark.asyncio
async def test_publish_and_duration_are_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    bus = EventBus()

    async def handler(event: Event) -> None:
        pass

    bus.subscribe("SampleEvent", handler)
    with caplog.at_level(logging.DEBUG, logger="app.events"):
        await bus.publish(SampleEvent(source="test-src", value=1))
        await bus.drain()

    messages = [record.message for record in caplog.records]
    assert any("Event published" in message for message in messages)
    assert any("subscribers=1" in message for message in messages)
    assert any("duration=" in message for message in messages)