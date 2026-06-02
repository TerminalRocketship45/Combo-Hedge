from decimal import Decimal, ROUND_DOWN
from dataclasses import dataclass
from typing import Dict
import numpy as np
from scipy.optimize import minimize

from combos_nba import COMBOS, SCENARIOS, get_paying_combo_ids, calc_net_profit

COMBO_IDS = [c["id"] for c in COMBOS]

# Pre-compute payout matrix: paying_matrix[s_idx][c_idx] = 1 if combo c pays in scenario s
_PAYOUT_MATRIX = np.zeros((len(SCENARIOS), len(COMBO_IDS)), dtype=float)
for _s_idx, _s in enumerate(SCENARIOS):
    _paying = set(get_paying_combo_ids(_s))
    for _c_idx, _cid in enumerate(COMBO_IDS):
        if _cid in _paying:
            _PAYOUT_MATRIX[_s_idx, _c_idx] = 1.0


@dataclass
class OptimizationResult:
    stakes: Dict[str, Decimal]
    contracts: Dict[str, Decimal]
    actual_costs: Dict[str, Decimal]
    fill_prices: Dict[str, Decimal]
    scenario_profits: Dict[str, Decimal]
    scenario_probs: Dict[str, Decimal]
    ev: Decimal
    avg_profit: Decimal
    worst_profit: Decimal
    best_profit: Decimal
    total_deployed: Decimal


def _feasible_x0(budget_f: float, max_loss_f: float, price_vec: np.ndarray) -> np.ndarray:
    """Build a feasible warm-start satisfying the floor constraint at equality.

    Strategy: allocate enough to each blowout combo (highest margin per
    winner/total quadrant) so its single-combo payout covers budget - max_loss.
    Distribute remaining budget equally among all other combos.

    Blowout combos (worst-case scenarios):
      C5  idx=4  spurs/over  highest margin
      C6  idx=5  spurs/under highest margin
      C11 idx=10 knicks/over highest margin
      C12 idx=11 knicks/under highest margin
    """
    BLOWOUT_IDXS = [4, 5, 10, 11]  # 0-based indices into COMBO_IDS
    x0 = np.zeros(len(COMBO_IDS))
    min_contracts = budget_f - max_loss_f  # contracts needed to hit floor exactly

    for idx in BLOWOUT_IDXS:
        x0[idx] = min_contracts * price_vec[idx]  # stake = contracts * price

    allocated = x0.sum()
    remaining = budget_f - allocated
    other_idxs = [i for i in range(len(COMBO_IDS)) if i not in BLOWOUT_IDXS]
    if remaining > 0 and other_idxs:
        per_other = remaining / len(other_idxs)
        for i in other_idxs:
            x0[i] = per_other

    return x0


def _make_scenario_key(s: dict) -> str:
    return f"{s['winner']}_{s['total']}_{s['margin_range']}"


def _profits_continuous(x: np.ndarray, price_vec: np.ndarray) -> np.ndarray:
    """Compute per-scenario profits in continuous space (no rounding).

    contracts_i = stake_i / price_i
    profit_s = sum(contracts_i for i in paying_s) - sum(contracts_i * price_i for all i)
             = sum(contracts_i for i in paying_s) - sum(stake_i for all i)

    Since stake_i = contracts_i * price_i and total cost = sum(stake_i).
    """
    contracts = x / price_vec  # shape (n,)
    payouts = _PAYOUT_MATRIX @ contracts  # shape (n_scenarios,)
    total_cost = np.sum(x)  # sum of dollar stakes = total cost
    return payouts - total_cost


def optimize(
    budget: Decimal,
    max_loss: Decimal,
    fill_prices: Dict[str, Decimal],
    scenario_probs: Dict[str, Decimal] = None,
) -> OptimizationResult:
    n = len(COMBO_IDS)
    budget_f   = float(budget)
    max_loss_f = float(max_loss)

    price_vec = np.array([float(fill_prices[cid]) for cid in COMBO_IDS])

    def objective(x):
        profits = _profits_continuous(x, price_vec)
        return -np.mean(profits)

    # Use a rounding buffer (0.10) so that after floor-to-2dp contract conversion,
    # the worst-case profit still stays above -max_loss.
    rounding_buffer = 0.10

    def floor_constraint(x):
        profits = _profits_continuous(x, price_vec)
        return np.min(profits) + max_loss_f - rounding_buffer

    constraints = [
        {"type": "eq",   "fun": lambda x: np.sum(x) - budget_f},
        {"type": "ineq", "fun": floor_constraint},
    ]
    bounds = [(0.0, budget_f)] * n

    # Warm-start from a feasible point: allocate just enough to each
    # "blowout" combo (highest margin per winner/total quadrant) so that
    # its payout covers budget - max_loss, satisfying the floor constraint.
    # Remaining budget is distributed equally among other combos.
    x0 = _feasible_x0(budget_f, max_loss_f, price_vec)

    result = minimize(
        objective, x0, method="SLSQP", bounds=bounds, constraints=constraints,
        options={"maxiter": 15000, "ftol": 1e-12},
    )

    # Fall back to x0 if solver didn't converge
    best_x = result.x if result.success else x0

    raw_stakes = {cid: Decimal(str(max(0.0, best_x[i]))) for i, cid in enumerate(COMBO_IDS)}
    return _build_result(raw_stakes, fill_prices, budget, scenario_probs or {})


def _build_result(
    raw_stakes: dict,
    fill_prices: dict,
    budget: Decimal,
    scenario_probs: dict,
) -> OptimizationResult:
    contracts = {
        cid: (raw_stakes[cid] / fill_prices[cid]).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        for cid in COMBO_IDS
    }
    actual_costs  = {cid: contracts[cid] * fill_prices[cid] for cid in COMBO_IDS}
    total_deployed = sum(actual_costs.values())

    scenario_profits = {}
    for s in SCENARIOS:
        key = _make_scenario_key(s)
        scenario_profits[key] = calc_net_profit(s, contracts, fill_prices)

    profits_list = list(scenario_profits.values())

    ev = Decimal("0")
    if scenario_probs:
        for key, profit in scenario_profits.items():
            prob = scenario_probs.get(key, Decimal("0"))
            ev  += prob * profit

    return OptimizationResult(
        stakes=raw_stakes,
        contracts=contracts,
        actual_costs=actual_costs,
        fill_prices=fill_prices,
        scenario_profits=scenario_profits,
        scenario_probs=scenario_probs,
        ev=ev,
        avg_profit=sum(profits_list) / len(profits_list),
        worst_profit=min(profits_list),
        best_profit=max(profits_list),
        total_deployed=total_deployed,
    )


def round_allocations(stakes: dict, fill_prices: dict, budget: Decimal) -> dict:
    """Convert dollar stakes to floored contracts, then trim to stay within budget.

    Flooring individual contracts to 2dp can cause total_cost to slightly exceed
    budget due to accumulated rounding. This function corrects that by reducing
    contracts one step at a time (0.01 contract = one Kalshi lot) starting from
    the cheapest combo until the budget constraint is satisfied.
    """
    contracts = {
        cid: (stakes[cid] / fill_prices[cid]).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        for cid in stakes
    }
    combo_ids = list(stakes.keys())
    total_cost = sum(contracts[cid] * fill_prices[cid] for cid in combo_ids)

    if total_cost > budget:
        # Sort by fill_price ascending: trim cheapest combos first to minimise
        # the number of lots removed while recovering the overage.
        sorted_ids = sorted(combo_ids, key=lambda cid: fill_prices[cid])
        for cid in sorted_ids:
            if total_cost <= budget:
                break
            excess = total_cost - budget
            # How many 0.01-contract lots do we need to drop?
            # Use ceiling (ROUND_UP) so we always remove enough to clear the excess.
            from decimal import ROUND_UP
            lots_to_drop = (excess / (fill_prices[cid] * Decimal("0.01"))).to_integral_value(rounding=ROUND_UP)
            lots_to_drop = min(lots_to_drop, (contracts[cid] / Decimal("0.01")).to_integral_value(rounding=ROUND_DOWN))
            drop = lots_to_drop * Decimal("0.01")
            contracts[cid] -= drop
            total_cost -= drop * fill_prices[cid]

    actual_costs = {cid: contracts[cid] * fill_prices[cid] for cid in contracts}
    return {"contracts": contracts, "actual_costs": actual_costs}
