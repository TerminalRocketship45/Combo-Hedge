#!/usr/bin/env python3
"""
Kalshi NBA Finals Combo Optimizer
Fetches live multipliers, runs SLSQP optimizer, writes HTML report.
No bets are placed.
"""
import argparse
import os
import sys
import webbrowser
import tempfile
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _estimate_missing_fills(fill_prices: dict, market_prices: dict) -> dict:
    """
    For combos with no live orderbook quotes, estimate YES fill price as the
    product of individual leg probabilities. This assumes independence between
    legs — a rough approximation, but better than a flat fallback.
    Combo leg structure: YES gameline × NO spread × YES/NO total
    """
    from combos_nba import COMBOS
    result = dict(fill_prices)
    for combo in COMBOS:
        cid = combo["id"]
        if result.get(cid) is not None:
            continue
        w = combo["winner"]
        m = str(combo["margin"])
        p_gameline = market_prices[f"{w}_win"]
        p_spread_over = market_prices[f"{w}_spread_{m}"]
        p_spread_no   = Decimal("1") - p_spread_over  # betting NO on spread
        p_total = (
            market_prices["total_over_217.5"] if combo["total"] == "over"
            else Decimal("1") - market_prices["total_over_217.5"]
        )
        estimated = p_gameline * p_spread_no * p_total
        # Kalshi adds vig; estimated price is the theoretical fair value.
        # Cap at 0.0100 minimum to avoid degenerate optimizer values.
        result[cid] = max(estimated, Decimal("0.0100"))
    return result


def _require_env():
    missing = [k for k in ("KALSHI_API_KEY_ID", "KALSHI_PRIVATE_KEY_PATH") if not os.environ.get(k)]
    if missing:
        print(f"ERROR: Missing environment variables: {', '.join(missing)}")
        print("Set them in a .env file or export them before running.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Kalshi NBA Finals Combo Optimizer — analysis only, no bets placed"
    )
    parser.add_argument("--budget",   type=float, help="Total budget in dollars")
    parser.add_argument("--max-loss", type=float, dest="max_loss", help="Max acceptable loss in any scenario ($)")
    parser.add_argument("--series",   type=str,   help="Override series ticker (e.g. KXNBAFINALSGA)")
    parser.add_argument("--demo",     action="store_true", help="Use demo API (https://demo-api.kalshi.co/trade-api/v2)")
    parser.add_argument("--refresh",  action="store_true", help="Bypass cache and re-discover all markets")
    parser.add_argument("--output",   type=str,   default=None, help="Save HTML to this path (default: temp file)")
    args = parser.parse_args()

    _require_env()

    budget = args.budget
    if budget is None:
        budget = float(input("Enter total budget ($): "))

    max_loss = args.max_loss
    if max_loss is None:
        max_loss = float(input("Enter max willing to lose ($): "))

    budget_d   = Decimal(str(budget))
    max_loss_d = Decimal(str(max_loss))

    if max_loss_d > budget_d:
        print("ERROR: max-loss cannot exceed budget.")
        sys.exit(1)

    from client import KalshiClient
    from cache import KalshiCache
    from discovery import discover_all, HARDCODED_COLLECTION_TICKER
    from orderbook import fetch_and_cache_orderbook, compute_vwap_yes_fill
    from probabilities import build_scenario_probs, get_market_prices_from_api
    from optimizer import optimize
    from report import generate_html

    client = KalshiClient(demo=args.demo)
    cache  = KalshiCache()

    print("\nChecking exchange status...")
    try:
        status = client.get("/exchange/status")
        if not status.get("exchange_active", True):
            print("WARNING: Exchange is currently not active.")
    except Exception:
        pass

    series_ticker = args.series or HARDCODED_COLLECTION_TICKER
    print(f"Game: NBA Finals G1 ({series_ticker})")

    if args.refresh:
        cache.refresh(series_ticker)
        print("Cache cleared.")

    print("Discovering Game 1 markets and creating combo markets...")
    market_tickers, combo_tickers = discover_all(client, series_ticker, cache)
    print(f"  -> {len(combo_tickers)} combos ready")

    print("Fetching market prices for probability model...")
    market_prices = get_market_prices_from_api(client, market_tickers)
    scenario_probs = build_scenario_probs(market_prices)

    print("Fetching orderbooks (live prices for combo markets)...")
    fill_prices = {}
    live_count  = 0
    for cid, combo_ticker in combo_tickers.items():
        no_bids = fetch_and_cache_orderbook(client, cache, series_ticker, combo_ticker)
        fill    = compute_vwap_yes_fill(no_bids, budget_d / 12)
        if fill is not None and fill > Decimal("0"):
            fill_prices[cid] = fill
            live_count += 1
        else:
            fill_prices[cid] = None  # will be filled with estimates below

    if live_count < len(combo_tickers):
        print(f"  {live_count}/{len(combo_tickers)} combos have live quotes. Estimating the rest from leg prices.")
        fill_prices = _estimate_missing_fills(fill_prices, market_prices)
    else:
        print(f"  All {live_count} combos have live quotes.")

    print("Running optimizer...")
    result = optimize(
        budget=budget_d,
        max_loss=max_loss_d,
        fill_prices=fill_prices,
        scenario_probs=scenario_probs,
    )

    fetched_at = datetime.now().strftime("%H:%M:%S")
    html = generate_html(result, budget=budget_d, max_loss=max_loss_d, fetched_at=fetched_at)

    if args.output:
        output_path = args.output
        Path(output_path).write_text(html, encoding="utf-8")
    else:
        tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8")
        tmp.write(html)
        tmp.close()
        output_path = tmp.name

    print(f"\nReport written to: {output_path}")
    print(f"  Worst case:  {float(result.worst_profit):+.2f}")
    print(f"  Best case:   {float(result.best_profit):+.2f}")
    print(f"  Avg profit:  {float(result.avg_profit):+.2f}")
    print(f"  Expected EV: {float(result.ev):+.2f}")
    print(f"  Deployed:    ${float(result.total_deployed):.2f} of ${budget:.2f}")

    webbrowser.open(f"file://{output_path}")
    print("\nOpened in browser.")
    print("Re-run within 60s of placing orders for best accuracy.")
    print("This tool does not place bets — all allocations are recommendations only.")


if __name__ == "__main__":
    main()
