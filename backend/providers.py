from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

import httpx

from backend.schemas import ChatMessage, ModelRoute, UsageMetadata


class ProviderError(RuntimeError):
    pass


class ProviderAdapter(ABC):
    def __init__(self, api_key: str | None):
        self.api_key = api_key

    def ensure_key(self) -> str:
        if not self.api_key:
            raise ProviderError("Missing API key for provider")
        return self.api_key

    @abstractmethod
    async def complete(self, route: ModelRoute, messages: list[ChatMessage]) -> tuple[str, UsageMetadata | None, int]:
        raise NotImplementedError


class OpenAICompatibleAdapter(ProviderAdapter):
    def __init__(self, api_key: str | None, base_url: str, app_title: str = "Model_Senate"):
        super().__init__(api_key)
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
            "X-Title": self.app_title,
        }
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
        latency_ms = int((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            raise ProviderError(f"{route.provider} returned {response.status_code}: {response.text[:500]}")
        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage = _usage_from_openai_compatible(data.get("usage"))
        return content, usage, latency_ms


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
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post("https://api.anthropic.com/v1/messages", json=payload, headers=headers)
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
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(url, json=payload)
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
    return {
        "openrouter": OpenAICompatibleAdapter(settings.openrouter_api_key, "https://openrouter.ai/api/v1"),
        "openai": OpenAICompatibleAdapter(settings.openai_api_key, "https://api.openai.com/v1"),
        "xai": OpenAICompatibleAdapter(settings.xai_api_key, "https://api.x.ai/v1"),
        "anthropic": AnthropicAdapter(settings.anthropic_api_key),
        "google": GoogleAdapter(settings.google_api_key),
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

