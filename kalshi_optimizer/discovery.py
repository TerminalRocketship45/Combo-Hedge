"""
Hardcoded market and collection tickers for NBA Finals Game 1: NYK at SAS (Jun 3, 2026).
Tickers confirmed via live API on 2026-06-01.
"""
from decimal import Decimal
from combos_nba import COMBOS

# ── Game 1: New York at San Antonio, Jun 3 2026 ────────────────────────────────
_GAME_SUFFIX = "26JUN03NYKSAS"

HARDCODED_MARKET_TICKERS: dict = {
    "spurs_win":          (f"KXNBAGAME-{_GAME_SUFFIX}-SAS",    f"KXNBAGAME-{_GAME_SUFFIX}"),
    "knicks_win":         (f"KXNBAGAME-{_GAME_SUFFIX}-NYK",    f"KXNBAGAME-{_GAME_SUFFIX}"),
    "total_over_217.5":   (f"KXNBATOTAL-{_GAME_SUFFIX}-217",   f"KXNBATOTAL-{_GAME_SUFFIX}"),
    "spurs_spread_4.5":   (f"KXNBASPREAD-{_GAME_SUFFIX}-SAS4",  f"KXNBASPREAD-{_GAME_SUFFIX}"),
    "spurs_spread_10.5":  (f"KXNBASPREAD-{_GAME_SUFFIX}-SAS10", f"KXNBASPREAD-{_GAME_SUFFIX}"),
    "spurs_spread_16.5":  (f"KXNBASPREAD-{_GAME_SUFFIX}-SAS16", f"KXNBASPREAD-{_GAME_SUFFIX}"),
    "knicks_spread_4.5":  (f"KXNBASPREAD-{_GAME_SUFFIX}-NYK4",  f"KXNBASPREAD-{_GAME_SUFFIX}"),
    "knicks_spread_10.5": (f"KXNBASPREAD-{_GAME_SUFFIX}-NYK10", f"KXNBASPREAD-{_GAME_SUFFIX}"),
    "knicks_spread_20.5": (f"KXNBASPREAD-{_GAME_SUFFIX}-NYK20", f"KXNBASPREAD-{_GAME_SUFFIX}"),
}

HARDCODED_COLLECTION_TICKER = f"KXMVENBASINGLEGAME-{_GAME_SUFFIX}"


def _combo_market_keys(combo: dict) -> tuple:
    winner = combo["winner"]
    margin = combo["margin"]
    gameline_key = f"{winner}_win"
    spread_key   = f"{winner}_spread_{margin}"
    total_key    = "total_over_217.5"
    return gameline_key, spread_key, total_key


def create_combo_market(
    client,
    collection_ticker: str,
    combo_def: dict,
    gameline_key: str,
    spread_key: str,
    total_key: str,
    market_tickers: dict,
) -> str:
    """POSTs to create a combo market. Returns the combo market ticker."""
    gl_ticker, gl_event   = market_tickers[gameline_key]
    sp_ticker, sp_event   = market_tickers[spread_key]
    tot_ticker, tot_event = market_tickers[total_key]

    body = {
        "selected_markets": [
            {"market_ticker": gl_ticker,  "event_ticker": gl_event,  "side": combo_def["gameline_side"]},
            {"market_ticker": sp_ticker,  "event_ticker": sp_event,  "side": combo_def["spread_side"]},
            {"market_ticker": tot_ticker, "event_ticker": tot_event, "side": combo_def["total_side"]},
        ],
        "with_market_payload": True,
    }
    resp = client.post(f"/multivariate_event_collections/{collection_ticker}", body)

    # Response: {"market_ticker": "...", "market": {...}, "event_ticker": "..."}
    if "market_ticker" in resp:
        return resp["market_ticker"]
    # Fallback for older API shape
    mv = resp.get("multivariate_market", resp.get("market", resp))
    return mv["ticker"]


def discover_all(client, series_ticker: str, cache) -> tuple:
    """
    Returns (market_tickers, combo_tickers).
    Uses hardcoded tickers for NBA Finals G1 (NYK at SAS, Jun 3 2026).
    Caches combo tickers (game-day TTL) to avoid re-creating combos on every run.
    """
    market_tickers    = HARDCODED_MARKET_TICKERS
    collection_ticker = HARDCODED_COLLECTION_TICKER

    combo_tickers = cache.get_tickers(series_ticker)
    if not combo_tickers:
        combo_tickers = {}
        for combo in COMBOS:
            gl_key, sp_key, tot_key = _combo_market_keys(combo)
            ticker = create_combo_market(
                client, collection_ticker, combo,
                gl_key, sp_key, tot_key, market_tickers,
            )
            combo_tickers[combo["id"]] = ticker
            print(f"    {combo['id']}: {ticker}")
        cache.set_tickers(series_ticker, combo_tickers)
    else:
        print(f"  (loaded {len(combo_tickers)} combo tickers from cache)")

    return market_tickers, combo_tickers
