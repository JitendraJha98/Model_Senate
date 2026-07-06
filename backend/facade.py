"""OpenAI-compatible facade — expose the Council as a `/v1/chat/completions` model.

Turns the project from "an app you visit" into "a model you can plug into anything"
(Open WebUI, LibreChat, Cursor, any OpenAI SDK). The synthesis is returned as a normal
chat completion; council metadata (confidence grade, run id) rides along under `x_council`.
"""

from __future__ import annotations

import time
from typing import Iterator

from pydantic import BaseModel

from backend.schemas import CouncilRun


class OAIMessage(BaseModel):
    role: str
    content: str


class OAIChatRequest(BaseModel):
    messages: list[OAIMessage]
    model: str | None = None
    stream: bool = False
    # Accepted and ignored — present so standard OpenAI clients don't 422.
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None


def messages_to_prompt(messages: list[OAIMessage]) -> tuple[str, str | None]:
    """Flatten an OpenAI messages array into (prompt, system_context).

    System messages become the council's system_context. A single user turn is used
    verbatim; a multi-turn conversation is flattened into a readable transcript.
    """
    system = "\n\n".join(m.content for m in messages if m.role == "system") or None
    convo = [m for m in messages if m.role != "system"]
    if not convo:
        return "", system
    if len(convo) == 1:
        return convo[0].content, system
    return "\n\n".join(f"{m.role.upper()}: {m.content}" for m in convo), system


def council_answer(run: CouncilRun) -> str:
    if run.reintegration and run.reintegration.unified_answer:
        return run.reintegration.unified_answer
    if run.synthesis and run.synthesis.direct_answer:
        return run.synthesis.direct_answer
    return ""


def to_chat_completion(run: CouncilRun, model: str | None, answer: str) -> dict:
    return {
        "id": f"chatcmpl-{run.id}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model or "model-council",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": answer},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": run.total_tokens,
            "total_tokens": run.total_tokens,
        },
        "x_council": {
            "confidence_grade": run.confidence_grade,
            "run_id": run.id,
            "status": run.status,
        },
    }


def to_stream_chunks(run: CouncilRun, model: str | None, answer: str) -> Iterator[dict]:
    base = {
        "id": f"chatcmpl-{run.id}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model or "model-council",
    }
    yield {**base, "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}
    yield {**base, "choices": [{"index": 0, "delta": {"content": answer}, "finish_reason": None}]}
    yield {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
