from decimal import Decimal, ROUND_DOWN
from typing import Optional


def compute_vwap_yes_fill(no_bids: list, order_dollars: Decimal) -> Optional[Decimal]:
    """
    Compute VWAP fill price for buying YES contracts.
    Walk NO bids descending (highest first = cheapest YES).
    YES fill at each level = 1 - no_bid_price.
    Returns VWAP YES fill, or None if no bids at all.
    """
    if not no_bids:
        return None

    remaining = order_dollars
    total_contracts = Decimal("0")
    total_cost = Decimal("0")

    for price_str, size_str in no_bids:
        no_bid = Decimal(price_str)
        yes_fill = Decimal("1") - no_bid
        size = Decimal(size_str)

        cost_for_all = size * yes_fill
        if cost_for_all <= remaining:
            total_contracts += size
            total_cost += cost_for_all
            remaining -= cost_for_all
        else:
            partial_contracts = remaining / yes_fill
            total_contracts += partial_contracts
            total_cost += remaining
            remaining = Decimal("0")
            break

    if total_contracts == 0:
        return None

    return total_cost / total_contracts


def compute_contracts(stake: Decimal, fill_price: Decimal) -> Decimal:
    """floor(stake / fill_price, 2dp) — Kalshi count_fp format."""
    return (stake / fill_price).quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def nominal_multiplier(fill_price: Decimal) -> Decimal:
    """Display multiplier = 1 / fill_price (gross, includes stake return)."""
    return Decimal("1") / fill_price


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
