from backend.config import Settings, load_model_routes


def test_model_routes_mark_missing_keys(monkeypatch):
    # Isolate from any local .env that overrides routes via MODEL_SENATE_ROUTES, so the
    # test exercises DEFAULT_ROUTES deterministically.
    monkeypatch.delenv("MODEL_SENATE_ROUTES", raising=False)
    settings = Settings(openrouter_api_key=None, openai_api_key="ok", model_senate_routes=None)
    routes = load_model_routes(settings)
    openrouter = next(route for route in routes if route.provider == "openrouter")
    openai = next(route for route in routes if route.provider == "openai")
    assert openrouter.missing_key is True
    assert openai.missing_key is False

