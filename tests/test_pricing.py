from backend.pricing import estimate_cost


def test_estimate_cost_basic_math():
    # claude-sonnet-4-5 = (3.00, 15.00) per 1M tokens
    cost = estimate_cost("claude-sonnet-4-5", 1_000_000, 1_000_000)
    assert cost == 18.0


def test_estimate_cost_strips_provider_prefix_and_normalizes_dots():
    # anthropic/claude-sonnet-4.5 must resolve to the same entry as claude-sonnet-4-5
    prefixed = estimate_cost("anthropic/claude-sonnet-4.5", 500_000, 200_000)
    direct = estimate_cost("claude-sonnet-4-5", 500_000, 200_000)
    assert prefixed == direct
    assert prefixed == round(500_000 / 1_000_000 * 3.0 + 200_000 / 1_000_000 * 15.0, 6)


def test_estimate_cost_unknown_model_is_none():
    assert estimate_cost("some/unlisted-model", 1000, 1000) is None


def test_estimate_cost_handles_missing_token_counts():
    # Missing completion tokens count as zero, not an error.
    assert estimate_cost("grok-4", 1_000_000, None) == 3.0
