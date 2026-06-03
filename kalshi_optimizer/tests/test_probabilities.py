from decimal import Decimal
from probabilities import build_scenario_probs

MOCK_PRICES = {
    "spurs_win":          Decimal("0.63"),
    "knicks_win":         Decimal("0.37"),
    "total_over_217.5":   Decimal("0.54"),
    "spurs_spread_4.5":   Decimal("0.53"),
    "spurs_spread_10.5":  Decimal("0.33"),
    "spurs_spread_16.5":  Decimal("0.21"),
    "knicks_spread_4.5":  Decimal("0.28"),
    "knicks_spread_10.5": Decimal("0.14"),
    "knicks_spread_20.5": Decimal("0.05"),
}

def test_12_scenario_probs_built():
    probs = build_scenario_probs(MOCK_PRICES)
    assert len(probs) == 12

def test_all_probs_positive():
    probs = build_scenario_probs(MOCK_PRICES)
    for key, p in probs.items():
        assert p > 0, f"Non-positive probability for {key}: {p}"

def test_marginal_not_cumulative():
    # Spurs 4.5-10.5 marginal = P(over 4.5) - P(over 10.5) = 0.53 - 0.33 = 0.20
    # P(scenario) = P(spurs) * P(over total) * 0.20
    probs = build_scenario_probs(MOCK_PRICES)
    p = probs["spurs_over_4.5to10.5"]
    expected = Decimal("0.63") * Decimal("0.54") * Decimal("0.20")
    assert abs(p - expected) < Decimal("0.001")

def test_scenario_keys_match_scenario_format():
    probs = build_scenario_probs(MOCK_PRICES)
    from combos_nba import SCENARIOS
    for s in SCENARIOS:
        key = f"{s['winner']}_{s['total']}_{s['margin_range']}"
        assert key in probs, f"Missing key: {key}"

def test_spurs_probs_sum_le_spurs_win():
    probs = build_scenario_probs(MOCK_PRICES)
    spurs_total = sum(p for key, p in probs.items() if key.startswith("spurs"))
    assert float(spurs_total) <= 0.63 + 0.01
