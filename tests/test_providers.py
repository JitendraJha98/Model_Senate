import asyncio
import json

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
async def test_json_mode_and_generation_params_reach_payload():
    captured: dict = {}

    def handler(request):
        captured.update(json.loads(request.content))
        return httpx.Response(200, json=_ok_body())

    respx.post("https://api.openai.com/v1/chat/completions").mock(side_effect=handler)
    route = ModelRoute(
        id="m", provider="openrouter", model="x", display_name="X",
        missing_key=False, temperature=0, max_tokens=256, seed=7,
    )
    adapter = OpenAICompatibleAdapter("key", "https://api.openai.com/v1")
    await adapter.complete(route, MESSAGES, json_mode=True)

    assert captured["response_format"] == {"type": "json_object"}
    assert captured["temperature"] == 0
    assert captured["max_tokens"] == 256
    assert captured["seed"] == 7


@respx.mock
@pytest.mark.asyncio
async def test_generation_params_omitted_when_unset():
    captured: dict = {}

    def handler(request):
        captured.update(json.loads(request.content))
        return httpx.Response(200, json=_ok_body())

    respx.post("https://api.openai.com/v1/chat/completions").mock(side_effect=handler)
    adapter = OpenAICompatibleAdapter("key", "https://api.openai.com/v1")
    await adapter.complete(ROUTE, MESSAGES)  # ROUTE has no generation params

    assert "temperature" not in captured
    assert "response_format" not in captured


@respx.mock
@pytest.mark.asyncio
async def test_route_base_url_overrides_and_needs_no_key():
    # Local server (Ollama-style): per-route base_url, adapter constructed with no key.
    captured_headers: dict = {}

    def handler(request):
        captured_headers.update(dict(request.headers))
        return httpx.Response(200, json=_ok_body())

    local = respx.post("http://localhost:11434/v1/chat/completions").mock(side_effect=handler)
    route = ModelRoute(
        id="local", provider="openai", model="llama3", display_name="Local Llama",
        base_url="http://localhost:11434/v1",
    )
    adapter = OpenAICompatibleAdapter(None, "https://api.openai.com/v1")  # no key
    content, _, _ = await adapter.complete(route, MESSAGES)

    assert content == "hello"
    assert local.call_count == 1  # hit the override, not the default endpoint
    assert "authorization" not in {k.lower() for k in captured_headers}


@pytest.mark.asyncio
async def test_base_url_route_is_not_marked_missing_key():
    from backend.config import Settings, load_model_routes

    settings = Settings(model_senate_routes=(
        '[{"id":"local","provider":"openai","model":"llama3",'
        '"display_name":"Local","base_url":"http://localhost:11434/v1"}]'
    ))
    routes = load_model_routes(settings)
    assert routes[0].missing_key is False  # available despite no OPENAI_API_KEY


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
