import asyncio

import httpx
import pytest
import respx

from backend.providers import OpenAICompatibleAdapter, ProviderError
from backend.schemas import ChatMessage, ModelRoute

ROUTE = ModelRoute(id="m", provider="openrouter", model="x", display_name="X", missing_key=False)
MESSAGES = [ChatMessage(role="user", content="hi")]


def _ok_body():
    return {"choices": [{"message": {"content": "hello"}}], "usage": {"total_tokens": 5}}


@respx.mock
@pytest.mark.asyncio
async def test_retries_on_429_then_succeeds():
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(429, json={"error": "rate limited"}),
            httpx.Response(200, json=_ok_body()),
        ]
    )
    adapter = OpenAICompatibleAdapter("key", "https://api.openai.com/v1", max_retries=2)
    content, usage, _ = await adapter.complete(ROUTE, MESSAGES)
    assert content == "hello"
    assert usage is not None and usage.total_tokens == 5
    assert route.call_count == 2


@respx.mock
@pytest.mark.asyncio
async def test_gives_up_after_max_retries():
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(503, json={"error": "unavailable"})
    )
    adapter = OpenAICompatibleAdapter("key", "https://api.openai.com/v1", max_retries=1)
    with pytest.raises(ProviderError):
        await adapter.complete(ROUTE, MESSAGES)


@respx.mock
@pytest.mark.asyncio
async def test_complete_streamed_collects_deltas():
    sse = (
        'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
        'data: {"choices":[{"delta":{}}],"usage":{"total_tokens":3}}\n\n'
        "data: [DONE]\n\n"
    )
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, text=sse)
    )
    deltas: list[str] = []

    async def on_delta(text: str) -> None:
        deltas.append(text)

    adapter = OpenAICompatibleAdapter("key", "https://api.openai.com/v1")
    content, usage, _ = await adapter.complete_streamed(ROUTE, MESSAGES, on_delta)
    assert content == "Hello"
    assert deltas == ["Hel", "lo"]
    assert usage is not None and usage.total_tokens == 3


@respx.mock
@pytest.mark.asyncio
async def test_semaphore_caps_concurrency():
    in_flight = 0
    peak = 0

    def handler(request):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        in_flight -= 1
        return httpx.Response(200, json=_ok_body())

    respx.post("https://api.openai.com/v1/chat/completions").mock(side_effect=handler)
    semaphore = asyncio.Semaphore(2)
    adapter = OpenAICompatibleAdapter("key", "https://api.openai.com/v1", semaphore=semaphore)
    await asyncio.gather(*(adapter.complete(ROUTE, MESSAGES) for _ in range(6)))
    assert peak <= 2
