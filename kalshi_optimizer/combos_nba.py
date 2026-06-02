from decimal import Decimal
from typing import List

COMBOS = [
    {"id": "C1",  "winner": "spurs",  "margin": Decimal("4.5"),  "total": "over",  "gameline_side": "yes", "spread_side": "no", "total_side": "yes"},
    {"id": "C2",  "winner": "spurs",  "margin": Decimal("4.5"),  "total": "under", "gameline_side": "yes", "spread_side": "no", "total_side": "no"},
    {"id": "C3",  "winner": "spurs",  "margin": Decimal("10.5"), "total": "over",  "gameline_side": "yes", "spread_side": "no", "total_side": "yes"},
    {"id": "C4",  "winner": "spurs",  "margin": Decimal("10.5"), "total": "under", "gameline_side": "yes", "spread_side": "no", "total_side": "no"},
    {"id": "C5",  "winner": "spurs",  "margin": Decimal("16.5"), "total": "over",  "gameline_side": "yes", "spread_side": "no", "total_side": "yes"},
    {"id": "C6",  "winner": "spurs",  "margin": Decimal("16.5"), "total": "under", "gameline_side": "yes", "spread_side": "no", "total_side": "no"},
    {"id": "C7",  "winner": "knicks", "margin": Decimal("4.5"),  "total": "over",  "gameline_side": "yes", "spread_side": "no", "total_side": "yes"},
    {"id": "C8",  "winner": "knicks", "margin": Decimal("4.5"),  "total": "under", "gameline_side": "yes", "spread_side": "no", "total_side": "no"},
    {"id": "C9",  "winner": "knicks", "margin": Decimal("10.5"), "total": "over",  "gameline_side": "yes", "spread_side": "no", "total_side": "yes"},
    {"id": "C10", "winner": "knicks", "margin": Decimal("10.5"), "total": "under", "gameline_side": "yes", "spread_side": "no", "total_side": "no"},
    {"id": "C11", "winner": "knicks", "margin": Decimal("20.5"), "total": "over",  "gameline_side": "yes", "spread_side": "no", "total_side": "yes"},
    {"id": "C12", "winner": "knicks", "margin": Decimal("20.5"), "total": "under", "gameline_side": "yes", "spread_side": "no", "total_side": "no"},
]

SCENARIOS = [
    {"winner": "spurs",  "margin_range": "0to4.5",    "total": "over"},
    {"winner": "spurs",  "margin_range": "0to4.5",    "total": "under"},
    {"winner": "spurs",  "margin_range": "4.5to10.5", "total": "over"},
    {"winner": "spurs",  "margin_range": "4.5to10.5", "total": "under"},
    {"winner": "spurs",  "margin_range": "10.5to16.5","total": "over"},
    {"winner": "spurs",  "margin_range": "10.5to16.5","total": "under"},
    {"winner": "knicks", "margin_range": "0to4.5",    "total": "over"},
    {"winner": "knicks", "margin_range": "0to4.5",    "total": "under"},
    {"winner": "knicks", "margin_range": "4.5to10.5", "total": "over"},
    {"winner": "knicks", "margin_range": "4.5to10.5", "total": "under"},
    {"winner": "knicks", "margin_range": "10.5to20.5","total": "over"},
    {"winner": "knicks", "margin_range": "10.5to20.5","total": "under"},
]


def get_paying_combo_ids(scenario: dict) -> List[str]:
    """Return combo IDs that pay out in the given scenario.

    A combo pays when:
    - Its winner matches the scenario winner
    - Its total direction matches the scenario total
    - Its margin threshold is strictly greater than the scenario lower bound
      (margin stacking: e.g. a 10.5 combo wins in both 0to4.5 and 4.5to10.5 scenarios)
    """
    winner = scenario["winner"]
    total = scenario["total"]
    margin_range = scenario["margin_range"]
    lo_str = margin_range.split("to")[0]
    lo = Decimal(lo_str)
    paying = []
    for combo in COMBOS:
        if combo["winner"] != winner:
            continue
        if combo["total"] != total:
            continue
        if combo["margin"] > lo:
            paying.append(combo["id"])
    return paying


def calc_net_profit(
    scenario: dict,
    contracts: dict,
    fill_prices: dict,
) -> Decimal:
    """Calculate net profit for a scenario given contract sizes and fill prices.

    Net profit = sum of payouts for winning combos - total cost of ALL combos.
    Each winning combo pays $1 per contract (Kalshi binary settled at $1).
    Each combo costs fill_price per contract regardless of outcome.
    """
    paying_ids = set(get_paying_combo_ids(scenario))
    payout = sum(contracts[cid] for cid in paying_ids if cid in contracts)
    total_cost = sum(contracts[cid] * fill_prices[cid] for cid in contracts)
    return payout - total_cost
