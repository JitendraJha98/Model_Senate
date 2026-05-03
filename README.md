# Model_Senate

Run one prompt. Get multiple minds.

Model_Senate is a local-first research app that sends the same query to several AI models, asks them to anonymously review each other's work, and then has a leader model synthesize one answer with agreement, disagreement, caveats, and recommended next checks.

## Why It Exists

Single models have blind spots. They can miss context, overstate weak claims, or lean toward one style of reasoning. Model_Senate helps you compare multiple model perspectives without manually copying prompts between providers.

Use it for investment research, complex decisions, creative brainstorming, and verification tasks where confidence matters.

## Pipeline

1. **First opinions**: each selected model answers independently.
2. **Anonymous review**: each model reviews and ranks the other answers without seeing model/provider names.
3. **Leader synthesis**: the chosen leader model combines the opinions and reviews into one final answer.

## Tech Stack

- Backend: FastAPI, async httpx, Pydantic, JSON file storage
- Frontend: React, Vite, TypeScript, react-markdown, lucide-react
- Package management: `uv` for Python, `npm` for JavaScript
- Default routing: OpenRouter chat completions API
- Optional direct adapters: OpenAI, Anthropic, Google, xAI

## Setup

### 1. Install dependencies

```bash
uv sync
cd frontend
npm install
cd ..
```

### 2. Configure keys

```bash
cp .env.example .env
```

Add at least one route key. OpenRouter is the easiest default:

```env
OPENROUTER_API_KEY=sk-or-v1-your-key
```

Optional direct provider keys are also supported:

```env
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=
XAI_API_KEY=
```

Keys are read from your local environment only. They are not stored in conversation JSON files.

### 3. Run the app

```bash
./start.sh
```

On Windows PowerShell:

```powershell
.\start.ps1
```

Manual mode:

```bash
uv run python -m backend.main
cd frontend
npm run dev
```

Open http://localhost:5173.

## Model Configuration

Default routes live in `backend/config.py`. You can also provide custom routes with `MODEL_SENATE_ROUTES` as JSON:

```json
[
  {
    "id": "openrouter-gpt-5-2",
    "provider": "openrouter",
    "model": "openai/gpt-5.2",
    "display_name": "GPT-5.2 via OpenRouter",
    "enabled": true,
    "supports_streaming": true
  }
]
```

The UI shows which routes are missing local API keys without revealing the key values.

## API

- `GET /api/health`
- `GET /api/config`
- `POST /api/senate/run`
- `GET /api/conversations`
- `GET /api/conversations/{run_id}`

## Testing

```bash
uv run pytest
cd frontend
npm test
npm run build
```

## Privacy

Model_Senate is local-first. Prompts and responses are stored in `data/conversations/` as JSON. API keys stay in `.env` or process environment variables and are never written to conversation files.

## Limitations

This MVP is designed for local research workflows, not hosted multi-tenant SaaS. Model output quality depends on the selected providers, model availability, and the user-supplied keys. For high-stakes financial, medical, or legal decisions, use Model_Senate as a research aid and verify with primary sources or qualified professionals.
