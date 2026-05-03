import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Bot, Check, Clock, Eye, KeyRound, Loader2, PanelRight, Send, Settings, Sparkles, X } from "lucide-react";
import { getConfig, getConversations, runSenate } from "./api";
import type { AppConfig, ModelOutput, ModelRoute, PeerReview, SenateRun } from "./types";

const SAMPLE_PROMPT =
  "Compare the strongest arguments for and against investing in renewable energy infrastructure over the next decade.";

export default function App() {
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [conversations, setConversations] = useState<SenateRun[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [leaderId, setLeaderId] = useState("");
  const [prompt, setPrompt] = useState("");
  const [systemContext, setSystemContext] = useState("");
  const [currentRun, setCurrentRun] = useState<SenateRun | null>(null);
  const [activeOpinion, setActiveOpinion] = useState(0);
  const [activeView, setActiveView] = useState<"answer" | "models" | "history">("answer");
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([getConfig(), getConversations()])
      .then(([loadedConfig, loadedConversations]) => {
        setConfig(loadedConfig);
        setConversations(loadedConversations);
        setSelectedIds(loadedConfig.defaults.selected_model_ids);
        setLeaderId(loadedConfig.defaults.leader_model_id);
        setCurrentRun(loadedConversations[0] ?? null);
      })
      .catch((err: Error) => setError(err.message));
  }, []);

  const selectedModels = useMemo(
    () => config?.models.filter((model) => selectedIds.includes(model.id)) ?? [],
    [config, selectedIds]
  );
  const canRun = prompt.trim().length > 0 && selectedIds.length >= 3 && leaderId && !isRunning;

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
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <strong>{selectedIds.length} models selected</strong>
            <span>{leaderId ? `Leader: ${config?.models.find((model) => model.id === leaderId)?.display_name}` : "Pick a leader"}</span>
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
          <ConversationHistory conversations={conversations} onSelect={(run) => {
            setCurrentRun(run);
            setActiveView("answer");
          }} />
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
      </section>
    </main>
  );
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
  return (
    <section className="results">
      <article className="final-answer">
        <div className="panel-heading">
          <h2>Final synthesis</h2>
          <p>{run.final_synthesis.leader_display_name} · {run.total_latency_ms} ms</p>
        </div>
        {run.final_synthesis.status === "completed" ? (
          <ReactMarkdown>{run.final_synthesis.content}</ReactMarkdown>
        ) : (
          <div className="error">{run.final_synthesis.error}</div>
        )}
      </article>

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
            {run.peer_reviews.map((review) => <ReviewView key={review.reviewer_model_id} review={review} />)}
            {run.peer_reviews.length === 0 && <p className="muted">Peer review needs at least two successful first opinions.</p>}
          </div>
        </article>
      </div>
    </section>
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

function ReviewView({ review }: { review: PeerReview }) {
  return (
    <div className="review">
      <h3><Eye size={16} /> {review.reviewer_display_name}</h3>
      {review.status === "completed" ? <ReactMarkdown>{review.content}</ReactMarkdown> : <div className="error">{review.error}</div>}
      <details>
        <summary>Reveal anonymous map</summary>
        {Object.entries(review.anonymized_map).map(([alias, modelId]) => (
          <div key={alias} className="map-row"><span>{alias}</span><code>{modelId}</code></div>
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

function ConversationHistory({ conversations, onSelect }: { conversations: SenateRun[]; onSelect: (run: SenateRun) => void }) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Conversation history</h2>
        <p>Stored locally as JSON files.</p>
      </div>
      <div className="wide-list">
        {conversations.map((run) => (
          <button key={run.id} onClick={() => onSelect(run)}>
            <span>{run.prompt}</span>
            <small>{run.status} · {new Date(run.created_at).toLocaleString()}</small>
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

