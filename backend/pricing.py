"""Per-model price estimates so every provider can report a cost, not just OpenRouter.

`PRICE_TABLE` holds USD per 1,000,000 tokens as `(prompt, completion)`. These are
maintained estimates keyed by the *model* string (provider prefix stripped, dots
normalized to dashes) so both `anthropic/claude-sonnet-4.5` and the direct
`claude-sonnet-4-5` resolve to the same entry. Unknown models return `None`
(cost stays absent, exactly as before), so adding a model here is purely additive.
"""

from __future__ import annotations

# USD per 1M tokens: model_key -> (prompt_price, completion_price).
# Keys are normalized (see `_normalize`). Edit these to match current provider pricing.
PRICE_TABLE: dict[str, tuple[float, float]] = {
    "gpt-5-2": (1.25, 10.00),
    "gemini-3-pro-preview": (1.25, 10.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "grok-4": (3.00, 15.00),
}


def _normalize(model: str) -> str:
    """Strip any `provider/` prefix, lowercase, and unify `.`/`_` to `-`."""
    key = model.split("/")[-1].lower()
    return key.replace(".", "-").replace("_", "-")


def estimate_cost(
    model: str, prompt_tokens: int | None, completion_tokens: int | None
) -> float | None:
    """Estimate USD cost from token counts, or None if the model isn't priced."""
    prices = PRICE_TABLE.get(_normalize(model))
    if prices is None:
        return None
    prompt_price, completion_price = prices
    prompt = (prompt_tokens or 0) / 1_000_000 * prompt_price
    completion = (completion_tokens or 0) / 1_000_000 * completion_price
    return round(prompt + completion, 6)
