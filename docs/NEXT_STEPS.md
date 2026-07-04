# Model Senate / Council — Next-Session Planning

> Companion to `docs/ROADMAP.md`. The ROADMAP covers **answer quality + proof** (eval
> harness, debate, calibration, cost/speed, provenance). This doc covers the axis the
> ROADMAP omits — **distribution / adoption** — plus signature **product ideas**. Together
> they are the path to "top in open source."
>
> **Strategy in one line:** the ROADMAP makes the council *provably better*; this doc makes
> it *effortlessly usable everywhere*. Do both and there is no comparable OSS project.

---

## 0. Status — where we are now

**Done (previous session): the pipeline-integrity fixes A1–A7.** These were prerequisites
for trustworthy benchmark numbers and are complete + tested (32 passing in a clean env):

| Fix | What changed | Key files |
|-----|--------------|-----------|
| A1 | Tools run in an agentic loop; results feed back into the answer | `council.py` `_run_opinion_with_tools`, `config.py` `COUNCIL_MAX_TOOL_ITERATIONS` |
| A2 | Native JSON mode (OpenAI `response_format`, Anthropic prefill, Gemini `responseMimeType`) on all JSON stages | `providers.py`, `council.py`, `orchestrator.py` |
| A3 | Adaptive election weights, rank normalized by n−1, parsed-first leadership, single-validator guard | `election.py`, `council.py` |
| A4 | Leader sees full opinions (removed `[:1500]` truncation) | `council.py` `_synthesis_prompt` |
| A5 | Cost/tokens counted across every stage (critique, validation, orchestration, reintegration, peer review) | `council.py`, `senate.py`, `schemas.py` |
| A6 | `ModelRoute` generation params (temperature/top_p/max_tokens/seed); Google adapter uses proper roles + `systemInstruction` | `providers.py`, `schemas.py` |
| A7 | History-based SSE with `Last-Event-ID` replay; `sub_run_id` on multi-part events | `streaming.py`, `main.py`, `council.py` |

**Not yet started:** everything in ROADMAP Phases 1–4, and everything in this doc.

**Recommended immediate next step:** ROADMAP **Phase 1 (eval harness + debate)** — it is
still the keystone. But interleave the distribution wave below, because proof + reach
landing together is what actually spikes adoption.

---

## 1. The missing axis — DISTRIBUTION (what actually wins OSS)

The ROADMAP optimizes quality and proof. But karpathy/llm-council has thousands of stars
mostly from distribution and story. These are the adoption levers, roughly in ROI order.

### B1. Local-model support — **highest ROI, lowest effort**
- **Gap:** `ModelRoute` has no `base_url`; the six providers use hardcoded endpoints, so
  Ollama / LM Studio / vLLM users are locked out entirely.
- **Fix:** add optional `base_url` to `ModelRoute`; `OpenAICompatibleAdapter` already does
  all the work — just honor the override. Ship an out-of-the-box Ollama preset route set.
- **Why it wins:** *"Run a council of open models on your own GPU — zero API keys"* is the
  r/LocalLLaMA front-page demo. No competitor in our landscape table has a
  council-of-local-models story.

### B2. Council-as-a-model — OpenAI-compatible `/v1/chat/completions` facade
- One FastAPI route that runs the council and returns the synthesis as a normal chat
  completion. Turns the project from "an app you visit" into "a model you can plug into
  anything": Open WebUI, LibreChat, Cursor, any SDK.
- **Most unique, low-effort/high-leverage feature available.** Nobody in the space does it.

### B3. MCP server — expose `consult_council` as a tool
- Let Claude Code, Codex, and other agents convene the council for high-stakes questions.
- Natural fit: agents are exactly the users who want a second opinion with confidence
  grades + provenance. A real 2026 distribution channel.

### B4. Packaging + CI basics
- `model-senate` console script already exists → finish the loop: publish to PyPI so
  `uvx model-senate` works; add Dockerfile + compose; add GitHub Actions (there are
  **zero** workflows in `.github/` today, so PRs currently merge untested).
- Once the harness exists, put the leaderboard table in the README — proof made visible.

### B5. Security minimum before anyone deploys
- API has **no auth** — anyone on the LAN can trigger paid runs. Add an optional
  bearer-token setting.
- Treat tool/web-search output as **untrusted**: it's injected into content other models
  then critique, so label it clearly in prompts to blunt prompt-injection propagation.

---

## 2. Signature product ideas (beyond the ROADMAP)

### C1. Cross-run reputation ledger — **the headline differentiator**
- ROADMAP has a *static* `model_strengths.json` from the harness. The unique version is
  *live*: per-model, per-query-type Elo updated from election outcomes, validation
  verdicts, and user 👍/👎 — fed back into election as a prior and into routing.
- *"The council learns which model to trust for which domain."* No rival has this, and we
  already persist every run in `data/conversations/`.

### C2. Multi-turn — chat with the council
- Both pipelines are single-shot. Follow-ups should reuse deliberation context, with a
  cheap mode (leader answers follow-ups) and full-council reconvene on demand. Converts
  one-shot demos into a daily driver.

### C3. Human-in-the-loop — the user as a senator
- Let the user submit their own opinion into Stage 1, or pause after critique to steer
  before synthesis. Fits the governance metaphor; makes deliberation participatory.

### C4. Unify Senate into Council
- Senate is now strictly a subset of Council (fixed leader, no orchestration/scoring/
  validation). Make it a Council preset (`mode: "classic"`) so every improvement lands in
  both and maintenance halves. Keep the `/api/senate/run` endpoint for compatibility.

---

## 3. Recommended sequence

1. **ROADMAP Phase 1** — eval harness + multi-round debate (the keystone; proves value).
2. **Distribution wave** — B1 (local models) → B2 (OpenAI-compatible endpoint) → B3 (MCP)
   → B4 (PyPI/Docker/CI) → B5 (auth). Ship alongside the first harness results.
3. **ROADMAP Phases 2–4** — verification, calibration, caching, provenance viz, leaderboard.
4. **Signature features** — C1 (reputation ledger) and C2 (multi-turn) as the flagship
   product bets; C3 and C4 as they fit.

Gate each quality feature on a harness re-run (per ROADMAP §11). Gate each distribution
feature on "a new user can do X in one command."

---

## 4. Fast-follow debt noticed during A1–A7 (small, not yet done)
- Native provider function-calling could replace the text-ReAct tool loop (A1 chose the
  provider-agnostic loop deliberately; native FC is a quality upgrade, esp. for tool-heavy
  runs).
- Cross-restart SSE durability (A7 added in-memory replay only; completed runs are already
  persisted, so this is low priority).
- Frontend does not yet render the new `sub_run_id`, per-stage `usage`, or provenance tree
  — surfacing them is ROADMAP Phase 4 work.
