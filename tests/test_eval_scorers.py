import pytest

from backend.eval.datasets import EvalItem, available_suites, load_suite
from backend.eval.scorers import (
    exact_match,
    extract_code,
    math_answer_match,
    score_prediction,
)


def test_exact_match_substring_and_normalization():
    assert exact_match("Au", "The chemical symbol for gold is Au.").correct
    assert exact_match("Tokyo", "The capital is Tokyo").correct
    assert not exact_match("Tokyo", "The capital is Kyoto").correct
    # Padding prevents partial-token false positives.
    assert not exact_match("au", "australia is large").correct


def test_math_answer_match_prefers_hash_marker_then_last_number():
    assert math_answer_match("10", "Reasoning here.\n#### 10").correct
    assert math_answer_match("180", "It travels 180 miles total.").correct
    assert not math_answer_match("10", "The answer is nine.").correct
    assert math_answer_match("1000", "cost is $1,000").correct


def test_extract_code_picks_longest_block():
    text = "usage:\n```python\nadd(1,2)\n```\nsolution:\n```python\ndef add(a, b):\n    return a + b\n```"
    assert "def add" in extract_code(text)


async def test_score_prediction_dispatches_by_suite():
    factual = EvalItem(id="f", suite="factual", question="q", gold="Au")
    math = EvalItem(id="m", suite="math", question="q", gold="42")
    assert (await score_prediction(factual, "It is Au")).correct
    assert (await score_prediction(math, "#### 42")).correct


def test_fixtures_load_and_are_nonempty():
    assert set(available_suites()) >= {"factual", "math", "code"}
    for suite in ("factual", "math", "code"):
        items = load_suite(suite)
        assert items and all(it.suite == suite and it.gold for it in items)


async def test_code_pass_executes_when_sandbox_available():
    from backend.tools import CodeExecutorTool

    # Skip if this locked-down environment can't spawn `python -c`.
    sanity = await CodeExecutorTool(10).run({"code": "print('ok')"})
    if not sanity.success:
        pytest.skip(f"code executor unavailable here: {sanity.error}")

    item = EvalItem(
        id="c", suite="code", question="write add",
        gold="assert add(2, 3) == 5",
    )
    good = await score_prediction(item, "```python\ndef add(a, b):\n    return a + b\n```")
    bad = await score_prediction(item, "```python\ndef add(a, b):\n    return a - b\n```")
    assert good.correct
    assert not bad.correct
