import time
import json
import tempfile
from pathlib import Path
from cache import KalshiCache

def make_cache(tmp_path):
    return KalshiCache(cache_dir=str(tmp_path))

def test_set_and_get_tickers(tmp_path):
    c = make_cache(tmp_path)
    c.set_tickers("KXNBA", {"C1": "KXNBA-ABC"})
    result = c.get_tickers("KXNBA")
    assert result == {"C1": "KXNBA-ABC"}

def test_tickers_persist_across_instances(tmp_path):
    c1 = make_cache(tmp_path)
    c1.set_tickers("KXNBA", {"C1": "KXNBA-ABC"})
    c2 = make_cache(tmp_path)
    assert c2.get_tickers("KXNBA") == {"C1": "KXNBA-ABC"}

def test_orderbook_ttl_fresh(tmp_path):
    c = make_cache(tmp_path)
    c.set_orderbook("KXNBA", "KXNBA-ABC", {"no_bids": [["0.93", "100"]]})
    result = c.get_orderbook("KXNBA", "KXNBA-ABC", ttl_seconds=60)
    assert result is not None
    assert result["no_bids"][0][0] == "0.93"

def test_orderbook_ttl_expired(tmp_path):
    c = make_cache(tmp_path)
    c.set_orderbook("KXNBA", "KXNBA-ABC", {"no_bids": []})
    data = json.loads((tmp_path / "KXNBA.json").read_text())
    data["orderbooks"]["KXNBA-ABC"]["fetched_at"] -= 120
    (tmp_path / "KXNBA.json").write_text(json.dumps(data))
    result = c.get_orderbook("KXNBA", "KXNBA-ABC", ttl_seconds=60)
    assert result is None

def test_refresh_clears_cache(tmp_path):
    c = make_cache(tmp_path)
    c.set_tickers("KXNBA", {"C1": "KXNBA-ABC"})
    c.refresh("KXNBA")
    assert c.get_tickers("KXNBA") is None
