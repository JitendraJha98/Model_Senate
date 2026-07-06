import pytest

from backend.doctor import run_doctor
from backend.schemas import ModelRoute, UsageMetadata


class OkAdapter:
    async def complete(self, route, messages, *, json_mode: bool = False):
        return "pong", UsageMetadata(total_tokens=1), 12


class FailAdapter:
    async def complete(self, route, messages, *, json_mode: bool = False):
        raise RuntimeError("connection refused")


async def test_doctor_reports_ok_missing_and_failing():
    routes = [
        ModelRoute(id="ok", provider="openrouter", model="x", display_name="OK"),
        ModelRoute(id="nokey", provider="anthropic", model="y", display_name="NoKey", missing_key=True),
        ModelRoute(id="down", provider="google", model="z", display_name="Down"),
    ]
    adapters = {"openrouter": OkAdapter(), "anthropic": OkAdapter(), "google": FailAdapter()}
    results = await run_doctor(routes, adapters)
    by_id = {r["id"]: r for r in results}

    assert by_id["ok"]["ok"] is True and by_id["ok"]["latency_ms"] == 12
    assert by_id["nokey"]["ok"] is False and by_id["nokey"]["error"] == "missing API key"
    assert by_id["down"]["ok"] is False and "connection refused" in by_id["down"]["error"]


async def test_doctor_checks_one_route_per_provider():
    routes = [
        ModelRoute(id="a1", provider="openrouter", model="x", display_name="A1"),
        ModelRoute(id="a2", provider="openrouter", model="y", display_name="A2"),
    ]
    results = await run_doctor(routes, {"openrouter": OkAdapter()})
    assert len(results) == 1  # deduped by provider
