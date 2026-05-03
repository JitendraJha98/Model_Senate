from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ProviderName = Literal["openrouter", "openai", "anthropic", "google", "xai"]
RunStatus = Literal["completed", "partial_failed", "failed"]


class ModelRoute(BaseModel):
    id: str
    provider: ProviderName
    model: str
    display_name: str
    enabled: bool = True
    supports_streaming: bool = False
    missing_key: bool = False


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class SenateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    selected_model_ids: list[str] = Field(min_length=3)
    leader_model_id: str
    system_context: str | None = None


class UsageMetadata(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost: float | None = None


class ModelOutput(BaseModel):
    model_id: str
    display_name: str
    provider: ProviderName
    status: Literal["completed", "failed"]
    content: str = ""
    error: str | None = None
    latency_ms: int | None = None
    usage: UsageMetadata | None = None


class PeerReview(BaseModel):
    reviewer_model_id: str
    reviewer_display_name: str
    status: Literal["completed", "failed"]
    anonymized_map: dict[str, str] = Field(default_factory=dict)
    content: str = ""
    error: str | None = None
    latency_ms: int | None = None


class FinalSynthesis(BaseModel):
    leader_model_id: str
    leader_display_name: str
    status: Literal["completed", "failed"]
    content: str = ""
    error: str | None = None
    latency_ms: int | None = None


class SenateRun(BaseModel):
    id: str
    status: RunStatus
    created_at: datetime
    completed_at: datetime
    prompt: str
    selected_models: list[ModelRoute]
    leader_model: ModelRoute
    first_opinions: list[ModelOutput]
    peer_reviews: list[PeerReview]
    final_synthesis: FinalSynthesis
    errors: list[str] = Field(default_factory=list)
    total_latency_ms: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class AppConfigResponse(BaseModel):
    models: list[ModelRoute]
    defaults: dict[str, Any]

