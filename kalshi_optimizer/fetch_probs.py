#!/usr/bin/env python3
"""
Fetch current Kalshi market probabilities for the NBA Finals G1 combo optimizer.
Outputs a JSON blob you can paste into optimizer.html's probability loader.

Usage:
    python fetch_probs.py
    python fetch_probs.py --patch   # also patches optimizer.html defaults directly
"""
import json
import sys
import os
import argparse
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

_GAME = "26JUN03NYKSAS"

# Individual market tickers
MARKETS = {
    "spurs_win":          f"KXNBAGAME-{_GAME}-SAS",
    "knicks_win":         f"KXNBAGAME-{_GAME}-NYK",
    "total_over":         f"KXNBATOTAL-{_GAME}-217",
    # Spread markets: YES = team wins by over X points
    "spurs_spread_4.5":   f"KXNBASPREAD-{_GAME}-SAS4",
    "spurs_spread_10.5":  f"KXNBASPREAD-{_GAME}-SAS10",
    "spurs_spread_16.5":  f"KXNBASPREAD-{_GAME}-SAS16",
    "knicks_spread_4.5":  f"KXNBASPREAD-{_GAME}-NYK4",
    "knicks_spread_10.5": f"KXNBASPREAD-{_GAME}-NYK10",
    "knicks_spread_20.5": f"KXNBASPREAD-{_GAME}-NYK20",
}

# Map each threshold to the best available spread market ticker
# Key = threshold, Value = market key from MARKETS
# For thresholds without an exact market (e.g. Spurs 20.5), use the closest available
SPURS_THRESHOLD_MAP  = {4.5: "spurs_spread_4.5",  10.5: "spurs_spread_10.5",  20.5: "spurs_spread_16.5"}
KNICKS_THRESHOLD_MAP = {4.5: "knicks_spread_4.5", 10.5: "knicks_spread_10.5", 20.5: "knicks_spread_20.5"}


def fetch_price(client, ticker: str) -> dict:
    resp = client.get(f"/markets/{ticker}")
    m = resp.get("market", resp)
    return {
        "bid":  float(m.get("yes_bid_dollars", 0) or 0),
        "ask":  float(m.get("yes_ask_dollars", 0) or 0),
        "last": float(m.get("last_price_dollars", 0) or 0),
    }


def best_price(p: dict) -> float:
    """Use last traded price if available, else mid of bid/ask."""
    if p["last"] > 0:
        return p["last"]
    if p["bid"] > 0 and p["ask"] > 0:
        return (p["bid"] + p["ask"]) / 2
    return p["ask"] or p["bid"] or 0.5


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--patch", action="store_true",
                        help="Patch optimizer.html default probability values in place")
    args = parser.parse_args()

    missing = [k for k in ("KALSHI_API_KEY_ID", "KALSHI_PRIVATE_KEY_PATH") if not os.environ.get(k)]
    if missing:
        print(f"ERROR: Missing env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    sys.path.insert(0, str(Path(__file__).parent))
    from client import KalshiClient
    client = KalshiClient()

    print("Fetching market prices from Kalshi API...", file=sys.stderr)

    prices = {}
    for key, ticker in MARKETS.items():
        try:
            prices[key] = fetch_price(client, ticker)
            p = prices[key]
            print(f"  {key}: bid={p['bid']:.3f} ask={p['ask']:.3f} last={p['last']:.3f}", file=sys.stderr)
        except Exception as e:
            print(f"  {key}: ERROR {e}", file=sys.stderr)
            prices[key] = {"bid": 0.5, "ask": 0.5, "last": 0.5}

    # Winner probabilities
    p_spurs_win  = best_price(prices["spurs_win"])
    p_knicks_win = best_price(prices["knicks_win"])
    p_over       = best_price(prices["total_over"])
    p_under      = round(1 - p_over, 4)

    # Cumulative margin probabilities:
    # P(team wins by UNDER threshold) = 1 - P(spread_X YES)
    # This is the value the HTML uses for its "cumulative under" inputs
    cum_spurs  = {}
    cum_knicks = {}
    for threshold, mkt_key in SPURS_THRESHOLD_MAP.items():
        spread_p = best_price(prices[mkt_key])
        cum_spurs[threshold] = round(1 - spread_p, 4)
    for threshold, mkt_key in KNICKS_THRESHOLD_MAP.items():
        spread_p = best_price(prices[mkt_key])
        cum_knicks[threshold] = round(1 - spread_p, 4)

    output = {
        "p_spurs_win":  round(p_spurs_win,  4),
        "p_knicks_win": round(p_knicks_win, 4),
        "p_over":       round(p_over,       4),
        "p_under":      p_under,
        "cum_spurs":    {str(k): v for k, v in cum_spurs.items()},
        "cum_knicks":   {str(k): v for k, v in cum_knicks.items()},
    }

    json_str = json.dumps(output, indent=2)
    print("\n" + json_str)

    if args.patch:
        html_path = Path(__file__).parent.parent / "optimizer.html"
        if not html_path.exists():
            print(f"\nWARNING: {html_path} not found, skipping patch.", file=sys.stderr)
            return
        html = html_path.read_text(encoding="utf-8")
        # Patch default input values in the HTML
        import re
        def patch_input(html, id_, val):
            return re.sub(
                rf'(id="{id_}"[^>]*value=")[^"]*(")',
                rf'\g<1>{val}\g<2>',
                html
            )
        html = patch_input(html, "pSpursWin",  output["p_spurs_win"])
        html = patch_input(html, "pKnicksWin", output["p_knicks_win"])
        html = patch_input(html, "pOver",      output["p_over"])
        html = patch_input(html, "pUnder",     output["p_under"])
        html_path.write_text(html, encoding="utf-8")
        print(f"\nPatched {html_path} with live probabilities.", file=sys.stderr)

    print("\nPaste the JSON above into optimizer.html → Probability Settings → LOAD", file=sys.stderr)


if __name__ == "__main__":
    main()
