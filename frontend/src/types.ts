export type ProviderName = "openrouter" | "openai" | "anthropic" | "google" | "xai";

export interface ModelRoute {
  id: string;
  provider: ProviderName;
  model: string;
  display_name: string;
  enabled: boolean;
  supports_streaming: boolean;
  missing_key: boolean;
}

export interface AppConfig {
  models: ModelRoute[];
  defaults: {
    selected_model_ids: string[];
    leader_model_id: string;
    min_models: number;
    council_selected_model_ids?: string[];
    council_min_models?: number;
  };
}

export interface ModelOutput {
  model_id: string;
  display_name: string;
  provider: ProviderName;
  status: "completed" | "failed";
  content: string;
  error?: string;
  latency_ms?: number;
}

export interface RankingEntry {
  rank: number;
  response_label: string;
  model_id?: string;
  display_name?: string;
  reason?: string;
}

export interface AggregateRanking {
  model_id: string;
  display_name: string;
  average_rank: number;
  vote_count: number;
  first_place_votes: number;
  best_rank?: number;
  worst_rank?: number;
  confidence_score: number;
}

export interface PeerReview {
  reviewer_model_id: string;
  reviewer_display_name: string;
  status: "completed" | "failed";
  anonymized_map: Record<string, string>;
  parsed_ranking: RankingEntry[];
  content: string;
  error?: string;
  latency_ms?: number;
}

export interface FinalSynthesis {
  leader_model_id: string;
  leader_display_name: string;
  status: "completed" | "failed";
  content: string;
  error?: string;
  latency_ms?: number;
}

export interface SenateRun {
  id: string;
  status: "completed" | "partial_failed" | "failed";
  created_at: string;
  completed_at: string;
  prompt: string;
  selected_models: ModelRoute[];
  leader_model: ModelRoute;
  first_opinions: ModelOutput[];
  peer_reviews: PeerReview[];
  aggregate_rankings: AggregateRanking[];
  final_synthesis: FinalSynthesis;
  errors: string[];
  total_latency_ms: number;
  metadata: Record<string, unknown>;
}

export interface OrchestrationPlan {
  query_type: "factual" | "analytical" | "code" | "ethics" | "creative" | "multi_part";
  is_multi_part: boolean;
  sub_questions: string[];
  role_assignments: Record<string, string>;
  tool_assignments: Record<string, string[]>;
  decomposition_rationale: string;
  orchestration_status: "completed" | "fallback";
}

export interface Claim {
  id: string;
  text: string;
  verification_status: "verified" | "partially_verified" | "unverified" | "disputed";
  source_model_id?: string;
}

export interface AgentOpinion {
  model_id: string;
  display_name: string;
  provider: ProviderName;
  role: string;
  status: "completed" | "failed" | "parse_failed";
  answer: string;
  confidence?: number;
  key_claims: Claim[];
  assumptions: string[];
  uncertainties: string[];
  raw_content: string;
  error?: string;
  latency_ms?: number;
}

export interface CouncilCritique {
  reviewer_model_id: string;
  reviewer_display_name: string;
  target_model_id: string;
  target_display_name: string;
  critique_role: string;
  status: "completed" | "failed" | "parse_failed";
  scores?: {
    accuracy: number;
    logic: number;
    completeness: number;
    calibration: number;
  };
  strengths: string[];
  weaknesses: string[];
  flags: string[];
  raw_content: string;
  error?: string;
}

export interface LeaderElection {
  leader_model_id: string;
  leader_display_name: string;
  validator_model_id?: string;
  validator_display_name?: string;
  candidates: {
    model_id: string;
    display_name: string;
    score: number;
    rank_score: number;
    calibration_score: number;
    tool_verification_score: number;
    first_place_votes: number;
  }[];
  rationale: string;
}

export interface CouncilSynthesis {
  leader_model_id: string;
  leader_display_name: string;
  status: "completed" | "failed";
  direct_answer: string;
  consensus: string[];
  dissent: string[];
  unresolved: string[];
  confidence_grade?: "A" | "B" | "C" | "D" | "F";
  raw_content: string;
  error?: string;
}

export interface SynthesisValidation {
  validator_model_id?: string;
  validator_display_name?: string;
  status: "approved" | "approved_with_caveats" | "flagged" | "failed";
  issues: string[];
  addendum?: string;
  raw_content: string;
  error?: string;
}

export interface CouncilRun {
  id: string;
  status: "completed" | "approved_with_caveats" | "partial_failed" | "failed";
  orchestration_plan: OrchestrationPlan;
  agent_opinions: AgentOpinion[];
  council_critiques: CouncilCritique[];
  leader_election?: LeaderElection;
  synthesis?: CouncilSynthesis;
  validation?: SynthesisValidation;
  confidence_grade?: "A" | "B" | "C" | "D" | "F";
  created_at: string;
  completed_at: string;
  prompt: string;
  selected_models: ModelRoute[];
  errors: string[];
  total_latency_ms: number;
  metadata: Record<string, unknown>;
}
