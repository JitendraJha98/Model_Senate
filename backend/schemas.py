from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ProviderName = Literal["openrouter", "openai", "anthropic", "google", "xai"]
RunStatus = Literal["completed", "approved_with_caveats", "partial_failed", "failed"]
QueryType = Literal["factual", "analytical", "code", "ethics", "creative", "multi_part"]


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


class CouncilRequest(BaseModel):
    prompt: str = Field(min_length=1)
    selected_model_ids: list[str] = Field(min_length=2)
    system_context: str | None = None


class UsageMetadata(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost: float | None = None


class RankingEntry(BaseModel):
    rank: int
    response_label: str
    model_id: str | None = None
    display_name: str | None = None
    reason: str | None = None


class AggregateRanking(BaseModel):
    model_id: str
    display_name: str
    average_rank: float
    vote_count: int
    first_place_votes: int = 0
    best_rank: int | None = None
    worst_rank: int | None = None
    confidence_score: float


class ModelOutput(BaseModel):
    model_id: str
    display_name: str
    provider: ProviderName
    status: Literal["completed", "failed"]
    content: str = ""
    error: str | None = None
    latency_ms: int | None = None
    usage: UsageMetadata | None = None


class ToolResult(BaseModel):
    tool_name: str
    success: bool
    input: str
    output: str = ""
    error: str | None = None
    latency_ms: int | None = None


class Claim(BaseModel):
    id: str
    text: str
    verification_status: Literal["verified", "partially_verified", "unverified", "disputed"] = "unverified"
    source_model_id: str | None = None
    supporting_tool_results: list[str] = Field(default_factory=list)


class OrchestrationPlan(BaseModel):
    query_type: QueryType
    is_multi_part: bool = False
    sub_questions: list[str] = Field(default_factory=list)
    role_assignments: dict[str, str] = Field(default_factory=dict)
    tool_assignments: dict[str, list[str]] = Field(default_factory=dict)
    decomposition_rationale: str = ""
    orchestration_status: Literal["completed", "fallback"] = "completed"


class AgentOpinion(BaseModel):
    model_id: str
    display_name: str
    provider: ProviderName
    role: str
    status: Literal["completed", "failed", "parse_failed"]
    answer: str = ""
    confidence: float | None = Field(default=None, ge=0, le=1)
    key_claims: list[Claim] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    raw_content: str = ""
    error: str | None = None
    latency_ms: int | None = None
    usage: UsageMetadata | None = None


class CritiqueScore(BaseModel):
    accuracy: float = Field(ge=0, le=1)
    logic: float = Field(ge=0, le=1)
    completeness: float = Field(ge=0, le=1)
    calibration: float = Field(ge=0, le=1)

    @property
    def average(self) -> float:
        return (self.accuracy + self.logic + self.completeness + self.calibration) / 4


class CouncilCritique(BaseModel):
    reviewer_model_id: str
    reviewer_display_name: str
    target_model_id: str
    target_display_name: str
    critique_role: str
    status: Literal["completed", "failed", "parse_failed"]
    scores: CritiqueScore | None = None
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    raw_content: str = ""
    error: str | None = None
    latency_ms: int | None = None


class ElectionCandidate(BaseModel):
    model_id: str
    display_name: str
    score: float
    rank_score: float = 0
    calibration_score: float = 0
    tool_verification_score: float = 0
    first_place_votes: int = 0


class LeaderElection(BaseModel):
    leader_model_id: str
    leader_display_name: str
    validator_model_id: str | None = None
    validator_display_name: str | None = None
    candidates: list[ElectionCandidate] = Field(default_factory=list)
    rationale: str = ""


class ProvenanceEntry(BaseModel):
    claim_id: str
    claim: str
    source_model_ids: list[str] = Field(default_factory=list)
    reviewer_model_ids: list[str] = Field(default_factory=list)
    verification_status: Literal["verified", "partially_verified", "unverified", "disputed"] = "unverified"
    notes: str | None = None


class CouncilSynthesis(BaseModel):
    leader_model_id: str
    leader_display_name: str
    status: Literal["completed", "failed"]
    direct_answer: str = ""
    consensus: list[str] = Field(default_factory=list)
    dissent: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    confidence_grade: Literal["A", "B", "C", "D", "F"] | None = None
    provenance: dict[str, list[str]] = Field(default_factory=dict)
    raw_content: str = ""
    error: str | None = None
    latency_ms: int | None = None


class SynthesisValidation(BaseModel):
    validator_model_id: str | None = None
    validator_display_name: str | None = None
    status: Literal["approved", "approved_with_caveats", "flagged", "failed"]
    issues: list[str] = Field(default_factory=list)
    addendum: str | None = None
    raw_content: str = ""
    error: str | None = None
    latency_ms: int | None = None


class ReintegrationOutput(BaseModel):
    status: Literal["completed", "failed"]
    final_answer: str = ""
    contradictions: list[str] = Field(default_factory=list)
    raw_content: str = ""
    error: str | None = None


class CouncilRun(BaseModel):
    id: str
    status: RunStatus
    orchestration_plan: OrchestrationPlan
    agent_opinions: list[AgentOpinion]
    council_critiques: list[CouncilCritique]
    leader_election: LeaderElection | None = None
    synthesis: CouncilSynthesis | None = None
    validation: SynthesisValidation | None = None
    reintegration: ReintegrationOutput | None = None
    sub_runs: list["CouncilRun"] = Field(default_factory=list)
    provenance_tree: dict[str, ProvenanceEntry] = Field(default_factory=dict)
    confidence_grade: Literal["A", "B", "C", "D", "F"] | None = None
    created_at: datetime
    completed_at: datetime
    prompt: str
    selected_models: list[ModelRoute]
    errors: list[str] = Field(default_factory=list)
    total_latency_ms: int
    total_tokens: int = 0
    total_cost_usd: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PeerReview(BaseModel):
    reviewer_model_id: str
    reviewer_display_name: str
    status: Literal["completed", "failed"]
    anonymized_map: dict[str, str] = Field(default_factory=dict)
    parsed_ranking: list[RankingEntry] = Field(default_factory=list)
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
    aggregate_rankings: list[AggregateRanking] = Field(default_factory=list)
    final_synthesis: FinalSynthesis
    errors: list[str] = Field(default_factory=list)
    total_latency_ms: int
    metadata: dict[str, Any] = Field(default_factory=dict)


class AppConfigResponse(BaseModel):
    models: list[ModelRoute]
    defaults: dict[str, Any]
