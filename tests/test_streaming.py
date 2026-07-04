import pytest

from backend.streaming import CouncilEventStream, ScopedEventStream


@pytest.mark.asyncio
async def test_late_subscriber_replays_full_history():
    stream = CouncilEventStream("run-1")
    await stream.emit("plan_ready", {"a": 1})
    await stream.emit("agent_opinion", {"b": 2})
    await stream.close()

    frames = [frame async for frame in stream.events()]
    assert any("event: plan_ready" in f for f in frames)
    assert any("event: agent_opinion" in f for f in frames)
    # Each frame carries a 1-based id cursor for reconnect resume.
    assert frames[0].startswith("id: 1")


@pytest.mark.asyncio
async def test_events_resume_from_offset():
    stream = CouncilEventStream("run-2")
    await stream.emit("a", {})
    await stream.emit("b", {})
    await stream.close()

    frames = [frame async for frame in stream.events(start=1)]
    assert not any("event: a" in f for f in frames)
    assert any("event: b" in f for f in frames)


@pytest.mark.asyncio
async def test_scoped_stream_tags_sub_run_id():
    parent = CouncilEventStream("run-3")
    scoped = ScopedEventStream(parent, "sub-123")
    await scoped.emit("agent_opinion", {"model_id": "m1"})
    await parent.close()

    frames = [frame async for frame in parent.events()]
    assert any("sub-123" in f for f in frames)
