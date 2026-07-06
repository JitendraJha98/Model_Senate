"""Deterministic scorers: a prediction string vs an item's gold answer.

Auto-scoring (exact/math/code) is preferred over the LLM judge for reproducibility.
"""

from __future__ import annotations

import re
import string

from pydantic import BaseModel

from backend.eval.datasets import EvalItem
from backend.schemas import ChatMessage
from backend.tools import CodeExecutorTool


class Score(BaseModel):
    correct: bool
    detail: str = ""


_PUNCT = str.maketrans("", "", string.punctuation)


def _normalize(text: str) -> str:
    return " ".join(text.lower().translate(_PUNCT).split())


def exact_match(gold: str, prediction: str) -> Score:
    """Normalized equality, or gold appearing as a contiguous token-run in the prediction."""
    g = _normalize(gold)
    p = _normalize(prediction)
    if not g:
        return Score(correct=False, detail="empty gold")
    correct = g == p or f" {g} " in f" {p} "
    return Score(correct=correct, detail=f"gold={g!r}")


_NUMBER_RE = re.compile(r"-?\$?\d[\d,]*(?:\.\d+)?")


def _to_number(token: str) -> float | None:
    cleaned = token.replace("$", "").replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_final_number(text: str) -> float | None:
    marker = re.search(r"####\s*(-?\$?[\d,]+(?:\.\d+)?)", text)
    if marker:
        return _to_number(marker.group(1))
    matches = _NUMBER_RE.findall(text)
    return _to_number(matches[-1]) if matches else None


def math_answer_match(gold: str, prediction: str) -> Score:
    g = _to_number(gold)
    p = _extract_final_number(prediction)
    if g is None:
        return Score(correct=False, detail="unparseable gold")
    if p is None:
        return Score(correct=False, detail="no number in prediction")
    return Score(correct=abs(g - p) < 1e-6, detail=f"gold={g}, pred={p}")


_CODE_BLOCK_RE = re.compile(r"```(?:python)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_code(prediction: str) -> str:
    blocks = _CODE_BLOCK_RE.findall(prediction)
    if blocks:
        # Prefer the longest block (the actual solution, not a usage snippet).
        return max(blocks, key=len).strip()
    return prediction.strip()


async def code_pass(item: EvalItem, prediction: str, timeout: int = 10) -> Score:
    """Run the extracted code plus the gold unit tests in the sandbox; pass@1."""
    program = f"{extract_code(prediction)}\n\n{item.gold}\n"
    result = await CodeExecutorTool(timeout).run({"code": program})
    return Score(correct=result.success, detail=result.error or "tests passed")


async def llm_judge(item: EvalItem, prediction: str, adapter, route) -> Score:
    messages = [
        ChatMessage(role="system", content="You are a strict grader. Reply with only CORRECT or INCORRECT."),
        ChatMessage(
            role="user",
            content=(
                f"Question: {item.question}\nReference answer: {item.gold}\n"
                f"Candidate answer: {prediction}\n\nIs the candidate answer correct?"
            ),
        ),
    ]
    content, _, _ = await adapter.complete(route, messages)
    verdict = content.upper()
    return Score(correct="CORRECT" in verdict and "INCORRECT" not in verdict, detail=content[:120])


async def score_prediction(item: EvalItem, prediction: str, judge=None) -> Score:
    """Dispatch to the right scorer for the item's suite / metric.

    `judge` is an optional `(adapter, route)` tuple used only for the `llm_judge` metric.
    """
    if item.suite == "math":
        return math_answer_match(item.gold, prediction)
    if item.suite == "code":
        return await code_pass(item, prediction)
    if item.metadata.get("metric") == "llm_judge" and judge is not None:
        return await llm_judge(item, prediction, judge[0], judge[1])
    return exact_match(item.gold, prediction)
