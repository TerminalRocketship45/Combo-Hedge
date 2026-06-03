from decimal import Decimal
from orderbook import compute_vwap_yes_fill, compute_contracts, nominal_multiplier

def test_vwap_single_level():
    no_bids = [("0.9300", "100.00")]
    fill = compute_vwap_yes_fill(no_bids, Decimal("0.70"))
    assert fill == Decimal("0.07")

def test_vwap_walks_multiple_levels():
    # L1: NO bid 0.93 → YES at 0.07, 10 contracts available, cost = 10*0.07 = $0.70
    # L2: NO bid 0.92 → YES at 0.08, need $0.30 more → 0.30/0.08 = 3.75 contracts
    # total contracts = 13.75, total cost = $1.00
    # VWAP = 1.00 / 13.75
    no_bids = [("0.9300", "10.00"), ("0.9200", "100.00")]
    fill = compute_vwap_yes_fill(no_bids, Decimal("1.00"))
    expected = Decimal("1.00") / Decimal("13.75")
    assert abs(fill - expected) < Decimal("0.0001")

def test_vwap_insufficient_liquidity():
    # Only 10 contracts at NO bid 0.93 (YES fill 0.07), cost = 10*0.07 = $0.70
    # Want $2.00 but only $0.70 available — return fill for what IS available
    no_bids = [("0.9300", "10.00")]
    fill = compute_vwap_yes_fill(no_bids, Decimal("2.00"))
    assert fill is not None
    assert fill == Decimal("0.07")

def test_vwap_no_bids_returns_none():
    fill = compute_vwap_yes_fill([], Decimal("1.00"))
    assert fill is None

def test_compute_contracts_floors_to_2dp():
    # stake 1.23, fill 0.07 → 17.571... → floor to 17.57
    contracts = compute_contracts(Decimal("1.23"), Decimal("0.07"))
    assert contracts == Decimal("17.57")

def test_compute_contracts_does_not_overspend():
    contracts = compute_contracts(Decimal("1.00"), Decimal("0.07"))
    actual_cost = contracts * Decimal("0.07")
    assert actual_cost <= Decimal("1.00")

def test_nominal_multiplier():
    mult = nominal_multiplier(Decimal("0.07"))
    assert abs(mult - Decimal("14.285714")) < Decimal("0.0001")
