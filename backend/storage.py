from __future__ import annotations

import json
from pathlib import Path

from backend.schemas import SenateRun


class ConversationStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def save(self, run: SenateRun) -> None:
        path = self.data_dir / f"{run.id}.json"
        path.write_text(run.model_dump_json(indent=2), encoding="utf-8")

    def list_runs(self) -> list[SenateRun]:
        runs: list[SenateRun] = []
        for path in sorted(self.data_dir.glob("*.json"), reverse=True):
            try:
                runs.append(SenateRun.model_validate(json.loads(path.read_text(encoding="utf-8"))))
            except (json.JSONDecodeError, OSError, ValueError):
                continue
        return runs

    def get(self, run_id: str) -> SenateRun | None:
        path = self.data_dir / f"{run_id}.json"
        if not path.exists():
            return None
        return SenateRun.model_validate(json.loads(path.read_text(encoding="utf-8")))

