"""CLI: `python -m backend.eval.run --suite math --configs single:<m>,council --limit 20`."""

from __future__ import annotations

import argparse
import asyncio

from backend.config import get_settings, load_model_routes
from backend.eval.baselines import EvalContext
from backend.eval.harness import run_eval
from backend.eval.report import write_report
from backend.providers import build_adapters
from backend.storage import ConversationStore
from backend.tools import build_tool_registry


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m backend.eval.run", description="Council evaluation harness")
    p.add_argument("--suite", default="factual,math,code", help="comma-separated suites")
    p.add_argument("--configs", required=True, help="comma-separated configs (e.g. single:gpt-5-2,council)")
    p.add_argument("--limit", type=int, default=None, help="max items per suite")
    p.add_argument("--out", default="eval_results", help="output directory")
    p.add_argument("--council-models", default=None, help="comma-separated model ids the council convenes")
    return p.parse_args()


async def _main() -> None:
    args = _parse_args()
    settings = get_settings()
    # Pin temperature=0 where supported for reproducibility (ROADMAP §9).
    routes = [r.model_copy(update={"temperature": 0.0}) for r in load_model_routes(settings) if not r.missing_key]
    if not routes:
        raise SystemExit("No routes with API keys configured. Populate .env first.")
    adapters = build_adapters(settings)
    council_ids = args.council_models.split(",") if args.council_models else [r.id for r in routes]

    ctx = EvalContext(
        routes=routes,
        adapters=adapters,
        store=ConversationStore(settings.data_dir),
        tool_registry=build_tool_registry(settings, force_code_executor=True),
        orchestrator_model_id=settings.orchestrator_model_id,
        council_ids=council_ids,
        debate_enabled=settings.council_debate_enabled,
    )

    suites = [s.strip() for s in args.suite.split(",") if s.strip()]
    configs = [c.strip() for c in args.configs.split(",") if c.strip()]
    report = await run_eval(suites, configs, ctx, limit=args.limit)
    path = write_report(report, args.out)
    print(f"Wrote leaderboard → {path}")
    for r in sorted(report.per_config_overall, key=lambda r: -r.accuracy):
        print(f"  {r.config:<28} acc={r.accuracy:.3f}  cost=${r.total_cost_usd:.4f}  n={r.n}")


if __name__ == "__main__":
    asyncio.run(_main())
