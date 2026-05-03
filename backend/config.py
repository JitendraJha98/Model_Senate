from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.schemas import ModelRoute, ProviderName

load_dotenv()


class Settings(BaseSettings):
    openrouter_api_key: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    xai_api_key: str | None = None
    frontend_origin: str = "http://localhost:5173"
    model_senate_host: str = "127.0.0.1"
    model_senate_port: int = 8000
    data_dir: Path = Path("data/conversations")
    model_senate_routes: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


DEFAULT_ROUTES = [
    ModelRoute(
        id="openrouter-gpt-5-2",
        provider="openrouter",
        model="openai/gpt-5.2",
        display_name="GPT-5.2 via OpenRouter",
        supports_streaming=True,
    ),
    ModelRoute(
        id="openrouter-gemini-3-pro",
        provider="openrouter",
        model="google/gemini-3-pro-preview",
        display_name="Gemini 3 Pro via OpenRouter",
        supports_streaming=True,
    ),
    ModelRoute(
        id="openrouter-claude-sonnet-4-5",
        provider="openrouter",
        model="anthropic/claude-sonnet-4.5",
        display_name="Claude Sonnet 4.5 via OpenRouter",
        supports_streaming=True,
    ),
    ModelRoute(
        id="openrouter-grok-4",
        provider="openrouter",
        model="x-ai/grok-4",
        display_name="Grok 4 via OpenRouter",
        supports_streaming=True,
    ),
    ModelRoute(id="openai-gpt-5-2", provider="openai", model="gpt-5.2", display_name="GPT-5.2 Direct"),
    ModelRoute(
        id="anthropic-claude-sonnet-4-5",
        provider="anthropic",
        model="claude-sonnet-4-5",
        display_name="Claude Sonnet 4.5 Direct",
    ),
    ModelRoute(
        id="google-gemini-3-pro",
        provider="google",
        model="gemini-3-pro-preview",
        display_name="Gemini 3 Pro Direct",
    ),
    ModelRoute(id="xai-grok-4", provider="xai", model="grok-4", display_name="Grok 4 Direct"),
]


def provider_has_key(settings: Settings, provider: ProviderName) -> bool:
    return bool(
        {
            "openrouter": settings.openrouter_api_key,
            "openai": settings.openai_api_key,
            "anthropic": settings.anthropic_api_key,
            "google": settings.google_api_key,
            "xai": settings.xai_api_key,
        }[provider]
    )


def _load_custom_routes(settings: Settings) -> list[ModelRoute] | None:
    raw = settings.model_senate_routes or os.getenv("MODEL_SENATE_ROUTES")
    if not raw:
        return None
    data = json.loads(raw)
    return [ModelRoute.model_validate(item) for item in data]


def load_model_routes(settings: Settings) -> list[ModelRoute]:
    routes = _load_custom_routes(settings) or DEFAULT_ROUTES
    hydrated: list[ModelRoute] = []
    for route in routes:
        hydrated.append(route.model_copy(update={"missing_key": not provider_has_key(settings, route.provider)}))
    return hydrated


@lru_cache
def get_settings() -> Settings:
    return Settings()

