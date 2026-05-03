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

export interface PeerReview {
  reviewer_model_id: string;
  reviewer_display_name: string;
  status: "completed" | "failed";
  anonymized_map: Record<string, string>;
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
  final_synthesis: FinalSynthesis;
  errors: string[];
  total_latency_ms: number;
  metadata: Record<string, unknown>;
}

