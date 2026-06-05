from __future__ import annotations

import asyncio
import json
import random
import time
from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable

import httpx

from backend.schemas import ChatMessage, ModelRoute, UsageMetadata

RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class ProviderError(RuntimeError):
    pass


class ProviderAdapter(ABC):
    def __init__(
        self,
        api_key: str | None,
        *,
        timeout: float = 90.0,
        max_retries: int = 2,
        semaphore: asyncio.Semaphore | None = None,
    ):
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        # A shared semaphore caps total in-flight requests across every adapter.
        self.semaphore = semaphore or asyncio.Semaphore(1000)

    def ensure_key(self) -> str:
        if not self.api_key:
            raise ProviderError("Missing API key for provider")
        return self.api_key

    @abstractmethod
    async def complete(self, route: ModelRoute, messages: list[ChatMessage]) -> tuple[str, UsageMetadata | None, int]:
        raise NotImplementedError

    async def complete_streamed(
        self,
        route: ModelRoute,
        messages: list[ChatMessage],
        on_delta: Callable[[str], Awaitable[None]] | None,
    ) -> tuple[str, UsageMetadata | None, int]:
        """Default: providers without native streaming fall back to a single full response."""
        content, usage, latency_ms = await self.complete(route, messages)
        if on_delta and content:
            await on_delta(content)
        return content, usage, latency_ms

    async def _send(
        self, build_request: Callable[[httpx.AsyncClient], Awaitable[httpx.Response]]
    ) -> httpx.Response:
        """Run an HTTP request under the shared concurrency cap, retrying transient failures."""
        last_error: str = "unknown error"
        for attempt in range(self.max_retries + 1):
            response: httpx.Response | None = None
            async with self.semaphore:
                try:
                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        response = await build_request(client)
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
            if response is not None:
                if response.status_code in RETRYABLE_STATUS and attempt < self.max_retries:
                    last_error = f"HTTP {response.status_code}"
                else:
                    return response
            if attempt < self.max_retries:
                await asyncio.sleep(min(8.0, 2 ** attempt) + random.uniform(0, 0.4))
        raise ProviderError(f"Request failed after {self.max_retries + 1} attempt(s): {last_error}")


class OpenAICompatibleAdapter(ProviderAdapter):
    def __init__(self, api_key: str | None, base_url: str, app_title: str = "Model_Senate", **kwargs: Any):
        super().__init__(api_key, **kwargs)
        self.base_url = base_url.rstrip("/")
        self.app_title = app_title

    async def complete(self, route: ModelRoute, messages: list[ChatMessage]) -> tuple[str, UsageMetadata | None, int]:
        api_key = self.ensure_key()
        started = time.perf_counter()
        payload = {"model": route.model, "messages": [m.model_dump() for m in messages]}
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:5173",
            "X-OpenRouter-Title": self.app_title,
        }
        response = await self._send(
            lambda client: client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            raise ProviderError(f"{route.provider} returned {response.status_code}: {response.text[:500]}")
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage = _usage_from_openai_compatible(data.get("usage"))
        return content, usage, latency_ms

    async def complete_streamed(
        self,
        route: ModelRoute,
        messages: list[ChatMessage],
        on_delta: Callable[[str], Awaitable[None]] | None,
    ) -> tuple[str, UsageMetadata | None, int]:
        api_key = self.ensure_key()
        started = time.perf_counter()
        payload = {
            "model": route.model,
            "messages": [m.model_dump() for m in messages],
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:5173",
            "X-OpenRouter-Title": self.app_title,
        }
        parts: list[str] = []
        usage: UsageMetadata | None = None
        async with self.semaphore:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST", f"{self.base_url}/chat/completions", json=payload, headers=headers
                ) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode(errors="replace")[:500]
                        raise ProviderError(f"{route.provider} returned {response.status_code}: {body}")
                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[len("data:"):].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk.get("choices") or []
                        if choices:
                            delta = (choices[0].get("delta") or {}).get("content")
                            if delta:
                                parts.append(delta)
                                if on_delta:
                                    await on_delta(delta)
                        if chunk.get("usage"):
                            usage = _usage_from_openai_compatible(chunk["usage"])
        latency_ms = int((time.perf_counter() - started) * 1000)
        return "".join(parts), usage, latency_ms


class AnthropicAdapter(ProviderAdapter):
    async def complete(self, route: ModelRoute, messages: list[ChatMessage]) -> tuple[str, UsageMetadata | None, int]:
        api_key = self.ensure_key()
        started = time.perf_counter()
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        anthropic_messages = [
            {"role": m.role, "content": m.content} for m in messages if m.role in {"user", "assistant"}
        ]
        payload: dict[str, Any] = {"model": route.model, "max_tokens": 4096, "messages": anthropic_messages}
        if system:
            payload["system"] = system
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        response = await self._send(
            lambda client: client.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers)
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            raise ProviderError(f"anthropic returned {response.status_code}: {response.text[:500]}")
        data = response.json()
        content = "".join(part.get("text", "") for part in data.get("content", []) if part.get("type") == "text")
        usage_data = data.get("usage") or {}
        usage = UsageMetadata(
            prompt_tokens=usage_data.get("input_tokens"),
            completion_tokens=usage_data.get("output_tokens"),
            total_tokens=(usage_data.get("input_tokens") or 0) + (usage_data.get("output_tokens") or 0),
        )
        return content, usage, latency_ms


class GoogleAdapter(ProviderAdapter):
    async def complete(self, route: ModelRoute, messages: list[ChatMessage]) -> tuple[str, UsageMetadata | None, int]:
        api_key = self.ensure_key()
        started = time.perf_counter()
        prompt = "\n\n".join(f"{m.role.upper()}: {m.content}" for m in messages)
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{route.model}:generateContent?key={api_key}"
        response = await self._send(lambda client: client.post(url, json=payload))
        latency_ms = int((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            raise ProviderError(f"google returned {response.status_code}: {response.text[:500]}")
        data = response.json()
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        content = "".join(part.get("text", "") for part in parts)
        usage_data = data.get("usageMetadata") or {}
        usage = UsageMetadata(
            prompt_tokens=usage_data.get("promptTokenCount"),
            completion_tokens=usage_data.get("candidatesTokenCount"),
            total_tokens=usage_data.get("totalTokenCount"),
        )
        return content, usage, latency_ms


def build_adapters(settings: Any) -> dict[str, ProviderAdapter]:
    limit = max(1, int(getattr(settings, "max_concurrent_requests", 8)))
    shared = asyncio.Semaphore(limit)
    opts = {
        "timeout": float(getattr(settings, "provider_timeout_seconds", 90.0)),
        "max_retries": int(getattr(settings, "provider_max_retries", 2)),
        "semaphore": shared,
    }
    return {
        "openrouter": OpenAICompatibleAdapter(settings.openrouter_api_key, "https://openrouter.ai/api/v1", **opts),
        "openai": OpenAICompatibleAdapter(settings.openai_api_key, "https://api.openai.com/v1", **opts),
        "xai": OpenAICompatibleAdapter(settings.xai_api_key, "https://api.x.ai/v1", **opts),
        "anthropic": AnthropicAdapter(settings.anthropic_api_key, **opts),
        "google": GoogleAdapter(settings.google_api_key, **opts),
    }


def _usage_from_openai_compatible(usage: dict[str, Any] | None) -> UsageMetadata | None:
    if not usage:
        return None
    return UsageMetadata(
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        total_tokens=usage.get("total_tokens"),
        cost=usage.get("cost"),
    )
