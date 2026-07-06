from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

DATA_DIR = Path(__file__).parent / "data"


class EvalItem(BaseModel):
    id: str
    suite: str
    question: str
    gold: str
    metadata: dict = Field(default_factory=dict)


def available_suites() -> list[str]:
    return sorted(p.stem for p in DATA_DIR.glob("*.jsonl"))


def load_suite(name: str, limit: int | None = None) -> list[EvalItem]:
    """Load a bundled JSONL fixture. Fixtures are committed for offline, deterministic runs."""
    path = DATA_DIR / f"{name}.jsonl"
    if not path.exists():
        raise FileNotFoundError(
            f"No eval suite fixture at {path}. Available: {', '.join(available_suites()) or 'none'}"
        )
    items: list[EvalItem] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            items.append(EvalItem.model_validate_json(line))
    return items[:limit] if limit is not None else items
