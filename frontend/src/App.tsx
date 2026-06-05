import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Bot, Check, Clock, Eye, KeyRound, Loader2, Moon, PanelRight, Send, Settings, Sparkles, Sun, X } from "lucide-react";
import { getConfig, getConversations, getCouncilRun, getCouncilRuns, runSenate, startCouncil } from "./api";
import { useCouncilStream } from "./hooks/useCouncilStream";
import type {
  AggregateRanking,
  AppConfig,
  CouncilRun,
  ModelOutput,
  ModelRoute,
  PeerReview,
  SenateRun
} from "./types";
import type { CouncilStreamState } from "./hooks/useCouncilStream";

const SAMPLE_PROMPT =
  "Compare the strongest arguments for and against investing in renewable energy infrastructure over the next decade.";

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [conversations, setConversations] = useState<SenateRun[]>([]);
  const [councilRuns, setCouncilRuns] = useState<CouncilRun[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [leaderId, setLeaderId] = useState("");
  const [prompt, setPrompt] = useState("");
  const [systemContext, setSystemContext] = useState("");
  const [currentRun, setCurrentRun] = useState<SenateRun | null>(null);
  const [currentCouncilRun, setCurrentCouncilRun] = useState<CouncilRun | null>(null);
  const [councilRunId, setCouncilRunId] = useState<string | null>(null);
  const councilStream = useCouncilStream(councilRunId);
  const [activeOpinion, setActiveOpinion] = useState(0);
  const [activeView, setActiveView] = useState<"answer" | "council" | "models" | "history">("answer");
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState("");
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    const saved = typeof localStorage !== "undefined" ? localStorage.getItem("ms-theme") : null;
    if (saved === "light" || saved === "dark") return saved;
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("ms-theme", theme);
  }, [theme]);

  useEffect(() => {
    Promise.all([getConfig(), getConversations(), getCouncilRuns()])
      .then(([loadedConfig, loadedConversations, loadedCouncilRuns]) => {
        setConfig(loadedConfig);
        setConversations(loadedConversations);
        setCouncilRuns(loadedCouncilRuns);
        setSelectedIds(loadedConfig.defaults.selected_model_ids);
        setLeaderId(loadedConfig.defaults.leader_model_id);
        setCurrentRun(loadedConversations[0] ?? null);
        setCurrentCouncilRun(loadedCouncilRuns[0] ?? null);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  const selectedModels = useMemo(
    () => config?.models.filter((model) => selectedIds.includes(model.id)) ?? [],
    [config, selectedIds]
  );
  const canRun = prompt.trim().length > 0 && selectedIds.length >= 3 && leaderId && !isRunning;
  const canRunCouncil = prompt.trim().length > 0 && selectedIds.length >= (config?.defaults.council_min_models ?? 2) && !isRunning;

  async function submit() {
    if (!canRun) return;
    setIsRunning(true);
    setError("");
    setCurrentRun(null);
    try {
      const run = await runSenate({
        prompt,
        selected_model_ids: selectedIds,
        leader_model_id: leaderId,
        system_context: systemContext || undefined
      });
      setCurrentRun(run);
      setConversations((items) => [run, ...items.filter((item) => item.id !== run.id)]);
      setActiveOpinion(0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Senate run failed");
    } finally {
      setIsRunning(false);
    }
  }

  async function submitCouncil() {
    if (!canRunCouncil) return;
    setIsRunning(true);
    setError("");
    setCurrentCouncilRun(null);
    try {
      const { run_id } = await startCouncil({
        prompt,
        selected_model_ids: selectedIds,
        system_context: systemContext || undefined
      });
      // Drive the live SSE progress view…
      setCouncilRunId(run_id);
      // …while polling for the authoritative persisted run as the source of truth.
      const run = await waitForCouncilRun(run_id);
      setCurrentCouncilRun(run);
      setCouncilRuns((items) => [run, ...items.filter((item) => item.id !== run.id)]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Council run failed");
    } finally {
      setCouncilRunId(null);
      setIsRunning(false);
    }
  }

  function toggleModel(model: ModelRoute) {
    setSelectedIds((ids) => (ids.includes(model.id) ? ids.filter((id) => id !== model.id) : [...ids, model.id]));
    if (leaderId === model.id && selectedIds.includes(model.id)) {
      setLeaderId(selectedIds.find((id) => id !== model.id) ?? "");
    }
  }

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">MS</div>
          <div>
            <h1>Model_Senate</h1>
            <p>Multiple models. One researched answer.</p>
          </div>
        </div>

        <nav className="nav">
          <button className={activeView === "answer" ? "active" : ""} onClick={() => setActiveView("answer")}>
            <Sparkles size={18} /> Senate
          </button>
          <button className={activeView === "council" ? "active" : ""} onClick={() => setActiveView("council")}>
            <Sparkles size={18} /> Council
          </button>
          <button className={activeView === "models" ? "active" : ""} onClick={() => setActiveView("models")}>
            <Settings size={18} /> Models
          </button>
          <button className={activeView === "history" ? "active" : ""} onClick={() => setActiveView("history")}>
            <Clock size={18} /> History
          </button>
        </nav>

        <section className="history-list">
          <div className="section-title">Recent runs</div>
          {conversations.slice(0, 8).map((run) => (
            <button key={run.id} className="history-item" onClick={() => setCurrentRun(run)}>
              <span>{run.prompt}</span>
              <small>{new Date(run.created_at).toLocaleString()}</small>
            </button>
          ))}
        </section>

        <button
          className="theme-toggle"
          onClick={() => setTheme((value) => (value === "dark" ? "light" : "dark"))}
          aria-label="Toggle color theme"
        >
          {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
          {theme === "dark" ? "Light chamber" : "Night chamber"}
        </button>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <strong>{selectedIds.length} models selected</strong>
            <span>
              {leaderId
                ? `Leader: ${config?.models.find((model) => model.id === leaderId)?.display_name}`
                : "Pick a leader"}
            </span>
          </div>
          <StatusBadge isRunning={isRunning} run={currentRun} />
        </header>

        {activeView === "models" && config && (
          <ModelSettings
            models={config.models}
            selectedIds={selectedIds}
            leaderId={leaderId}
            onToggle={toggleModel}
            onLeaderChange={setLeaderId}
          />
        )}

        {activeView === "history" && (
          <ConversationHistory
            conversations={conversations}
            councilRuns={councilRuns}
            onSelect={(run) => {
              setCurrentRun(run);
              setActiveView("answer");
            }}
            onCouncilSelect={(run) => {
              setCurrentCouncilRun(run);
              setActiveView("council");
            }}
          />
        )}

        {activeView === "answer" && (
          <>
            <section className="composer">
              <textarea
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                placeholder={SAMPLE_PROMPT}
                rows={4}
              />
              <textarea
                value={systemContext}
                onChange={(event) => setSystemContext(event.target.value)}
                placeholder="Optional context, constraints, source notes, or audience..."
                rows={2}
              />
              <div className="composer-actions">
                <div className={selectedIds.length >= 3 ? "hint ok" : "hint"}>
                  {selectedIds.length >= 3 ? <Check size={16} /> : <X size={16} />} Select at least 3 models
                </div>
                <button className="primary" disabled={!canRun} onClick={submit}>
                  {isRunning ? <Loader2 className="spin" size={18} /> : <Send size={18} />} Run Senate
                </button>
              </div>
              {error && <div className="error">{error}</div>}
            </section>

            {isRunning && <LoadingRun selectedModels={selectedModels} />}
            {currentRun && !isRunning && (
              <Results run={currentRun} activeOpinion={activeOpinion} onOpinionChange={setActiveOpinion} />
            )}
            {!currentRun && !isRunning && <EmptyState />}
          </>
        )}

        {activeView === "council" && (
          <>
            <section className="composer">
              <textarea
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                placeholder={SAMPLE_PROMPT}
                rows={4}
              />
              <textarea
                value={systemContext}
                onChange={(event) => setSystemContext(event.target.value)}
                placeholder="Optional context, constraints, source notes, or audience..."
                rows={2}
              />
              <div className="composer-actions">
                <div className={canRunCouncil ? "hint ok" : "hint"}>
                  {canRunCouncil ? <Check size={16} /> : <X size={16} />} Select at least {config?.defaults.council_min_models ?? 2} models
                </div>
                <button className="primary" disabled={!canRunCouncil} onClick={submitCouncil}>
                  {isRunning ? <Loader2 className="spin" size={18} /> : <Send size={18} />} Run Council
                </button>
              </div>
              {error && <div className="error">{error}</div>}
            </section>
            {isRunning && <CouncilLiveProgress stream={councilStream} selectedModels={selectedModels} />}
            {currentCouncilRun && !isRunning && <CouncilResults run={currentCouncilRun} />}
            {!currentCouncilRun && !isRunning && <EmptyState />}
          </>
        )}
      </section>
    </main>
  );
}

function runMeta(latencyMs: number, tokens: number, costUsd?: number | null): string {
  const parts = [`${(latencyMs / 1000).toFixed(1)}s`];
  if (tokens) parts.push(`${tokens.toLocaleString()} tokens`);
  if (costUsd != null) parts.push(`$${costUsd.toFixed(costUsd < 0.01 ? 4 : 2)}`);
  return parts.join(" · ");
}

async function waitForCouncilRun(runId: string): Promise<CouncilRun> {
  for (let attempt = 0; attempt < 360; attempt += 1) {
    try {
      return await getCouncilRun(runId);
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  }
  throw new Error("Council run did not complete in time");
}

function StatusBadge({ isRunning, run }: { isRunning: boolean; run: SenateRun | null }) {
  if (isRunning) return <div className="badge running"><Loader2 className="spin" size={16} /> Running</div>;
  if (!run) return <div className="badge">Ready</div>;
  return <div className={`badge ${run.status}`}>{run.status.replace("_", " ")}</div>;
}

function ModelSettings({
  models,
  selectedIds,
  leaderId,
  onToggle,
  onLeaderChange
}: {
  models: ModelRoute[];
  selectedIds: string[];
  leaderId: string;
  onToggle: (model: ModelRoute) => void;
  onLeaderChange: (id: string) => void;
}) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Model routes</h2>
        <p>Keys are read from local environment variables and are never shown here.</p>
      </div>
      <div className="model-grid">
        {models.map((model) => (
          <article className={selectedIds.includes(model.id) ? "model-card selected" : "model-card"} key={model.id}>
            <div>
              <h3>{model.display_name}</h3>
              <p>{model.provider} / {model.model}</p>
            </div>
            <div className="model-actions">
              {model.missing_key && <span className="key-warning"><KeyRound size={14} /> missing key</span>}
              <label>
                <input type="checkbox" checked={selectedIds.includes(model.id)} onChange={() => onToggle(model)} />
                Active
              </label>
              <label>
                <input
                  type="radio"
                  name="leader"
                  checked={leaderId === model.id}
                  disabled={!selectedIds.includes(model.id)}
                  onChange={() => onLeaderChange(model.id)}
                />
                Leader
              </label>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function Results({
  run,
  activeOpinion,
  onOpinionChange
}: {
  run: SenateRun;
  activeOpinion: number;
  onOpinionChange: (index: number) => void;
}) {
  const opinion = run.first_opinions[activeOpinion] ?? run.first_opinions[0];
  const modelsById = new Map(run.selected_models.map((model) => [model.id, model.display_name]));
  return (
    <section className="results">
      <article className="final-answer">
        <div className="panel-heading">
          <h2>Final synthesis</h2>
          <p>{run.final_synthesis.leader_display_name} · {runMeta(run.total_latency_ms, run.total_tokens, run.total_cost_usd)}</p>
        </div>
        {run.final_synthesis.status === "completed" ? (
          <ReactMarkdown>{run.final_synthesis.content}</ReactMarkdown>
        ) : (
          <div className="error">{run.final_synthesis.error}</div>
        )}
      </article>

      <AggregateRankings rankings={run.aggregate_rankings} />

      <div className="detail-grid">
        <article className="panel">
          <div className="panel-heading">
            <h2>First opinions</h2>
            <p>Inspect each independent answer.</p>
          </div>
          <div className="tabs">
            {run.first_opinions.map((item, index) => (
              <button className={activeOpinion === index ? "active" : ""} key={item.model_id} onClick={() => onOpinionChange(index)}>
                {item.status === "completed" ? <Check size={14} /> : <X size={14} />}
                {item.display_name}
              </button>
            ))}
          </div>
          {opinion && <OpinionView opinion={opinion} />}
        </article>

        <article className="panel">
          <div className="panel-heading">
            <h2>Peer review</h2>
            <p>Anonymized rankings, revealed after completion.</p>
          </div>
          <div className="review-list">
            <p className="muted">Models saw anonymous labels only. Names below are revealed after completion for readability and auditability.</p>
            {run.peer_reviews.map((review) => (
              <ReviewView key={review.reviewer_model_id} review={review} modelsById={modelsById} />
            ))}
            {run.peer_reviews.length === 0 && <p className="muted">Peer review needs at least two successful first opinions.</p>}
          </div>
        </article>
      </div>
    </section>
  );
}

function AggregateRankings({ rankings }: { rankings: AggregateRanking[] }) {
  if (rankings.length === 0) return null;
  return (
    <article className="panel aggregate-panel">
      <div className="panel-heading">
        <h2>Senate ranking</h2>
        <p>Average anonymous peer position. Lower rank is better.</p>
      </div>
      <div className="ranking-grid">
        {rankings.map((ranking, index) => (
          <div className="ranking-card" key={ranking.model_id}>
            <div className="rank-number">{index + 1}</div>
            <div>
              <strong>{ranking.display_name}</strong>
              <div className="rank-meter" aria-label={`Confidence ${Math.round(ranking.confidence_score * 100)} percent`}>
                <span style={{ width: `${Math.round(ranking.confidence_score * 100)}%` }} />
              </div>
              <small>
                Avg {ranking.average_rank} - {ranking.vote_count} votes - {ranking.first_place_votes} first-place
              </small>
            </div>
          </div>
        ))}
      </div>
    </article>
  );
}

function OpinionView({ opinion }: { opinion: ModelOutput }) {
  if (opinion.status === "failed") return <div className="error">{opinion.error}</div>;
  return (
    <div className="markdown">
      <ReactMarkdown>{opinion.content}</ReactMarkdown>
    </div>
  );
}

function ReviewView({ review, modelsById }: { review: PeerReview; modelsById: Map<string, string> }) {
  return (
    <div className="review">
      <h3><Eye size={16} /> {review.reviewer_display_name}</h3>
      {review.status === "completed" ? <ReactMarkdown>{review.content}</ReactMarkdown> : <div className="error">{review.error}</div>}
      {review.parsed_ranking.length > 0 && (
        <div className="extracted-ranking">
          <strong>Extracted ranking</strong>
          {review.parsed_ranking.map((entry) => (
            <div className="ranking-row" key={`${review.reviewer_model_id}-${entry.rank}`}>
              <span>{entry.rank}. {entry.response_label}</span>
              <b>{entry.model_id ? modelsById.get(entry.model_id) ?? entry.model_id : "Unknown model"}</b>
              {entry.reason && <small>{entry.reason}</small>}
            </div>
          ))}
        </div>
      )}
      <details>
        <summary>Reveal anonymous map</summary>
        {Object.entries(review.anonymized_map).map(([alias, modelId]) => (
          <div key={alias} className="map-row">
            <span>{alias}</span>
            <code>{modelsById.get(modelId) ?? modelId}</code>
          </div>
        ))}
      </details>
    </div>
  );
}

function LoadingRun({ selectedModels }: { selectedModels: ModelRoute[] }) {
  return (
    <section className="loading-run">
      {["First opinions", "Anonymous peer review", "Leader synthesis"].map((stage, index) => (
        <div className="stage" key={stage}>
          <Loader2 className="spin" size={18} />
          <strong>{stage}</strong>
          <span>{index === 0 ? selectedModels.map((model) => model.display_name).join(", ") : "Queued in the Senate pipeline"}</span>
        </div>
      ))}
    </section>
  );
}

function CouncilLiveProgress({
  stream,
  selectedModels
}: {
  stream: CouncilStreamState;
  selectedModels: ModelRoute[];
}) {
  const total = selectedModels.length || 1;
  const stages: { label: string; done: boolean; detail: string }[] = [
    {
      label: "Orchestration",
      done: stream.plan !== null,
      detail: stream.plan ? `Query type: ${stream.plan.query_type}` : "Classifying the query…"
    },
    {
      label: "First opinions",
      done: stream.opinions.length >= total,
      detail: `${stream.opinions.length}/${total} models responded`
    },
    {
      label: "Cross critique",
      done: stream.critiques.length > 0,
      detail: stream.critiques.length > 0 ? `${stream.critiques.length} critiques scored` : "Peers reviewing each other…"
    },
    {
      label: "Leader election",
      done: stream.election !== null,
      detail: stream.election ? `Elected ${stream.election.elected_display_name}` : "Scoring candidates…"
    },
    {
      label: "Synthesis",
      done: stream.synthesis !== null,
      detail: stream.synthesis ? `By ${stream.synthesis.leader_display_name}` : "Awaiting election…"
    },
    {
      label: "Validation",
      done: stream.validation !== null,
      detail: stream.validation ? `Verdict: ${stream.validation.verdict ?? stream.validation.status}` : "Awaiting synthesis…"
    }
  ];

  // The first stage that is not yet done is the one currently in flight.
  const activeIndex = stages.findIndex((stage) => !stage.done);

  const nameFor = (modelId: string) =>
    selectedModels.find((model) => model.id === modelId)?.display_name ?? modelId;
  const settledIds = new Set(stream.opinions.map((opinion) => opinion.model_id));
  const drafting = Object.entries(stream.opinionDrafts).filter(([modelId]) => !settledIds.has(modelId));

  return (
    <section className="results">
      <section className="loading-run">
        {stages.map((stage, index) => (
          <div className="stage" key={stage.label}>
            {stage.done ? (
              <Check size={18} />
            ) : index === activeIndex ? (
              <Loader2 className="spin" size={18} />
            ) : (
              <Clock size={18} />
            )}
            <strong>{stage.label}</strong>
            <span>{stage.detail}</span>
          </div>
        ))}
      </section>

      {drafting.length > 0 && (
        <article className="panel">
          <div className="panel-heading">
            <h2>Live drafting</h2>
            <p>Token-by-token output as each model thinks.</p>
          </div>
          <div className="review-list">
            {drafting.map(([modelId, text]) => (
              <div className="review" key={modelId}>
                <h3>
                  <Loader2 className="spin" size={16} /> {nameFor(modelId)}
                </h3>
                <p className="muted typing">{text}</p>
              </div>
            ))}
          </div>
        </article>
      )}

      {stream.opinions.length > 0 && (
        <article className="panel">
          <div className="panel-heading">
            <h2>Opinions arriving live</h2>
            <p>Streamed straight from the pipeline as each model finishes.</p>
          </div>
          <div className="review-list">
            {stream.opinions.map((opinion) => (
              <div className="review" key={opinion.model_id}>
                <h3>
                  {opinion.status === "failed" ? <X size={16} /> : <Check size={16} />} {opinion.display_name} — {opinion.role}
                </h3>
                {opinion.status === "failed" ? (
                  <div className="error">{opinion.error}</div>
                ) : (
                  <p className="muted">{opinion.answer_summary || `${opinion.content.slice(0, 240)}…`}</p>
                )}
              </div>
            ))}
          </div>
        </article>
      )}
    </section>
  );
}

function CouncilResults({ run }: { run: CouncilRun }) {
  const isMultiPart = run.reintegration != null;
  return (
    <section className="results">
      {isMultiPart && run.reintegration ? (
        <article className="final-answer">
          <div className="panel-heading">
            <h2>Re-integrated answer</h2>
            <p>
              {run.reintegration.display_name} · {run.sub_runs.length} sub-questions · grade{" "}
              {run.confidence_grade ?? "—"} · {runMeta(run.total_latency_ms, run.total_tokens, run.total_cost_usd)}
            </p>
          </div>
          <ReactMarkdown>{run.reintegration.unified_answer || "No unified answer produced."}</ReactMarkdown>
          {run.reintegration.contradictions_unresolved.length > 0 && (
            <div className="extracted-ranking">
              <strong>Unresolved contradictions</strong>
              <ul>
                {run.reintegration.contradictions_unresolved.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </div>
          )}
        </article>
      ) : (
        <article className="final-answer">
          <div className="panel-heading">
            <h2>Model Council synthesis</h2>
            <p>
              {run.synthesis?.leader_display_name ?? "No leader"} · grade{" "}
              {run.confidence_grade ?? "—"} · {runMeta(run.total_latency_ms, run.total_tokens, run.total_cost_usd)}
            </p>
          </div>
          {run.synthesis?.status === "completed" ? (
            <>
              <ReactMarkdown>{run.synthesis.direct_answer}</ReactMarkdown>
              {run.synthesis.unresolved_conflicts.length > 0 && (
                <div className="extracted-ranking">
                  <strong>Unresolved conflicts</strong>
                  <ul>
                    {run.synthesis.unresolved_conflicts.map((c, i) => (
                      <li key={i}>{c}</li>
                    ))}
                  </ul>
                </div>
              )}
              {run.synthesis.recommended_next_checks.length > 0 && (
                <div className="extracted-ranking">
                  <strong>Recommended next checks</strong>
                  <ul>
                    {run.synthesis.recommended_next_checks.map((c, i) => (
                      <li key={i}>{c}</li>
                    ))}
                  </ul>
                </div>
              )}
              {run.validation && (
                <p className="muted">
                  Validation: {run.validation.verdict ?? run.validation.status}
                  {run.validation.issues.length > 0 && ` — ${run.validation.issues.join("; ")}`}
                  {run.validation.addendum && ` — ${run.validation.addendum}`}
                </p>
              )}
            </>
          ) : (
            <div className="error">{run.synthesis?.error ?? "Synthesis failed"}</div>
          )}
        </article>
      )}

      {isMultiPart && (
        <article className="panel">
          <div className="panel-heading">
            <h2>Sub-question answers</h2>
            <p>Each part was run through its own Council pipeline.</p>
          </div>
          <div className="review-list">
            {run.sub_runs.map((sub) => (
              <div className="review" key={sub.id}>
                <h3>
                  {sub.prompt} <small>(grade {sub.confidence_grade ?? "N/A"})</small>
                </h3>
                <ReactMarkdown>{sub.synthesis?.direct_answer || "No synthesis produced."}</ReactMarkdown>
              </div>
            ))}
          </div>
        </article>
      )}

      <article className="panel">
        <div className="panel-heading">
          <h2>Orchestration</h2>
          <p>{run.orchestration_plan.query_type} — {run.orchestration_plan.orchestration_status}</p>
        </div>
        <div className="wide-list">
          {Object.entries(run.orchestration_plan.role_assignments).map(([modelId, role]) => (
            <div className="ranking-row" key={modelId}>
              <span>{run.selected_models.find((m) => m.id === modelId)?.display_name ?? modelId}</span>
              <b>{role}</b>
            </div>
          ))}
        </div>
      </article>

      {run.leader_election && (
        <article className="panel aggregate-panel">
          <div className="panel-heading">
            <h2>Leader election</h2>
            <p>{run.leader_election.rationale}</p>
          </div>
          <div className="ranking-grid">
            {Object.entries(run.leader_election.all_scores)
              .sort(([, a], [, b]) => b - a)
              .map(([modelId, score], index) => {
                const breakdown = run.leader_election!.score_breakdown[modelId];
                const displayName =
                  run.selected_models.find((m) => m.id === modelId)?.display_name ?? modelId;
                const isElected = modelId === run.leader_election!.elected_model_id;
                return (
                  <div className="ranking-card" key={modelId}>
                    <div className="rank-number">{index + 1}{isElected ? " ★" : ""}</div>
                    <div>
                      <strong>{displayName}</strong>
                      <div
                        className="rank-meter"
                        aria-label={`Election score ${Math.round(score * 100)} percent`}
                      >
                        <span style={{ width: `${Math.round(score * 100)}%` }} />
                      </div>
                      <small>
                        score {score.toFixed(3)} | rank {breakdown?.rank_score?.toFixed(2)} |
                        calib {breakdown?.calibration_score?.toFixed(2)} |
                        tool {breakdown?.tool_verification_ratio?.toFixed(2)}
                      </small>
                    </div>
                  </div>
                );
              })}
          </div>
        </article>
      )}

      {!isMultiPart && <div className="detail-grid">
        <article className="panel">
          <div className="panel-heading">
            <h2>Agent opinions</h2>
            <p>Role-specific first answers.</p>
          </div>
          <div className="review-list">
            {run.agent_opinions.map((opinion) => (
              <div className="review" key={opinion.model_id}>
                <h3>
                  {opinion.display_name} — {opinion.role}
                  {opinion.confidence != null && (
                    <small> (confidence: {Math.round(opinion.confidence * 100)}%)</small>
                  )}
                </h3>
                {opinion.status === "failed" ? (
                  <div className="error">{opinion.error}</div>
                ) : (
                  <ReactMarkdown>
                    {opinion.answer_summary
                      ? `**Summary:** ${opinion.answer_summary}\n\n${opinion.content}`
                      : opinion.content}
                  </ReactMarkdown>
                )}
              </div>
            ))}
          </div>
        </article>
        <CritiqueHeatmap run={run} />
      </div>}

      {run.synthesis?.consensus_points && run.synthesis.consensus_points.length > 0 && (
        <article className="panel">
          <div className="panel-heading">
            <h2>Consensus &amp; Dissent</h2>
          </div>
          <div className="detail-grid">
            <div>
              <h4>Consensus</h4>
              <ul>{run.synthesis.consensus_points.map((p, i) => <li key={i}>{p}</li>)}</ul>
            </div>
            <div>
              <h4>Dissent</h4>
              <ul>{run.synthesis.dissent_points.map((p, i) => <li key={i}>{p}</li>)}</ul>
            </div>
          </div>
        </article>
      )}
    </section>
  );
}

function CritiqueHeatmap({ run }: { run: CouncilRun }) {
  const models = run.selected_models.filter((model) =>
    run.council_critiques.some(
      (c) => c.reviewer_model_id === model.id || c.target_model_id === model.id
    )
  );
  const byPair = new Map(
    run.council_critiques.map((c) => [`${c.reviewer_model_id}:${c.target_model_id}`, c])
  );

  const avgScore = (modelA: string, modelB: string): number | null => {
    const c = byPair.get(`${modelA}:${modelB}`);
    if (
      !c ||
      c.factual_accuracy_score == null ||
      c.logical_validity_score == null ||
      c.completeness_score == null ||
      c.calibration_score == null
    ) {
      return null;
    }
    return (
      (c.factual_accuracy_score +
        c.logical_validity_score +
        c.completeness_score +
        c.calibration_score) /
      4
    );
  };

  // Red (low) → gold → green (high)
  const cellColor = (value: number) => `hsl(${Math.round(value * 132)} 58% 72%)`;
  const short = (name: string) => name.split(" ")[0];

  return (
    <article className="panel">
      <div className="panel-heading">
        <h2>Critique heatmap</h2>
        <p>How each reviewer (row) scored each peer (column), averaged across all four axes.</p>
      </div>
      <div className="heatmap">
        <table>
          <thead>
            <tr>
              <th className="row-head">Reviewer ↓ / Target →</th>
              {models.map((model) => (
                <th key={model.id}>{short(model.display_name)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {models.map((reviewer) => (
              <tr key={reviewer.id}>
                <td className="row-head">{short(reviewer.display_name)}</td>
                {models.map((target) => {
                  if (reviewer.id === target.id) {
                    return (
                      <td className="heatmap-cell self" key={target.id}>
                        —
                      </td>
                    );
                  }
                  const score = avgScore(reviewer.id, target.id);
                  return (
                    <td
                      className="heatmap-cell"
                      key={target.id}
                      style={score != null ? { background: cellColor(score) } : undefined}
                    >
                      {score != null ? `${Math.round(score * 100)}` : "·"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="heatmap-legend">
        <span>weaker</span>
        <div className="bar" />
        <span>stronger</span>
      </div>
    </article>
  );
}

function ConversationHistory({
  conversations,
  councilRuns,
  onSelect,
  onCouncilSelect
}: {
  conversations: SenateRun[];
  councilRuns: CouncilRun[];
  onSelect: (run: SenateRun) => void;
  onCouncilSelect: (run: CouncilRun) => void;
}) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Conversation history</h2>
        <p>Stored locally as JSON files.</p>
      </div>
      <div className="wide-list">
        {councilRuns.map((run) => (
          <button key={run.id} onClick={() => onCouncilSelect(run)}>
            <span>{run.prompt}</span>
            <small>council - {run.status} - {new Date(run.created_at).toLocaleString()}</small>
          </button>
        ))}
        {conversations.map((run) => (
          <button key={run.id} onClick={() => onSelect(run)}>
            <span>{run.prompt}</span>
            <small>senate - {run.status} - {new Date(run.created_at).toLocaleString()}</small>
          </button>
        ))}
      </div>
    </section>
  );
}

function EmptyState() {
  return (
    <section className="empty">
      <Bot size={36} />
      <h2>Ask once. Compare many minds.</h2>
      <p>Choose your models, submit a research question, and Model_Senate will collect first opinions, run anonymous review, and synthesize the final answer.</p>
      <PanelRight size={22} />
    </section>
  );
}
