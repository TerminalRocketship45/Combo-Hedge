from decimal import Decimal
from combos_nba import SCENARIOS

ScenarioProbs = dict


def build_scenario_probs(market_prices: dict) -> ScenarioProbs:
    """
    Compute probability for each of the 12 non-blowout scenarios.
    Keys: "{winner}_{total}_{margin_range}"

    Marginal margin range probability (NOT cumulative):
        P(margin in [lo, hi]) = P(over lo) - P(over hi)

    Scenario probability:
        P(scenario) = P(winner) * P(total direction) * P(margin in range)
    """
    p_spurs_win   = market_prices["spurs_win"]
    p_knicks_win  = market_prices["knicks_win"]
    p_over_total  = market_prices["total_over_217.5"]
    p_under_total = Decimal("1") - p_over_total

    # Store P(over X.5) for each spread threshold per winner
    over_probs = {
        "spurs": {
            "4.5":  market_prices["spurs_spread_4.5"],
            "10.5": market_prices["spurs_spread_10.5"],
            "16.5": market_prices["spurs_spread_16.5"],
        },
        "knicks": {
            "4.5":  market_prices["knicks_spread_4.5"],
            "10.5": market_prices["knicks_spread_10.5"],
            "20.5": market_prices["knicks_spread_20.5"],
        },
    }

    # margin_ranges: (range_key, lo_str, hi_str)
    # lo_str == "0" means P(over 0) = 1.0 (winner must win by at least 0.5)
    margin_ranges = {
        "spurs": [
            ("0to4.5",    "0",    "4.5"),
            ("4.5to10.5", "4.5",  "10.5"),
            ("10.5to16.5","10.5", "16.5"),
        ],
        "knicks": [
            ("0to4.5",    "0",    "4.5"),
            ("4.5to10.5", "4.5",  "10.5"),
            ("10.5to20.5","10.5", "20.5"),
        ],
    }

    def marginal(winner: str, lo: str, hi: str) -> Decimal:
        """P(margin in (lo, hi]) = P(over lo) - P(over hi)."""
        op = over_probs[winner]
        p_over_lo = Decimal("1") if lo == "0" else op[lo]
        p_over_hi = op[hi]
        return max(Decimal("0"), p_over_lo - p_over_hi)

    p_winner = {"spurs": p_spurs_win, "knicks": p_knicks_win}
    p_total  = {"over": p_over_total, "under": p_under_total}

    probs: ScenarioProbs = {}
    for scenario in SCENARIOS:
        winner = scenario["winner"]
        mrange = scenario["margin_range"]
        total  = scenario["total"]

        _, lo, hi = next(r for r in margin_ranges[winner] if r[0] == mrange)
        p_margin = marginal(winner, lo, hi)

        key = f"{winner}_{total}_{mrange}"
        probs[key] = p_winner[winner] * p_total[total] * p_margin

    return probs


def get_market_prices_from_api(client, market_tickers: dict) -> dict:
    """Fetch yes_ask price for each of the 9 individual markets."""
    prices = {}
    for key, ticker_tuple in market_tickers.items():
        ticker = ticker_tuple[0] if isinstance(ticker_tuple, (tuple, list)) else ticker_tuple
        resp = client.get(f"/markets/{ticker}")
        market = resp.get("market", resp)
        prices[key] = Decimal(str(market.get("yes_ask_dollars", market.get("yes_ask", "0.5"))))
    return prices
