from decimal import Decimal

REQUIRED_MARKET_KEYS = [
    "spurs_win", "knicks_win", "total_over_217.5",
    "spurs_spread_4.5", "spurs_spread_10.5", "spurs_spread_16.5",
    "knicks_spread_4.5", "knicks_spread_10.5", "knicks_spread_20.5",
]

_MARKET_PATTERNS = [
    ("spurs_win",          lambda t: "spurs" in t and "win" in t and "over" not in t and "by" not in t),
    ("knicks_win",         lambda t: "knicks" in t and "win" in t and "over" not in t and "by" not in t),
    ("total_over_217.5",   lambda t: "217.5" in t),
    ("spurs_spread_4.5",   lambda t: "spurs" in t and "4.5" in t and ("over" in t or "by" in t)),
    ("spurs_spread_10.5",  lambda t: "spurs" in t and "10.5" in t and ("over" in t or "by" in t)),
    ("spurs_spread_16.5",  lambda t: "spurs" in t and "16.5" in t and ("over" in t or "by" in t)),
    ("knicks_spread_4.5",  lambda t: "knicks" in t and "4.5" in t and ("over" in t or "by" in t)),
    ("knicks_spread_10.5", lambda t: "knicks" in t and "10.5" in t and ("over" in t or "by" in t)),
    ("knicks_spread_20.5", lambda t: "knicks" in t and "20.5" in t and ("over" in t or "by" in t)),
]


def find_nba_finals_series(client) -> str:
    resp = client.get("/series")
    for s in resp.get("series", []):
        title = s.get("title", "").lower()
        if "nba" in title and ("finals" in title or "game 1" in title or "game1" in title):
            return s["ticker"]
    for s in resp.get("series", []):
        if "nba" in s.get("ticker", "").lower() or "nba" in s.get("title", "").lower():
            return s["ticker"]
    raise RuntimeError("Could not find NBA Finals series. Use --series to specify.")


def find_game1_markets(client, series_ticker: str) -> dict:
    resp = client.get("/markets", params={"series_ticker": series_ticker, "status": "open"})
    markets = resp.get("markets", [])
    result = {}
    for key, matcher in _MARKET_PATTERNS:
        for m in markets:
            title = m.get("title", "").lower()
            if matcher(title):
                result[key] = (m["ticker"], m["event_ticker"])
                break
    missing = [k for k in REQUIRED_MARKET_KEYS if k not in result]
    if missing:
        raise RuntimeError(f"Could not find markets for: {missing}. Check series ticker.")
    return result


from combos_nba import COMBOS


def _combo_market_keys(combo: dict) -> tuple:
    winner = combo["winner"]
    margin = combo["margin"]
    total  = combo["total"]
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
    return resp["multivariate_market"]["ticker"]


def find_collection_ticker(client, series_ticker: str) -> str:
    resp = client.get("/multivariate_event_collections", params={"series_ticker": series_ticker})
    collections = resp.get("multivariate_event_collections", [])
    if not collections:
        raise RuntimeError(f"No combo collections found for series {series_ticker}")
    return collections[0]["ticker"]


def discover_all(client, series_ticker: str, cache) -> tuple:
    market_tickers = cache.get_market_tickers(series_ticker)
    if not market_tickers:
        market_tickers = find_game1_markets(client, series_ticker)
        cache.set_market_tickers(series_ticker, {k: list(v) for k, v in market_tickers.items()})
    else:
        market_tickers = {k: tuple(v) for k, v in market_tickers.items()}

    combo_tickers = cache.get_tickers(series_ticker)
    if not combo_tickers:
        collection_ticker = find_collection_ticker(client, series_ticker)
        combo_tickers = {}
        for combo in COMBOS:
            gl_key, sp_key, tot_key = _combo_market_keys(combo)
            ticker = create_combo_market(
                client, collection_ticker, combo, gl_key, sp_key, tot_key, market_tickers
            )
            combo_tickers[combo["id"]] = ticker
        cache.set_tickers(series_ticker, combo_tickers)

    return market_tickers, combo_tickers
