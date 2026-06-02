from unittest.mock import MagicMock
from discovery import find_nba_finals_series, find_game1_markets, create_combo_market

MOCK_SERIES = [
    {"ticker": "KXNBAFINALSGA", "title": "NBA Finals Game 1", "status": "open"},
    {"ticker": "KXNBA", "title": "NBA", "status": "open"},
]

MOCK_MARKETS = [
    {"ticker": "KXNBA-SPURSWIN",   "title": "Will the Spurs win Game 1?",         "category": "moneyline", "event_ticker": "KXNBA-G1", "yes_ask": "0.6300"},
    {"ticker": "KXNBA-KNICKSWIN",  "title": "Will the Knicks win Game 1?",        "category": "moneyline", "event_ticker": "KXNBA-G1", "yes_ask": "0.3700"},
    {"ticker": "KXNBA-OVER217",    "title": "Over 217.5 total points",             "category": "totals",    "event_ticker": "KXNBA-G1", "yes_ask": "0.5400"},
    {"ticker": "KXNBA-SPURS4.5",   "title": "Spurs win by over 4.5 pts",          "category": "spread",    "event_ticker": "KXNBA-G1", "yes_ask": "0.5300"},
    {"ticker": "KXNBA-SPURS10.5",  "title": "Spurs win by over 10.5 pts",         "category": "spread",    "event_ticker": "KXNBA-G1", "yes_ask": "0.3300"},
    {"ticker": "KXNBA-SPURS16.5",  "title": "Spurs win by over 16.5 pts",         "category": "spread",    "event_ticker": "KXNBA-G1", "yes_ask": "0.2100"},
    {"ticker": "KXNBA-KNICKS4.5",  "title": "Knicks win by over 4.5 pts",         "category": "spread",    "event_ticker": "KXNBA-G1", "yes_ask": "0.2800"},
    {"ticker": "KXNBA-KNICKS10.5", "title": "Knicks win by over 10.5 pts",        "category": "spread",    "event_ticker": "KXNBA-G1", "yes_ask": "0.1400"},
    {"ticker": "KXNBA-KNICKS20.5", "title": "Knicks win by over 20.5 pts",        "category": "spread",    "event_ticker": "KXNBA-G1", "yes_ask": "0.0500"},
]

def test_find_nba_finals_series():
    client = MagicMock()
    client.get.return_value = {"series": MOCK_SERIES}
    ticker = find_nba_finals_series(client)
    assert ticker == "KXNBAFINALSGA"

def test_find_game1_markets_returns_9_tickers():
    client = MagicMock()
    client.get.return_value = {"markets": MOCK_MARKETS}
    tickers = find_game1_markets(client, "KXNBAFINALSGA")
    assert "spurs_win" in tickers
    assert "knicks_win" in tickers
    assert "total_over_217.5" in tickers
    assert "spurs_spread_4.5" in tickers
    assert "knicks_spread_20.5" in tickers

def test_create_combo_market_returns_ticker():
    client = MagicMock()
    client.post.return_value = {
        "multivariate_market": {"ticker": "KXNBA-COMBO-ABC123"}
    }
    combo_def = {
        "gameline_side": "yes", "spread_side": "no", "total_side": "yes"
    }
    market_tickers = {
        "spurs_win":         ("KXNBA-SPURSWIN",  "KXNBA-G1"),
        "spurs_spread_4.5":  ("KXNBA-SPURS4.5",  "KXNBA-G1"),
        "total_over_217.5":  ("KXNBA-OVER217",   "KXNBA-G1"),
    }
    result = create_combo_market(
        client, "KXNBA-COLL", combo_def,
        gameline_key="spurs_win",
        spread_key="spurs_spread_4.5",
        total_key="total_over_217.5",
        market_tickers=market_tickers,
    )
    assert result == "KXNBA-COMBO-ABC123"
    client.post.assert_called_once()

def test_find_nba_finals_series_fallback():
    client = MagicMock()
    client.get.return_value = {"series": [
        {"ticker": "KXNBA", "title": "NBA Regular Season"},
    ]}
    # Should return the NBA series even without "Finals" in title
    ticker = find_nba_finals_series(client)
    assert ticker == "KXNBA"
