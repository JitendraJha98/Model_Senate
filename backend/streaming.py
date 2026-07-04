from __future__ import annotations

import asyncio
import json
from typing import Any


class CouncilEventStream:
    """Append-only event log for one run.

    Events are retained so a subscriber that connects late — or reconnects after a
    dropped connection — can replay from any offset instead of losing everything.
    """

    def __init__(self, run_id: str):
        self.run_id = run_id
        self._history: list[tuple[str, dict[str, Any]]] = []
        self._closed = False
        self._new = asyncio.Event()

    async def emit(self, event: str, payload: dict[str, Any]) -> None:
        if not self._closed:
            self._history.append((event, payload))
            self._new.set()

    async def close(self) -> None:
        self._closed = True
        self._history.append(("__close__", {}))
        self._new.set()

    async def events(self, start: int = 0):
        """Yield SSE frames from index `start`; each frame carries a 1-based `id:` cursor
        so an EventSource reconnect (via Last-Event-ID) resumes without gaps."""
        i = max(0, start)
        while True:
            while i < len(self._history):
                event, payload = self._history[i]
                i += 1
                if event == "__close__":
                    return
                yield f"id: {i}\nevent: {event}\ndata: {json.dumps(payload, default=str)}\n\n"
            if self._closed:
                return
            self._new.clear()
            if i < len(self._history):
                continue  # guard against an emit that landed between the check and clear
            await self._new.wait()


class ScopedEventStream:
    """Wraps a parent stream and tags every payload with the sub-run it came from, so
    interleaved multi-part events can be attributed to the right sub-question."""

    def __init__(self, parent: CouncilEventStream, sub_run_id: str):
        self._parent = parent
        self._sub_run_id = sub_run_id

    async def emit(self, event: str, payload: dict[str, Any]) -> None:
        await self._parent.emit(event, {**payload, "sub_run_id": self._sub_run_id})


active_streams: dict[str, CouncilEventStream] = {}


def create_stream(run_id: str) -> CouncilEventStream:
    stream = CouncilEventStream(run_id)
    active_streams[run_id] = stream
    return stream


def get_stream(run_id: str) -> CouncilEventStream | None:
    return active_streams.get(run_id)


def close_stream(run_id: str) -> None:
    active_streams.pop(run_id, None)
