from decimal import Decimal
from optimizer import optimize, round_allocations, OptimizationResult

FILL_PRICES = {
    "C1":  Decimal("0.0676"),
    "C2":  Decimal("0.0578"),
    "C3":  Decimal("0.1961"),
    "C4":  Decimal("0.1667"),
    "C5":  Decimal("0.2703"),
    "C6":  Decimal("0.2439"),
    "C7":  Decimal("0.0633"),
    "C8":  Decimal("0.0503"),
    "C9":  Decimal("0.1370"),
    "C10": Decimal("0.1163"),
    "C11": Decimal("0.1887"),
    "C12": Decimal("0.1786"),
}

def test_optimize_budget_approximately_allocated():
    result = optimize(budget=Decimal("10.00"), max_loss=Decimal("2.00"), fill_prices=FILL_PRICES)
    total = sum(result.actual_costs.values())
    assert total <= Decimal("10.00")
    assert total >= Decimal("9.00")  # at least 90% deployed

def test_optimize_floor_constraint_satisfied():
    result = optimize(budget=Decimal("10.00"), max_loss=Decimal("2.00"), fill_prices=FILL_PRICES)
    for key, profit in result.scenario_profits.items():
        assert profit >= Decimal("-2.00") - Decimal("0.15"), f"Floor violated in {key}: {profit}"

def test_optimize_returns_result_dataclass():
    result = optimize(budget=Decimal("10.00"), max_loss=Decimal("2.00"), fill_prices=FILL_PRICES)
    assert isinstance(result, OptimizationResult)
    assert len(result.contracts) == 12
    assert len(result.scenario_profits) == 12

def test_round_allocations_never_overspend():
    from combos_nba import COMBOS
    stakes = {c["id"]: Decimal("0.834") for c in COMBOS}
    fill_prices = {c["id"]: Decimal("0.07") for c in COMBOS}
    rounded = round_allocations(stakes, fill_prices, budget=Decimal("10.00"))
    total_cost = sum(rounded["contracts"][cid] * fill_prices[cid] for cid in rounded["contracts"])
    assert total_cost <= Decimal("10.00")

def test_round_allocations_contracts_are_2dp():
    stakes = {"C1": Decimal("1.234")}
    fill_prices = {"C1": Decimal("0.07")}
    rounded = round_allocations(stakes, fill_prices, budget=Decimal("1.234"))
    contracts = rounded["contracts"]["C1"]
    assert contracts == contracts.quantize(Decimal("0.01"))
