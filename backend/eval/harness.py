"""Drive config × suite over items, score, and aggregate into an `EvalReport`."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from backend.eval.baselines import EvalContext, Prediction, run_config
from backend.eval.datasets import EvalItem, load_suite
from backend.eval.metrics import accuracy, expected_calibration_error, fit_calibration, win_rate
from backend.eval.scorers import score_prediction


class ConfigResult(BaseModel):
    config: str
    suite: str
    n: int
    accuracy: float
    avg_cost_usd: float
    avg_latency_s: float
    total_cost_usd: float
    ece: float | None = None
    errors: int = 0


class EvalReport(BaseModel):
    configs: list[str]
    suites: list[str]
    per_config_suite: list[ConfigResult] = Field(default_factory=list)
    per_config_overall: list[ConfigResult] = Field(default_factory=list)
    best_single_config: str | None = None
    win_rate_vs_best_single: dict[str, float] = Field(default_factory=dict)
    calibration: dict[str, float] = Field(default_factory=dict)
    predictions: list[Prediction] = Field(default_factory=list)
    manifest: dict = Field(default_factory=dict)


def _aggregate(config: str, suite: str, preds: list[Prediction]) -> ConfigResult:
    scored = [p for p in preds if p.correct is not None]
    correct = [bool(p.correct) for p in scored]
    confidences = [p.confidence for p in scored]
    ece = (
        expected_calibration_error([c for c in confidences if c is not None],
                                   [ok for c, ok in zip(confidences, correct) if c is not None])
        if any(c is not None for c in confidences) else None
    )
    return ConfigResult(
        config=config,
        suite=suite,
        n=len(scored),
        accuracy=round(accuracy(correct), 4),
        avg_cost_usd=round(sum(p.cost_usd for p in preds) / len(preds), 6) if preds else 0.0,
        avg_latency_s=round(sum(p.latency_s for p in preds) / len(preds), 3) if preds else 0.0,
        total_cost_usd=round(sum(p.cost_usd for p in preds), 6),
        ece=round(ece, 4) if ece is not None else None,
        errors=sum(1 for p in preds if p.error),
    )


def _suite_hash(items: list[EvalItem]) -> str:
    joined = "|".join(f"{it.id}:{it.gold}" for it in items)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:12]


async def run_eval(
    suites: list[str],
    configs: list[str],
    ctx: EvalContext,
    limit: int | None = None,
    judge=None,
) -> EvalReport:
    items_by_suite = {s: load_suite(s, limit) for s in suites}
    all_items = [it for s in suites for it in items_by_suite[s]]

    predictions: list[Prediction] = []
    for config in configs:
        for item in all_items:
            pred = await run_config(config, item, ctx)
            if pred.error is None:
                score = await score_prediction(item, pred.answer, judge)
                pred.correct = score.correct
            predictions.append(pred)

    per_suite: list[ConfigResult] = []
    per_overall: list[ConfigResult] = []
    for config in configs:
        cfg_preds = [p for p in predictions if p.config == config]
        for suite in suites:
            sp = [p for p in cfg_preds if p.suite == suite]
            if sp:
                per_suite.append(_aggregate(config, suite, sp))
        per_overall.append(_aggregate(config, "ALL", cfg_preds))

    # Win-rate vs the strongest single model (by overall accuracy).
    singles = [r for r in per_overall if r.config.startswith("single:")]
    best_single = max(singles, key=lambda r: r.accuracy).config if singles else None
    win_rates: dict[str, float] = {}
    if best_single:
        by_key = {(p.config, p.item_id): bool(p.correct) for p in predictions if p.correct is not None}
        base = [by_key[(best_single, it.id)] for it in all_items if (best_single, it.id) in by_key]
        for config in configs:
            if config == best_single:
                continue
            aligned = [
                (by_key[(config, it.id)], by_key[(best_single, it.id)])
                for it in all_items
                if (config, it.id) in by_key and (best_single, it.id) in by_key
            ]
            if aligned:
                win_rates[config] = round(win_rate([a for a, _ in aligned], [b for _, b in aligned]), 4)

    # Calibration map fitted from Council grades vs outcomes.
    council_preds = [p for p in predictions if p.config == "council" and p.correct is not None and p.grade]
    calibration = fit_calibration([p.grade for p in council_preds], [bool(p.correct) for p in council_preds])

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "suites": {s: {"n": len(items_by_suite[s]), "hash": _suite_hash(items_by_suite[s])} for s in suites},
        "configs": configs,
        "council_models": ctx.council_model_ids(),
        "orchestrator_model_id": ctx.orchestrator_model_id,
        "limit": limit,
    }

    return EvalReport(
        configs=configs,
        suites=suites,
        per_config_suite=per_suite,
        per_config_overall=per_overall,
        best_single_config=best_single,
        win_rate_vs_best_single=win_rates,
        calibration=calibration,
        predictions=predictions,
        manifest=manifest,
    )
