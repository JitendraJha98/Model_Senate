from __future__ import annotations

import json
import secrets
from pathlib import Path
from uuid import uuid4

import uvicorn
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from backend.config import get_settings, load_model_routes
from backend.council import CouncilService
from backend.facade import (
    OAIChatRequest,
    council_answer,
    messages_to_prompt,
    to_chat_completion,
    to_stream_chunks,
)
from backend.providers import build_adapters
from backend.schemas import AppConfigResponse, CouncilRequest, CouncilRun, SenateRequest, SenateRun
from backend.senate import SenateService
from backend.storage import ConversationStore
from backend.streaming import close_stream, create_stream, get_stream
from backend.tools import build_tool_registry

settings = get_settings()
routes = load_model_routes(settings)
store = ConversationStore(settings.data_dir)
adapters = build_adapters(settings)
service = SenateService(routes=routes, adapters=adapters, store=store)
council_service = CouncilService(
    routes=routes,
    adapters=adapters,
    store=store,
    tool_registry=build_tool_registry(settings),
    orchestrator_model_id=settings.orchestrator_model_id,
    synthesis_retry_on_failure=settings.council_synthesis_retry_on_failure,
    max_tool_iterations=settings.council_max_tool_iterations,
    debate_enabled=settings.council_debate_enabled,
    debate_max_rounds=settings.council_debate_max_rounds,
    debate_recritique=settings.council_debate_recritique,
    debate_convergence=settings.council_debate_convergence,
)

app = FastAPI(title="Model_Senate API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_origin,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_auth(authorization: str | None = Header(default=None)) -> None:
    """Gate paid endpoints behind an optional bearer token.

    When API_AUTH_TOKEN is unset the API is open (current behavior); when set, the
    run-triggering endpoints require `Authorization: Bearer <token>`.
    """
    token = settings.api_auth_token
    if not token:
        return
    expected = f"Bearer {token}"
    if not authorization or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/health/deep")
async def health_deep() -> dict:
    """Preflight: tiny generation against each provider; reports reachable routes."""
    from backend.doctor import run_doctor

    results = await run_doctor(routes, adapters)
    reachable = sum(1 for r in results if r["ok"])
    return {"status": "ok" if reachable else "degraded", "reachable": reachable, "routes": results}


@app.get("/api/config", response_model=AppConfigResponse)
async def get_config() -> AppConfigResponse:
    openrouter_models = [route.id for route in routes if route.provider == "openrouter"]
    return AppConfigResponse(
        models=routes,
        defaults={
            "selected_model_ids": openrouter_models[:3],
            "leader_model_id": openrouter_models[0] if openrouter_models else routes[0].id,
            "min_models": 3,
            "council_selected_model_ids": openrouter_models[: max(settings.council_min_models, 2)],
            "council_min_models": settings.council_min_models,
        },
    )


@app.post("/api/senate/run", response_model=SenateRun, dependencies=[Depends(require_auth)])
async def run_senate(request: SenateRequest) -> SenateRun:
    try:
        return await service.run(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/council/run", dependencies=[Depends(require_auth)])
async def run_council(request: CouncilRequest, background_tasks: BackgroundTasks) -> dict[str, str]:
    if len(request.selected_model_ids) < settings.council_min_models:
        raise HTTPException(status_code=400, detail=f"Select at least {settings.council_min_models} models")
    run_id = str(uuid4())
    stream = create_stream(run_id)

    async def execute() -> None:
        try:
            await council_service.run(request, run_id=run_id, stream=stream)
        finally:
            await stream.close()
            close_stream(run_id)

    background_tasks.add_task(execute)
    return {"run_id": run_id}


@app.get("/api/council/run/{run_id}/stream")
async def stream_council_run(run_id: str, request: Request) -> StreamingResponse:
    stream = get_stream(run_id)
    if not stream:
        raise HTTPException(status_code=404, detail="Council stream not found")
    # Resume from the last delivered event on reconnect (EventSource sets this header).
    try:
        start = int(request.headers.get("last-event-id", 0))
    except ValueError:
        start = 0
    return StreamingResponse(stream.events(start), media_type="text/event-stream")


@app.get("/api/council/run/{run_id}", response_model=CouncilRun)
async def get_council_run(run_id: str) -> CouncilRun:
    run = store.get_council(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Council run not found")
    return run


@app.get("/api/council/runs", response_model=list[CouncilRun])
async def list_council_runs() -> list[CouncilRun]:
    return store.list_council_runs()[:100]


@app.get("/api/conversations", response_model=list[SenateRun])
async def list_conversations() -> list[SenateRun]:
    return store.list_runs()


@app.get("/api/conversations/{run_id}", response_model=SenateRun)
async def get_conversation(run_id: str) -> SenateRun:
    run = store.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return run


@app.post("/v1/chat/completions", dependencies=[Depends(require_auth)])
@app.post("/api/v1/chat/completions", dependencies=[Depends(require_auth)])
async def openai_chat_completions(request: OAIChatRequest):
    """OpenAI-compatible endpoint: run the Council, return the synthesis as a completion."""
    prompt, system_context = messages_to_prompt(request.messages)
    if not prompt.strip():
        raise HTTPException(status_code=400, detail="No user message provided")
    model_ids = [route.id for route in routes if not route.missing_key]
    if len(model_ids) < settings.council_min_models:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least {settings.council_min_models} available models; {len(model_ids)} configured",
        )
    run = await council_service.run(
        CouncilRequest(prompt=prompt, selected_model_ids=model_ids, system_context=system_context)
    )
    answer = council_answer(run)
    if request.stream:
        async def event_stream():
            for chunk in to_stream_chunks(run, request.model, answer):
                yield f"data: {json.dumps(chunk)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")
    return JSONResponse(to_chat_completion(run, request.model, answer))


def _frontend_dir() -> Path | None:
    """Locate a built frontend: bundled in the wheel (backend/static) or the repo (frontend/dist)."""
    here = Path(__file__).resolve().parent
    for candidate in (here / "static", here.parent / "frontend" / "dist"):
        if (candidate / "index.html").exists():
            return candidate
    return None


# Mount the SPA last so it never shadows the /api/* routes registered above.
_frontend = _frontend_dir()
if _frontend is not None:
    app.mount("/", StaticFiles(directory=str(_frontend), html=True), name="frontend")


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host=settings.model_senate_host, port=settings.model_senate_port, reload=True)
