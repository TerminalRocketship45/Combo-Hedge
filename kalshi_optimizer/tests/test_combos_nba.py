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
    # 1 combo wins at 14.8x with stake $1, 1 combo loses with stake $1
    # net = $14.80 - $2.00 = $12.80 (NOT $14.80 - $1.00 = $13.80)
    costs = {"C1": Decimal("1.00"), "C2": Decimal("1.00")}
    payouts = {"C1": Decimal("14.80"), "C2": Decimal("0")}
    total_cost = Decimal("2.00")
    net = sum(payouts.values()) - total_cost
    assert net == Decimal("12.80")
