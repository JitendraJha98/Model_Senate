from __future__ import annotations

import asyncio
import json
from typing import Any


class CouncilEventStream:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self._queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
        self._closed = False

    async def emit(self, event: str, payload: dict[str, Any]) -> None:
        if not self._closed:
            await self._queue.put((event, payload))

    async def close(self) -> None:
        self._closed = True
        await self._queue.put(("__close__", {}))

    async def events(self):
        while True:
            event, payload = await self._queue.get()
            if event == "__close__":
                break
            yield f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


active_streams: dict[str, CouncilEventStream] = {}


def create_stream(run_id: str) -> CouncilEventStream:
    stream = CouncilEventStream(run_id)
    active_streams[run_id] = stream
    return stream


def get_stream(run_id: str) -> CouncilEventStream | None:
    return active_streams.get(run_id)


def close_stream(run_id: str) -> None:
    active_streams.pop(run_id, None)
