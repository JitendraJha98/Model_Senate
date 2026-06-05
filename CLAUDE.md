# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Backend (Python)
```bash
uv sync                          # Install dependencies
uv run python -m backend.main    # Start backend server (port 8001, auto-reload)
uv run pytest                    # Run all tests
uv run pytest tests/test_senate.py::test_name  # Run a single test
```

### Frontend (TypeScript/React)
Run these from the `frontend/` directory (that's where `package.json` lives).
```bash
cd frontend
npm install          # Install dependencies
npm run dev          # Start Vite dev server (port 5173, proxies /api → backend)
npm run build        # TypeScript compile + production build
npm test             # Run Vitest tests
```

### Full Stack
```powershell
.\start.ps1          # Start backend + frontend concurrently (Windows)
```

Both servers must run simultaneously during development. The frontend Vite config proxies all `/api/*` requests to `http://127.0.0.1:8001`.

## Architecture

This project hosts **two parallel consensus pipelines**: the original **Model Senate** and the newer **Model Council**. Both share the same providers, storage, and routes but differ in pipeline design and output schemas.

### Model Senate — 3-Stage Pipeline (`backend/senate.py`)

The original pipeline. A fixed "leader" model is pre-designated by the caller.

1. **Stage 1 — First Opinions:** All selected models called in parallel (`asyncio.gather`). Each produces an independent response.
2. **Stage 2 — Peer Review:** Each Stage-1-successful model receives anonymized summaries of other models' answers (labeled "Response A", "Response B", etc.) and independently ranks them. Rankings are extracted via regex from a `FINAL RANKING:` block, then de-anonymized using a stored label→model-id map.
3. **Stage 3 — Leader Synthesis:** The designated leader model receives the original query, all first opinions, all peer reviews, and aggregate ranking data to produce a final synthesized answer.

### Model Council — 5-Stage Pipeline (`backend/council.py`)

The newer pipeline. The leader is elected dynamically based on scored performance.

0. **Stage 0 — Orchestration:** `orchestrator.py` calls a designated orchestrator model (or falls back to heuristics) to classify the query type (`factual`, `analytical`, `code`, `ethics`, `creative`, `multi_part`) and assign each model a role from `backend/roles.py` (e.g. Fact Verifier, Devil's Advocate, Code Verifier). Tool assignments are derived from roles.
1. **Stage 1 — First Opinions:** Models respond in their assigned roles. Each response is parsed into a structured JSON opinion (`answer`, `confidence`, `key_claims`, `assumptions`, `uncertainties`). Parse failures fall back to raw content with `status="parse_failed"`. Tool calls embedded in model output (`TOOL_CALL: <name>: <input>`) are executed via `backend/tools.py` and results appended to the opinion.
2. **Stage 2 — Critique:** Every successful model critiques every other model's opinion, producing `CritiqueScore` (accuracy/logic/completeness/calibration). Critique roles rotate across `CritiqueRole` variants.
3. **Stage 3 — Leader Election:** `backend/election.py` scores each candidate as: `score = (rank_score × 0.6) + (calibration_score × 0.25) + (tool_verification_score × 0.15)`. Elects a leader and a backup validator.
4. **Stage 4 — Synthesis:** The elected leader synthesizes all opinions and critiques into structured JSON (`direct_answer`, `consensus`, `dissent`, `unresolved`, `confidence_grade`, `provenance`). Retries with the validator model if synthesis fails.
5. **Stage 5 — Validation:** The validator model checks the synthesis against the original query and critique flags, returning `approved`, `approved_with_caveats`, or `flagged`.

The Council pipeline runs asynchronously: `POST /api/council/run` returns a `run_id` immediately; the client polls `GET /api/council/run/{run_id}/stream` for Server-Sent Events.

### Provider Adapters (`backend/providers.py`)

Abstract base `ProviderAdapter` with a single async `complete()` method. Concrete implementations:
- `OpenAICompatibleAdapter` — handles OpenRouter, OpenAI, and xAI (same API shape)
- `AnthropicAdapter` — Anthropic messages API
- `GoogleAdapter` — Google Generative Language API

`build_adapters()` is the factory; adapters are instantiated once in `main.py` and shared across both pipelines.

### Backend Module Reference

| Module | Role |
|--------|------|
| `main.py` | FastAPI app, CORS, all REST endpoints, global singletons |
| `config.py` | `Settings` (pydantic-settings, reads `.env`), `DEFAULT_ROUTES`, `load_model_routes()` |
| `schemas.py` | All Pydantic DTOs; `SenateRun` and `CouncilRun` are the top-level outputs |
| `senate.py` | `SenateService` — original 3-stage pipeline |
| `council.py` | `CouncilService` — 5-stage pipeline; also contains JSON parsing helpers |
| `orchestrator.py` | Query classification and role/tool assignment for Council Stage 0 |
| `roles.py` | `AgentRole`, `CritiqueRole` enums; `QUERY_ROLE_MAP`; system prompt builders |
| `election.py` | `elect_leader()` — scores candidates, returns `LeaderElection` |
| `validator.py` | `build_validation_prompt()` / `parse_validation_result()` for Stage 5 |
| `reintegrator.py` | `detect_contradictions()` / re-integration prompt + parsing for Stage 6 (multi-part) |
| `tools.py` | `CalculatorTool`, `CodeExecutorTool`, `WebSearchTool`; `inject_tool_results()` |
| `streaming.py` | `CouncilEventStream` (asyncio queue) and `active_streams` registry |
| `storage.py` | `ConversationStore` reads/writes JSON under `data/conversations/` |
| `providers.py` | Provider adapter implementations |

### Frontend Structure (`frontend/src/`)
- `App.tsx` — Monolithic component with three views (Senate workspace, Models settings, History). All state lives here.
- `api.ts` — Typed fetch helpers for both pipelines
- `types.ts` — TypeScript interfaces mirroring backend Pydantic schemas
- `styles.css` — Custom CSS only; no CSS framework

### API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | Liveness check |
| GET | `/api/config` | Available models + defaults for both pipelines |
| POST | `/api/senate/run` | Execute Senate pipeline; returns `SenateRun` synchronously |
| GET | `/api/conversations` | List past Senate runs (sorted newest-first) |
| GET | `/api/conversations/{run_id}` | Retrieve specific Senate run |
| POST | `/api/council/run` | Start Council pipeline; returns `{"run_id": "..."}` immediately |
| GET | `/api/council/run/{run_id}/stream` | SSE stream of Council pipeline events |
| GET | `/api/council/run/{run_id}` | Retrieve completed Council run |
| GET | `/api/council/runs` | List past Council runs (newest-first, capped at 100) |

### Environment / API Keys

Copy `.env.example` to `.env` and populate API keys. OpenRouter is the primary provider; direct keys for OpenAI, Anthropic, Google, and xAI are optional. Notable non-key settings:

| Setting | Default | Purpose |
|---------|---------|---------|
| `ORCHESTRATOR_MODEL_ID` | `openrouter-gpt-5-2` | Model used for Council Stage 0 |
| `COUNCIL_MIN_MODELS` | `2` | Minimum models required for a Council run |
| `COUNCIL_SYNTHESIS_RETRY_ON_FAILURE` | `true` | Retry synthesis with validator if leader fails |
| `TOOL_CODE_EXECUTOR_ENABLED` | `false` | Enable sandboxed Python code execution tool |
| `TOOL_WEB_SEARCH_ENABLED` | `false` | Enable web search tool (no provider implemented yet) |

Custom model routes can be injected via `MODEL_SENATE_ROUTES` as a JSON array of `ModelRoute` objects, overriding `DEFAULT_ROUTES` entirely.

### Pytest Configuration

`asyncio_mode = "auto"` is set in `pyproject.toml`, so async test functions work without decorators. `respx` is used for HTTP-level mocking; `FakeAdapter` in `test_senate.py` mocks the provider adapter layer.

---

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.
