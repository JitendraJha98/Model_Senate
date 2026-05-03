import type { AppConfig, SenateRun } from "./types";

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

