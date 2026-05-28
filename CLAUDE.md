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
```bash
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

Model Senate is a **multi-model consensus system**: a single prompt is sent to N AI models in parallel, models anonymously peer-review each other's responses, and a designated "leader" model synthesizes a final answer.

### Three-Stage Pipeline (`backend/senate.py`)

1. **Stage 1 — First Opinions:** All selected models called in parallel (`asyncio.gather`). Each produces an independent response.
2. **Stage 2 — Peer Review:** Each Stage-1-successful model receives anonymized summaries of other models' answers (labeled "Response A", "Response B", etc.) and independently ranks them. Rankings are extracted via regex from a `FINAL RANKING:` block, then de-anonymized using a stored label→model-id map.
3. **Stage 3 — Leader Synthesis:** The designated leader model receives the original query, all first opinions, all peer reviews, and aggregate ranking data to produce a final synthesized answer.

One model failing Stage 1 does not abort the pipeline; that model is simply excluded from Stage 2.

### Provider Adapters (`backend/providers.py`)

Abstract base `ProviderAdapter` with a single async `complete()` method. Concrete implementations:
- `OpenAICompatibleAdapter` — handles OpenRouter, OpenAI, and xAI (same API shape)
- `AnthropicAdapter` — Anthropic messages API
- `GoogleAdapter` — Google Generative Language API

`build_adapters()` is the factory; adapters are instantiated once in `main.py` and shared.

### Backend Structure
- `main.py` — FastAPI app, CORS, 5 REST endpoints, global singletons
- `config.py` — `Settings` (pydantic-settings, reads `.env`), `DEFAULT_ROUTES` (8 predefined models), `load_model_routes()` hydrates `missing_key` flags per provider
- `schemas.py` — Pydantic models for all DTOs; `SenateRun` is the top-level output
- `senate.py` — `SenateService` orchestrates the pipeline; also holds all system prompt strings and helper functions for ranking aggregation
- `storage.py` — `ConversationStore` reads/writes `data/conversations/{run_id}.json`

### Frontend Structure (`frontend/src/`)
- `App.tsx` — Monolithic component with three views (Senate workspace, Models settings, History). All state lives here.
- `api.ts` — Three typed fetch helpers: `getConfig()`, `getConversations()`, `runSenate()`
- `types.ts` — TypeScript interfaces that mirror backend Pydantic schemas
- `styles.css` — Custom CSS only; no CSS framework

### API Endpoints
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | Liveness check |
| GET | `/api/config` | Available models + defaults |
| POST | `/api/senate/run` | Execute pipeline; returns `SenateRun` |
| GET | `/api/conversations` | List past runs (sorted newest-first) |
| GET | `/api/conversations/{run_id}` | Retrieve specific run |

### Environment / API Keys
Copy `.env.example` to `.env` and populate API keys. OpenRouter is the primary provider; direct keys for OpenAI, Anthropic, Google, and xAI are optional. The `missing_key` field on each `ModelRoute` is set at startup by `config.py` and surfaced in the frontend Models view.

### Pytest Configuration
`asyncio_mode = "auto"` is set in `pyproject.toml`, so async test functions work without decorators. `respx` is used for HTTP-level mocking in tests; `FakeAdapter` in `test_senate.py` mocks the provider adapter layer.
