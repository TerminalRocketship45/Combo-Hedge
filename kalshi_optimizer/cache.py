import json
import time
from pathlib import Path
from datetime import date


class KalshiCache:
    def __init__(self, cache_dir: str = None):
        if cache_dir is None:
            cache_dir = str(Path.home() / ".kalshi_optimizer")
        self._dir = Path(cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, series: str) -> Path:
        return self._dir / f"{series}.json"

    def _load(self, series: str) -> dict:
        p = self._path(series)
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, series: str, data: dict):
        self._path(series).write_text(json.dumps(data, indent=2))

    def get_tickers(self, series: str) -> dict | None:
        data = self._load(series)
        stored_date = data.get("date")
        if stored_date != date.today().isoformat():
            return None
        return data.get("combo_tickers") or None

    def set_tickers(self, series: str, tickers: dict):
        data = self._load(series)
        data["date"] = date.today().isoformat()
        data["combo_tickers"] = tickers
        self._save(series, data)

    def get_market_tickers(self, series: str) -> dict | None:
        data = self._load(series)
        if data.get("date") != date.today().isoformat():
            return None
        return data.get("market_tickers") or None

    def set_market_tickers(self, series: str, tickers: dict):
        data = self._load(series)
        data["date"] = date.today().isoformat()
        data["market_tickers"] = tickers
        self._save(series, data)

    def get_orderbook(self, series: str, ticker: str, ttl_seconds: int = 60) -> dict | None:
        data = self._load(series)
        ob = data.get("orderbooks", {}).get(ticker)
        if not ob:
            return None
        if time.time() - ob.get("fetched_at", 0) > ttl_seconds:
            return None
        return ob

    def set_orderbook(self, series: str, ticker: str, orderbook: dict):
        data = self._load(series)
        data.setdefault("orderbooks", {})[ticker] = {
            **orderbook,
            "fetched_at": time.time(),
        }
        self._save(series, data)

    def refresh(self, series: str):
        p = self._path(series)
        if p.exists():
            p.unlink()
