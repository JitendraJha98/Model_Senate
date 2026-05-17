import type { AppConfig, CouncilRun, SenateRun } from "./types";

export async function getConfig(): Promise<AppConfig> {
  const response = await fetch("/api/config");
  if (!response.ok) throw new Error("Failed to load app config");
  return response.json();
}

export async function getConversations(): Promise<SenateRun[]> {
  const response = await fetch("/api/conversations");
  if (!response.ok) throw new Error("Failed to load conversations");
  return response.json();
}

export async function runSenate(payload: {
  prompt: string;
  selected_model_ids: string[];
  leader_model_id: string;
  system_context?: string;
}): Promise<SenateRun> {
  const response = await fetch("/api/senate/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Senate run failed" }));
    throw new Error(error.detail || "Senate run failed");
  }
  return response.json();
}

export async function startCouncil(payload: {
  prompt: string;
  selected_model_ids: string[];
  system_context?: string;
}): Promise<{ run_id: string }> {
  const response = await fetch("/api/council/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Council run failed" }));
    throw new Error(error.detail || "Council run failed");
  }
  return response.json();
}

export async function getCouncilRun(runId: string): Promise<CouncilRun> {
  const response = await fetch(`/api/council/run/${runId}`);
  if (!response.ok) throw new Error("Failed to load council run");
  return response.json();
}

export async function getCouncilRuns(): Promise<CouncilRun[]> {
  const response = await fetch("/api/council/runs");
  if (!response.ok) throw new Error("Failed to load council runs");
  return response.json();
}

