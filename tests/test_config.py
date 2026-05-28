from backend.config import Settings, load_model_routes


def test_model_routes_mark_missing_keys():
    settings = Settings(openrouter_api_key=None, openai_api_key="ok")
    routes = load_model_routes(settings)
    openrouter = next(route for route in routes if route.provider == "openrouter")
    openai = next(route for route in routes if route.provider == "openai")
    assert openrouter.missing_key is True
    assert openai.missing_key is False

