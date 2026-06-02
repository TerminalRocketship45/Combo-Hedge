from decimal import Decimal
from combos_nba import COMBOS, SCENARIOS, get_paying_combo_ids, calc_net_profit

def test_exactly_12_combos():
    assert len(COMBOS) == 12

def test_exactly_12_non_blowout_scenarios():
    assert len(SCENARIOS) == 12

def test_all_spread_sides_are_no():
    for c in COMBOS:
        assert c["spread_side"] == "no"

def test_all_gameline_sides_are_yes():
    for c in COMBOS:
        assert c["gameline_side"] == "yes"

def test_spurs_max_margin_is_16_5():
    spurs_combos = [c for c in COMBOS if c["winner"] == "spurs"]
    margins = {c["margin"] for c in spurs_combos}
    assert max(margins) == Decimal("16.5")
    assert Decimal("20.5") not in margins

def test_knicks_max_margin_is_20_5():
    knicks_combos = [c for c in COMBOS if c["winner"] == "knicks"]
    margins = {c["margin"] for c in knicks_combos}
    assert max(margins) == Decimal("20.5")

def test_margin_stacking_pays_multiple_combos():
    scenario = next(s for s in SCENARIOS if s["winner"] == "spurs" and s["margin_range"] == "0to4.5" and s["total"] == "over")
    paying = get_paying_combo_ids(scenario)
    paying_combos = [c for c in COMBOS if c["id"] in paying]
    assert len(paying_combos) == 3
    for c in paying_combos:
        assert c["winner"] == "spurs"
        assert c["total"] == "over"

def test_margin_stacking_middle_range():
    scenario = next(s for s in SCENARIOS if s["winner"] == "spurs" and s["margin_range"] == "4.5to10.5" and s["total"] == "over")
    paying = get_paying_combo_ids(scenario)
    paying_combos = [c for c in COMBOS if c["id"] in paying]
    assert len(paying_combos) == 2
    margins = {c["margin"] for c in paying_combos}
    assert Decimal("4.5") not in margins
    assert Decimal("10.5") in margins
    assert Decimal("16.5") in margins

def test_highest_margin_range_pays_one_combo():
    scenario = next(s for s in SCENARIOS if s["winner"] == "spurs" and s["margin_range"] == "10.5to16.5" and s["total"] == "over")
    paying = get_paying_combo_ids(scenario)
    paying_combos = [c for c in COMBOS if c["id"] in paying]
    assert len(paying_combos) == 1
    assert paying_combos[0]["margin"] == Decimal("16.5")

def test_net_profit_correct_formula():
    # Scenario: Spurs win by 1-4 pts, over 217.5 → C1, C3, C5 pay out (3 contracts each)
    # C2 loses. Net = (3+3+3) contracts * $1 - sum(contracts * fill for all combos)
    scenario = next(s for s in SCENARIOS if s["winner"] == "spurs" and s["margin_range"] == "0to4.5" and s["total"] == "over")
    # Give every combo 10 contracts at $0.10 fill price → cost = $1.00 each
    all_ids = [c["id"] for c in COMBOS]
    contracts   = {cid: Decimal("10.00") for cid in all_ids}
    fill_prices = {cid: Decimal("0.10")  for cid in all_ids}
    # C1, C3, C5 pay (spurs + over, margins 4.5/10.5/16.5 all > 0)
    # payout = 3 winning combos * 10 contracts * $1 = $30
    # total_cost = 12 combos * 10 * 0.10 = $12
    # net = $30 - $12 = $18
    net = calc_net_profit(scenario, contracts, fill_prices)
    assert net == Decimal("18.00")

def test_net_profit_subtracts_winning_stakes_too():
    # Verify that winning combo costs are ALSO subtracted (the JSX bug was not doing this)
    # Scenario where only C5 wins (spurs + over, margin 10.5to16.5)
    scenario = next(s for s in SCENARIOS if s["winner"] == "spurs" and s["margin_range"] == "10.5to16.5" and s["total"] == "over")
    all_ids = [c["id"] for c in COMBOS]
    contracts   = {cid: Decimal("10.00") for cid in all_ids}
    fill_prices = {cid: Decimal("0.10")  for cid in all_ids}
    # Only C5 wins: payout = 10 contracts * $1 = $10
    # total_cost = 12 * 10 * 0.10 = $12
    # net = $10 - $12 = -$2.00 (we lost money overall despite C5 paying out)
    net = calc_net_profit(scenario, contracts, fill_prices)
    assert net == Decimal("-2.00")
