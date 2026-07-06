"""Preflight health check: is each configured provider actually reachable?

`python -m backend.doctor` (or GET /api/health/deep) does a tiny generation against one
route per provider and reports ready/failed — so a missing key or a down provider is
caught before a run wastes time. Mirrors the graceful degradation the pipelines already do.
"""

from __future__ import annotations

import asyncio
import sys

from backend.config import get_settings, load_model_routes
from backend.providers import ProviderAdapter, build_adapters
from backend.schemas import ChatMessage, ModelRoute


async def _check_route(route: ModelRoute, adapter: ProviderAdapter) -> dict:
    try:
        _, _, latency_ms = await adapter.complete(
            route, [ChatMessage(role="user", content="ping")]
        )
        return {"id": route.id, "provider": route.provider, "ok": True, "latency_ms": latency_ms}
    except Exception as exc:  # noqa: BLE001 — report, don't raise; this is a diagnostic
        return {"id": route.id, "provider": route.provider, "ok": False, "error": str(exc)}


async def run_doctor(routes: list[ModelRoute], adapters: dict[str, ProviderAdapter]) -> list[dict]:
    """Check one usable route per provider. Missing-key routes are flagged without a call."""
    results: list[dict] = []
    seen: set[str] = set()
    for route in routes:
        if route.missing_key:
            results.append({"id": route.id, "provider": route.provider, "ok": False, "error": "missing API key"})
            continue
        if route.provider in seen:
            continue
        seen.add(route.provider)
        adapter = adapters.get(route.provider)
        if adapter is None:
            results.append({"id": route.id, "provider": route.provider, "ok": False, "error": "no adapter"})
            continue
        results.append(await _check_route(route, adapter))
    return results


def main() -> None:
    settings = get_settings()
    routes = load_model_routes(settings)
    adapters = build_adapters(settings)
    results = asyncio.run(run_doctor(routes, adapters))

    print("\n  Model Council — provider doctor\n")
    for r in results:
        mark = "✅" if r["ok"] else "❌"
        detail = f"{r.get('latency_ms', '?')}ms" if r["ok"] else r.get("error", "failed")
        print(f"  {mark}  {r['provider']:<12} {r['id']:<30} {detail}")

    reachable = [r for r in results if r["ok"]]
    print(f"\n  {len(reachable)}/{len(results)} routes reachable.\n")
    # Non-zero exit if nothing is reachable (useful for CI / container healthchecks).
    sys.exit(0 if reachable else 1)


if __name__ == "__main__":
    main()
