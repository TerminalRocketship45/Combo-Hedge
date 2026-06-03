from decimal import Decimal, ROUND_DOWN
from typing import Optional


def fetch_and_cache_orderbook(client, cache, series_ticker: str, combo_ticker: str) -> list:
    """
    Returns no_bids list for combo_ticker.
    Uses cache with 60s TTL; fetches fresh if stale.
    no_bids sorted descending by NO bid price (highest first).
    """
    cached = cache.get_orderbook(series_ticker, combo_ticker)
    if cached:
        return cached["no_bids"]

    resp = client.get(f"/markets/{combo_ticker}/orderbook")
    ob = resp.get("orderbook_fp", resp.get("orderbook", {}))
    no_bids = [[str(level[0]), str(level[1])] for level in ob.get("no_dollars", ob.get("no", []))]
    no_bids.sort(key=lambda x: Decimal(x[0]), reverse=True)

    cache.set_orderbook(series_ticker, combo_ticker, {"no_bids": no_bids})
    return no_bids
