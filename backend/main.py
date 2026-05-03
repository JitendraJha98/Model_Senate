from __future__ import annotations

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings, load_model_routes
from backend.providers import build_adapters
from backend.schemas import AppConfigResponse, SenateRequest, SenateRun
from backend.senate import SenateService
from backend.storage import ConversationStore

settings = get_settings()
routes = load_model_routes(settings)
store = ConversationStore(settings.data_dir)
service = SenateService(routes=routes, adapters=build_adapters(settings), store=store)

app = FastAPI(title="Model_Senate API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config", response_model=AppConfigResponse)
async def get_config() -> AppConfigResponse:
    openrouter_models = [route.id for route in routes if route.provider == "openrouter"]
    return AppConfigResponse(
        models=routes,
        defaults={
            "selected_model_ids": openrouter_models[:3],
            "leader_model_id": openrouter_models[0] if openrouter_models else routes[0].id,
            "min_models": 3,
        },
    )


@app.post("/api/senate/run", response_model=SenateRun)
async def run_senate(request: SenateRequest) -> SenateRun:
    try:
        return await service.run(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/conversations", response_model=list[SenateRun])
async def list_conversations() -> list[SenateRun]:
    return store.list_runs()


@app.get("/api/conversations/{run_id}", response_model=SenateRun)
async def get_conversation(run_id: str) -> SenateRun:
    run = store.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return run


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host=settings.model_senate_host, port=settings.model_senate_port, reload=True)

