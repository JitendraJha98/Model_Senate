"""Render an `EvalReport` to `leaderboard.md` + `.json` and write `calibration.json`."""

from __future__ import annotations

import json
from pathlib import Path

from backend.eval.harness import ConfigResult, EvalReport


def _table(rows: list[list[str]], headers: list[str]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def _fmt_ece(r: ConfigResult) -> str:
    return f"{r.ece:.3f}" if r.ece is not None else "—"


def render_markdown(report: EvalReport) -> str:
    overall = sorted(report.per_config_overall, key=lambda r: (-r.accuracy, r.total_cost_usd))
    leaderboard = _table(
        [
            [
                r.config,
                f"{r.accuracy:.3f}",
                _fmt_ece(r),
                f"${r.avg_cost_usd:.5f}",
                f"{r.avg_latency_s:.2f}s",
                str(r.n),
                str(r.errors),
            ]
            for r in overall
        ],
        ["config", "accuracy", "ECE", "avg cost", "avg latency", "n", "errors"],
    )

    lines = [
        "# Council Evaluation Leaderboard",
        "",
        f"Suites: {', '.join(report.suites)}  ·  Configs: {len(report.configs)}",
        "",
        "## Leaderboard (overall, sorted by accuracy then cost)",
        "",
        leaderboard,
        "",
    ]

    if report.best_single_config:
        lines += [
            f"**Best single model:** `{report.best_single_config}`",
            "",
            "## Win-rate vs best single model (net, −1..1)",
            "",
            _table(
                [[cfg, f"{wr:+.3f}"] for cfg, wr in sorted(report.win_rate_vs_best_single.items(), key=lambda kv: -kv[1])],
                ["config", "net win-rate"],
            ),
            "",
        ]

    # Ablation view: council vs each ablation, overall accuracy delta.
    overall_by_cfg = {r.config: r for r in report.per_config_overall}
    if "council" in overall_by_cfg:
        base = overall_by_cfg["council"].accuracy
        ablation_rows = [
            [cfg, f"{overall_by_cfg[cfg].accuracy:.3f}", f"{base - overall_by_cfg[cfg].accuracy:+.3f}"]
            for cfg in ["council_no_debate", "council_no_critique", "council_no_election", "council_no_tools"]
            if cfg in overall_by_cfg
        ]
        if ablation_rows:
            lines += [
                "## Ablations (council accuracy minus ablation = that stage's contribution)",
                "",
                _table(ablation_rows, ["ablation", "accuracy", "Δ from full council"]),
                "",
            ]

    # Per-domain breakdown.
    lines += ["## Per-domain accuracy", ""]
    for suite in report.suites:
        rows = sorted(
            [r for r in report.per_config_suite if r.suite == suite],
            key=lambda r: -r.accuracy,
        )
        if rows:
            lines += [
                f"### {suite}",
                "",
                _table([[r.config, f"{r.accuracy:.3f}", str(r.n)] for r in rows], ["config", "accuracy", "n"]),
                "",
            ]

    if report.calibration:
        lines += [
            "## Fitted calibration (Council grade → measured accuracy)",
            "",
            _table([[g, f"{p:.3f}"] for g, p in sorted(report.calibration.items())], ["grade", "accuracy"]),
            "",
        ]

    return "\n".join(lines)


def write_report(report: EvalReport, out_dir: str | Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "leaderboard.md").write_text(render_markdown(report), encoding="utf-8")
    (out / "leaderboard.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    # calibration.json feeds runtime calibration (Phase 2); write into the eval package.
    calib_path = Path(__file__).parent / "calibration.json"
    calib_path.write_text(json.dumps(report.calibration, indent=2), encoding="utf-8")
    return out / "leaderboard.md"
