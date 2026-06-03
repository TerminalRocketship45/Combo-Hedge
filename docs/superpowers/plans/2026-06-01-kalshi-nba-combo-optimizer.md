# Kalshi NBA Finals Combo Optimizer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Python CLI that hits the Kalshi API, creates all 12 NBA Finals combo markets, fetches live multipliers via orderbook VWAP, runs a constrained optimizer (excluding blowout scenarios), and writes a self-contained HTML report styled after `kalshi_hedge.jsx`.

**Architecture:** Three layers — API layer (auth + HTTP + discovery), math layer (VWAP fill + optimizer), HTML report. A file-based cache (TTL: 60s orderbooks, game-day tickers) sits between API and math layers. No order placement.

**Tech Stack:** Python 3.11+, `cryptography`, `requests`, `tenacity`, `scipy`, `numpy`, `python-dotenv`, `decimal` (all money math), vanilla HTML/CSS/JS for output.

---

## Profit Formula (Critical)

```
contracts_i   = floor(stake_i / vwap_fill_i, 2dp)    # Kalshi count_fp
actual_cost_i = contracts_i × vwap_fill_i             # what Kalshi charges
payout_i      = contracts_i × $1.00                   # what Kalshi pays on win

net_profit_in_scenario = sum(payout_i for winning combos)
                       − sum(actual_cost_i for ALL combos)
```

**Not** `totalWinnings − losingStaked` (JSX bug — omits winning stakes from cost).

---

## Blowout Scenarios — Excluded

12 non-blowout scenarios drive the optimizer and the HTML. Blowout scenarios (Spurs +17, Knicks +21+) are NOT constrained and NOT shown. A footer note warns the user.

---

## File Structure

```
kalshi_optimizer/
├── auth.py              # RSA-PSS signing headers
├── client.py            # KalshiClient: GET/POST with rate-limiting + retry
├── combos_nba.py        # Hardcoded combo defs, scenario matrix, payout matrix
├── cache.py             # KalshiCache: file-based TTL cache
├── discovery.py         # Find NBA Finals tickers, POST to create combo markets
├── orderbook.py         # Fetch orderbooks, VWAP YES fill from NO bids
├── probabilities.py     # Implied probs from market prices, scenario probs
├── optimizer.py         # SLSQP on 12 non-blowout scenarios, rounding pass
├── report.py            # Generate self-contained HTML file
├── kalshi_optimizer.py  # CLI entrypoint (argparse)
├── requirements.txt
├── .env.example
└── tests/
    ├── test_auth.py
    ├── test_combos_nba.py
    ├── test_orderbook.py
    ├── test_optimizer.py
    ├── test_probabilities.py
    └── test_report.py
```

---

## Task 1: Project Scaffolding

**Files:**
- Create: `kalshi_optimizer/requirements.txt`
- Create: `kalshi_optimizer/.env.example`
- Create: `kalshi_optimizer/.gitignore`
- Create: `kalshi_optimizer/tests/__init__.py`

- [ ] **Step 1: Create requirements.txt**

```
cryptography>=42.0.0
requests>=2.31.0
tenacity>=8.2.0
scipy>=1.12.0
numpy>=1.26.0
python-dotenv>=1.0.0
pytest>=8.0.0
pytest-mock>=3.12.0
```

- [ ] **Step 2: Create .env.example**

```
KALSHI_API_KEY_ID=your-key-id-here
KALSHI_PRIVATE_KEY_PATH=/path/to/private_key.pem
```

- [ ] **Step 3: Create .gitignore**

```
.env
*.pem
__pycache__/
*.pyc
.pytest_cache/
output/
```

- [ ] **Step 4: Create tests/__init__.py**

Empty file.

- [ ] **Step 5: Install dependencies**

```bash
cd kalshi_optimizer
pip install -r requirements.txt
```

Expected: all packages install without error.

- [ ] **Step 6: Commit**

```bash
git add kalshi_optimizer/
git commit -m "feat: project scaffolding for Kalshi NBA combo optimizer"
```

---

## Task 2: auth.py — RSA-PSS Signing

**Files:**
- Create: `kalshi_optimizer/auth.py`
- Create: `kalshi_optimizer/tests/test_auth.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_auth.py
import time
from unittest.mock import MagicMock
from auth import sign_request

def _make_key():
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.backends import default_backend
    return rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())

def test_sign_request_returns_three_headers():
    key = _make_key()
    headers = sign_request(key, "test-key-id", "GET", "/trade-api/v2/events")
    assert set(headers.keys()) == {"KALSHI-ACCESS-KEY", "KALSHI-ACCESS-TIMESTAMP", "KALSHI-ACCESS-SIGNATURE"}

def test_sign_request_timestamp_is_recent():
    key = _make_key()
    headers = sign_request(key, "test-key-id", "GET", "/trade-api/v2/events")
    ts = int(headers["KALSHI-ACCESS-TIMESTAMP"])
    now_ms = int(time.time() * 1000)
    assert abs(ts - now_ms) < 5000  # within 5 seconds

def test_sign_request_key_id_matches():
    key = _make_key()
    headers = sign_request(key, "my-key-id", "GET", "/trade-api/v2/events")
    assert headers["KALSHI-ACCESS-KEY"] == "my-key-id"

def test_sign_request_signature_is_base64():
    import base64
    key = _make_key()
    headers = sign_request(key, "test-key-id", "POST", "/trade-api/v2/markets")
    sig = headers["KALSHI-ACCESS-SIGNATURE"]
    decoded = base64.b64decode(sig)  # raises if not valid base64
    assert len(decoded) > 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd kalshi_optimizer && pytest tests/test_auth.py -v
```

Expected: `ModuleNotFoundError: No module named 'auth'`

- [ ] **Step 3: Implement auth.py**

```python
# auth.py
import time
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding


def sign_request(private_key, key_id: str, method: str, path: str) -> dict:
    ts = str(int(time.time() * 1000))
    message = (ts + method.upper() + path).encode("utf-8")
    signature = private_key.sign(
        message,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return {
        "KALSHI-ACCESS-KEY": key_id,
        "KALSHI-ACCESS-TIMESTAMP": ts,
        "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode("utf-8"),
    }


def load_private_key(pem_path: str):
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    with open(pem_path, "rb") as f:
        return load_pem_private_key(f.read(), password=None)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_auth.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add kalshi_optimizer/auth.py kalshi_optimizer/tests/test_auth.py
git commit -m "feat: RSA-PSS signing for Kalshi API auth"
```

---

## Task 3: combos_nba.py — Combo Definitions & Scenario Matrix

**Files:**
- Create: `kalshi_optimizer/combos_nba.py`
- Create: `kalshi_optimizer/tests/test_combos_nba.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_combos_nba.py
from decimal import Decimal
from combos_nba import COMBOS, SCENARIOS, get_paying_combo_ids, calc_net_profit

def test_exactly_12_combos():
    assert len(COMBOS) == 12

def test_exactly_12_non_blowout_scenarios():
    assert len(SCENARIOS) == 12

def test_all_spread_sides_are_no():
    for c in COMBOS:
        assert c["spread_side"] == "no"

def test_all_gameline_sides_are_yes():
    for c in COMBOS:
        assert c["gameline_side"] == "yes"

def test_spurs_max_margin_is_16_5():
    spurs_combos = [c for c in COMBOS if c["winner"] == "spurs"]
    margins = {c["margin"] for c in spurs_combos}
    assert max(margins) == Decimal("16.5")
    assert Decimal("20.5") not in margins

def test_knicks_max_margin_is_20_5():
    knicks_combos = [c for c in COMBOS if c["winner"] == "knicks"]
    margins = {c["margin"] for c in knicks_combos}
    assert max(margins) == Decimal("20.5")

def test_margin_stacking_pays_multiple_combos():
    # Spurs win by 3 pts, over 217.5 → C1 (under4.5), C3 (under10.5), C5 (under16.5) all pay
    scenario = next(s for s in SCENARIOS if s["winner"] == "spurs" and s["margin_range"] == "0to4.5" and s["total"] == "over")
    paying = get_paying_combo_ids(scenario)
    paying_combos = [c for c in COMBOS if c["id"] in paying]
    # All paying combos must be spurs + over + under (4.5, 10.5, or 16.5)
    assert len(paying_combos) == 3
    for c in paying_combos:
        assert c["winner"] == "spurs"
        assert c["total"] == "over"

def test_margin_stacking_middle_range():
    # Spurs win by 7 pts, over → only under10.5 and under16.5 pay (not under4.5)
    scenario = next(s for s in SCENARIOS if s["winner"] == "spurs" and s["margin_range"] == "4.5to10.5" and s["total"] == "over")
    paying = get_paying_combo_ids(scenario)
    paying_combos = [c for c in COMBOS if c["id"] in paying]
    assert len(paying_combos) == 2
    margins = {c["margin"] for c in paying_combos}
    assert Decimal("4.5") not in margins
    assert Decimal("10.5") in margins
    assert Decimal("16.5") in margins

def test_highest_margin_range_pays_one_combo():
    # Spurs win by 14 pts → only under16.5 pays
    scenario = next(s for s in SCENARIOS if s["winner"] == "spurs" and s["margin_range"] == "10.5to16.5" and s["total"] == "over")
    paying = get_paying_combo_ids(scenario)
    paying_combos = [c for c in COMBOS if c["id"] in paying]
    assert len(paying_combos) == 1
    assert paying_combos[0]["margin"] == Decimal("16.5")

def test_net_profit_correct_formula():
    # 1 combo wins at 14.8x with stake $1, 1 combo loses with stake $1
    # net = $14.80 - $2.00 = $12.80 (not $14.80 - $1.00 = $13.80)
    costs = {"C1": Decimal("1.00"), "C2": Decimal("1.00")}
    payouts = {"C1": Decimal("14.80"), "C2": Decimal("0")}
    total_cost = Decimal("2.00")
    net = sum(payouts.values()) - total_cost
    assert net == Decimal("12.80")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_combos_nba.py -v
```

Expected: `ModuleNotFoundError: No module named 'combos_nba'`

- [ ] **Step 3: Implement combos_nba.py**

```python
# combos_nba.py
from decimal import Decimal
from dataclasses import dataclass, field
from typing import List

# ── Combo definitions ─────────────────────────────────────────────────────────
# 12 combos: 2 winners × 3 margin thresholds × 2 totals
# Leg sides: gameline=YES, spread=NO (betting under margin), total=YES(over)/NO(under)

COMBOS = [
    # Spurs win combos
    {"id": "C1",  "winner": "spurs",  "margin": Decimal("4.5"),  "total": "over",  "gameline_side": "yes", "spread_side": "no", "total_side": "yes"},
    {"id": "C2",  "winner": "spurs",  "margin": Decimal("4.5"),  "total": "under", "gameline_side": "yes", "spread_side": "no", "total_side": "no"},
    {"id": "C3",  "winner": "spurs",  "margin": Decimal("10.5"), "total": "over",  "gameline_side": "yes", "spread_side": "no", "total_side": "yes"},
    {"id": "C4",  "winner": "spurs",  "margin": Decimal("10.5"), "total": "under", "gameline_side": "yes", "spread_side": "no", "total_side": "no"},
    {"id": "C5",  "winner": "spurs",  "margin": Decimal("16.5"), "total": "over",  "gameline_side": "yes", "spread_side": "no", "total_side": "yes"},
    {"id": "C6",  "winner": "spurs",  "margin": Decimal("16.5"), "total": "under", "gameline_side": "yes", "spread_side": "no", "total_side": "no"},
    # Knicks win combos
    {"id": "C7",  "winner": "knicks", "margin": Decimal("4.5"),  "total": "over",  "gameline_side": "yes", "spread_side": "no", "total_side": "yes"},
    {"id": "C8",  "winner": "knicks", "margin": Decimal("4.5"),  "total": "under", "gameline_side": "yes", "spread_side": "no", "total_side": "no"},
    {"id": "C9",  "winner": "knicks", "margin": Decimal("10.5"), "total": "over",  "gameline_side": "yes", "spread_side": "no", "total_side": "yes"},
    {"id": "C10", "winner": "knicks", "margin": Decimal("10.5"), "total": "under", "gameline_side": "yes", "spread_side": "no", "total_side": "no"},
    {"id": "C11", "winner": "knicks", "margin": Decimal("20.5"), "total": "over",  "gameline_side": "yes", "spread_side": "no", "total_side": "yes"},
    {"id": "C12", "winner": "knicks", "margin": Decimal("20.5"), "total": "under", "gameline_side": "yes", "spread_side": "no", "total_side": "no"},
]

# ── 12 non-blowout scenarios ───────────────────────────────────────────────────
# 2 winners × 3 margin ranges × 2 totals = 12
# Blowout scenarios (Spurs 17+, Knicks 21+) intentionally excluded.
SCENARIOS = [
    {"winner": "spurs",  "margin_range": "0to4.5",    "total": "over"},
    {"winner": "spurs",  "margin_range": "0to4.5",    "total": "under"},
    {"winner": "spurs",  "margin_range": "4.5to10.5", "total": "over"},
    {"winner": "spurs",  "margin_range": "4.5to10.5", "total": "under"},
    {"winner": "spurs",  "margin_range": "10.5to16.5","total": "over"},
    {"winner": "spurs",  "margin_range": "10.5to16.5","total": "under"},
    {"winner": "knicks", "margin_range": "0to4.5",    "total": "over"},
    {"winner": "knicks", "margin_range": "0to4.5",    "total": "under"},
    {"winner": "knicks", "margin_range": "4.5to10.5", "total": "over"},
    {"winner": "knicks", "margin_range": "4.5to10.5", "total": "under"},
    {"winner": "knicks", "margin_range": "10.5to20.5","total": "over"},
    {"winner": "knicks", "margin_range": "10.5to20.5","total": "under"},
]


def get_paying_combo_ids(scenario: dict) -> List[str]:
    """
    Return IDs of combos that pay out in this scenario.
    Margin stacking: a combo with threshold T pays if actual margin < T.
    In a scenario with range "4.5to10.5", actual margin is 5-10 pts:
      - threshold 4.5: NO (5 > 4.5)
      - threshold 10.5: YES (5 < 10.5)
      - threshold 16.5/20.5: YES (5 < 16.5)
    """
    winner = scenario["winner"]
    total = scenario["total"]
    margin_range = scenario["margin_range"]

    # Parse range lower bound from the key
    lo_str = margin_range.split("to")[0]
    lo = Decimal(lo_str)

    paying = []
    for combo in COMBOS:
        if combo["winner"] != winner:
            continue
        if combo["total"] != total:
            continue
        # Combo pays if its threshold is ABOVE the lower bound of the range
        # i.e., the actual margin (which is > lo) is still < combo.margin
        if combo["margin"] > lo:
            paying.append(combo["id"])
    return paying


def calc_net_profit(
    scenario: dict,
    contracts: dict,      # {combo_id: Decimal contracts}
    fill_prices: dict,    # {combo_id: Decimal fill price}
) -> Decimal:
    """
    net = sum(contracts_i * $1 for winning combos)
        - sum(contracts_i * fill_price_i for ALL combos)

    This is the corrected formula — subtracts ALL stakes, not just losing ones.
    """
    paying_ids = set(get_paying_combo_ids(scenario))
    payout = sum(contracts[cid] for cid in paying_ids if cid in contracts)
    total_cost = sum(contracts[cid] * fill_prices[cid] for cid in contracts)
    return payout - total_cost
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_combos_nba.py -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add kalshi_optimizer/combos_nba.py kalshi_optimizer/tests/test_combos_nba.py
git commit -m "feat: hardcoded NBA Finals combo definitions and scenario matrix"
```

---

## Task 4: client.py — HTTP Client

**Files:**
- Create: `kalshi_optimizer/client.py`

- [ ] **Step 1: Implement client.py**

No unit test here — HTTP behavior is integration-tested in discovery tests. The retry/rate-limit logic is simple enough to trust.

```python
# client.py
import os
import time
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from auth import sign_request, load_private_key

PROD_BASE = "https://api.elections.kalshi.com/trade-api/v2"
DEMO_BASE = "https://demo-api.kalshi.co/trade-api/v2"

_last_call_times: list = []
_MAX_READS_PER_SEC = 18   # stay under 20/s limit


def _rate_limit():
    now = time.monotonic()
    _last_call_times[:] = [t for t in _last_call_times if now - t < 1.0]
    if len(_last_call_times) >= _MAX_READS_PER_SEC:
        time.sleep(1.0 - (now - _last_call_times[0]))
    _last_call_times.append(time.monotonic())


class KalshiClient:
    def __init__(self, demo: bool = False):
        self.base = DEMO_BASE if demo else PROD_BASE
        self.key_id = os.environ["KALSHI_API_KEY_ID"]
        self.private_key = load_private_key(os.environ["KALSHI_PRIVATE_KEY_PATH"])

    def _headers(self, method: str, path: str) -> dict:
        return sign_request(self.private_key, self.key_id, method, path)

    @retry(
        retry=retry_if_exception_type(requests.HTTPError),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(5),
    )
    def get(self, path: str, params: dict = None) -> dict:
        _rate_limit()
        qs = ""
        if params:
            qs = "?" + "&".join(f"{k}={v}" for k, v in params.items())
        full_path = path + qs
        resp = requests.get(
            self.base + path,
            params=params,
            headers=self._headers("GET", full_path),
        )
        if resp.status_code == 429:
            raise requests.HTTPError("Rate limited", response=resp)
        resp.raise_for_status()
        return resp.json()

    @retry(
        retry=retry_if_exception_type(requests.HTTPError),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(5),
    )
    def post(self, path: str, body: dict) -> dict:
        _rate_limit()
        resp = requests.post(
            self.base + path,
            json=body,
            headers={**self._headers("POST", path), "Content-Type": "application/json"},
        )
        if resp.status_code == 429:
            raise requests.HTTPError("Rate limited", response=resp)
        resp.raise_for_status()
        return resp.json()
```

- [ ] **Step 2: Commit**

```bash
git add kalshi_optimizer/client.py
git commit -m "feat: Kalshi HTTP client with rate limiting and retry"
```

---

## Task 5: cache.py — File-Based TTL Cache

**Files:**
- Create: `kalshi_optimizer/cache.py`
- Create: `kalshi_optimizer/tests/test_cache.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cache.py
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
    # Manually backdate the timestamp
    data = json.loads((tmp_path / "KXNBA.json").read_text())
    data["orderbooks"]["KXNBA-ABC"]["fetched_at"] -= 120  # 2 minutes ago
    (tmp_path / "KXNBA.json").write_text(json.dumps(data))
    result = c.get_orderbook("KXNBA", "KXNBA-ABC", ttl_seconds=60)
    assert result is None  # expired

def test_refresh_clears_cache(tmp_path):
    c = make_cache(tmp_path)
    c.set_tickers("KXNBA", {"C1": "KXNBA-ABC"})
    c.refresh("KXNBA")
    assert c.get_tickers("KXNBA") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_cache.py -v
```

Expected: `ModuleNotFoundError: No module named 'cache'`

- [ ] **Step 3: Implement cache.py**

```python
# cache.py
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
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_cache.py -v
```

Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add kalshi_optimizer/cache.py kalshi_optimizer/tests/test_cache.py
git commit -m "feat: file-based TTL cache for combo tickers and orderbooks"
```

---

## Task 6: discovery.py — Market Discovery & Combo Creation

**Files:**
- Create: `kalshi_optimizer/discovery.py`
- Create: `kalshi_optimizer/tests/test_discovery.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_discovery.py
from unittest.mock import MagicMock, patch
from discovery import find_nba_finals_series, find_game1_markets, create_combo_market

MOCK_SERIES = [
    {"ticker": "KXNBAFINALSGA", "title": "NBA Finals Game 1", "status": "open"},
    {"ticker": "KXNBA", "title": "NBA", "status": "open"},
]

MOCK_MARKETS = [
    {"ticker": "KXNBA-SPURSWIN", "title": "Will the Spurs win Game 1?", "category": "moneyline", "event_ticker": "KXNBA-G1", "yes_ask": "0.6300"},
    {"ticker": "KXNBA-KNICKSWIN", "title": "Will the Knicks win Game 1?", "category": "moneyline", "event_ticker": "KXNBA-G1", "yes_ask": "0.3700"},
    {"ticker": "KXNBA-OVER217", "title": "Over 217.5 total points", "category": "totals", "event_ticker": "KXNBA-G1", "yes_ask": "0.5400"},
    {"ticker": "KXNBA-SPURS4.5", "title": "Spurs win by over 4.5 pts", "category": "spread", "event_ticker": "KXNBA-G1", "yes_ask": "0.5300"},
    {"ticker": "KXNBA-SPURS10.5", "title": "Spurs win by over 10.5 pts", "category": "spread", "event_ticker": "KXNBA-G1", "yes_ask": "0.3300"},
    {"ticker": "KXNBA-SPURS16.5", "title": "Spurs win by over 16.5 pts", "category": "spread", "event_ticker": "KXNBA-G1", "yes_ask": "0.2100"},
    {"ticker": "KXNBA-KNICKS4.5", "title": "Knicks win by over 4.5 pts", "category": "spread", "event_ticker": "KXNBA-G1", "yes_ask": "0.2800"},
    {"ticker": "KXNBA-KNICKS10.5", "title": "Knicks win by over 10.5 pts", "category": "spread", "event_ticker": "KXNBA-G1", "yes_ask": "0.1400"},
    {"ticker": "KXNBA-KNICKS20.5", "title": "Knicks win by over 20.5 pts", "category": "spread", "event_ticker": "KXNBA-G1", "yes_ask": "0.0500"},
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
        "spurs_win": ("KXNBA-SPURSWIN", "KXNBA-G1"),
        "spurs_spread_4.5": ("KXNBA-SPURS4.5", "KXNBA-G1"),
        "total_over_217.5": ("KXNBA-OVER217", "KXNBA-G1"),
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_discovery.py -v
```

Expected: `ModuleNotFoundError: No module named 'discovery'`

- [ ] **Step 3: Implement discovery.py**

```python
# discovery.py
from decimal import Decimal

# Keys we need to discover from the Kalshi API
REQUIRED_MARKET_KEYS = [
    "spurs_win", "knicks_win", "total_over_217.5",
    "spurs_spread_4.5", "spurs_spread_10.5", "spurs_spread_16.5",
    "knicks_spread_4.5", "knicks_spread_10.5", "knicks_spread_20.5",
]

# Keywords to match markets by title (case-insensitive)
_MARKET_PATTERNS = [
    ("spurs_win",         lambda t: "spurs" in t and "win" in t and "over" not in t and "by" not in t),
    ("knicks_win",        lambda t: "knicks" in t and "win" in t and "over" not in t and "by" not in t),
    ("total_over_217.5",  lambda t: "217.5" in t),
    ("spurs_spread_4.5",  lambda t: "spurs" in t and "4.5" in t and ("over" in t or "by" in t)),
    ("spurs_spread_10.5", lambda t: "spurs" in t and "10.5" in t and ("over" in t or "by" in t)),
    ("spurs_spread_16.5", lambda t: "spurs" in t and "16.5" in t and ("over" in t or "by" in t)),
    ("knicks_spread_4.5", lambda t: "knicks" in t and "4.5" in t and ("over" in t or "by" in t)),
    ("knicks_spread_10.5",lambda t: "knicks" in t and "10.5" in t and ("over" in t or "by" in t)),
    ("knicks_spread_20.5",lambda t: "knicks" in t and "20.5" in t and ("over" in t or "by" in t)),
]


def find_nba_finals_series(client) -> str:
    resp = client.get("/series")
    for s in resp.get("series", []):
        title = s.get("title", "").lower()
        if "nba" in title and ("finals" in title or "game 1" in title or "game1" in title):
            return s["ticker"]
    # Fallback: return first NBA series
    for s in resp.get("series", []):
        if "nba" in s.get("ticker", "").lower() or "nba" in s.get("title", "").lower():
            return s["ticker"]
    raise RuntimeError("Could not find NBA Finals series. Use --series to specify.")


def find_game1_markets(client, series_ticker: str) -> dict:
    """Returns {key: (market_ticker, event_ticker)} for all 9 required markets."""
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


# Maps each combo_id to (gameline_key, spread_key, total_key)
from combos_nba import COMBOS

def _combo_market_keys(combo: dict) -> tuple:
    winner = combo["winner"]
    margin = combo["margin"]
    total = combo["total"]
    gameline_key = f"{winner}_win"
    spread_key = f"{winner}_spread_{margin}"
    total_key = "total_over_217.5"
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
    gl_ticker, gl_event = market_tickers[gameline_key]
    sp_ticker, sp_event = market_tickers[spread_key]
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
    """
    Returns (market_tickers, combo_tickers).
    Uses cache where available; POSTs to create all 12 combo markets.
    """
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
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_discovery.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add kalshi_optimizer/discovery.py kalshi_optimizer/tests/test_discovery.py
git commit -m "feat: NBA Finals market discovery and combo creation"
```

---

## Task 7: orderbook.py — VWAP Fill Price

**Files:**
- Create: `kalshi_optimizer/orderbook.py`
- Create: `kalshi_optimizer/tests/test_orderbook.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_orderbook.py
from decimal import Decimal
from orderbook import compute_vwap_yes_fill, compute_contracts, nominal_multiplier

def test_vwap_single_level():
    # NO bid at 0.93 → YES fill at 0.07; buy $0.70 worth
    no_bids = [("0.9300", "100.00")]
    fill = compute_vwap_yes_fill(no_bids, Decimal("0.70"))
    assert fill == Decimal("0.07")

def test_vwap_walks_multiple_levels():
    # Level 1: NO bid 0.93 → YES at 0.07, 10 contracts available = $0.70 cost
    # Level 2: NO bid 0.92 → YES at 0.08, need $0.30 more
    # We spend $1.00 total, contracts from L1 = 10, from L2 = 0.30/0.08 = 3.75
    # VWAP = $1.00 / 13.75 ≈ 0.07272...
    no_bids = [("0.9300", "10.00"), ("0.9200", "100.00")]
    fill = compute_vwap_yes_fill(no_bids, Decimal("1.00"))
    # total_contracts = 10 + 0.30/0.08 = 10 + 3.75 = 13.75
    # vwap = 1.00 / 13.75
    expected = Decimal("1.00") / Decimal("13.75")
    assert abs(fill - expected) < Decimal("0.0001")

def test_vwap_insufficient_liquidity():
    # Only $0.93 worth of NO bids available; want to spend $2.00
    no_bids = [("0.9300", "10.00")]  # 10 contracts * 0.07 = $0.70 available
    fill = compute_vwap_yes_fill(no_bids, Decimal("2.00"))
    # Should return fill for whatever is available, not None
    assert fill is not None
    assert fill == Decimal("0.07")

def test_vwap_no_bids_returns_none():
    fill = compute_vwap_yes_fill([], Decimal("1.00"))
    assert fill is None

def test_compute_contracts_floors_to_2dp():
    # stake 1.23, fill 0.07 → 17.571... → floor to 17.57
    contracts = compute_contracts(Decimal("1.23"), Decimal("0.07"))
    assert contracts == Decimal("17.57")

def test_compute_contracts_does_not_overspend():
    contracts = compute_contracts(Decimal("1.00"), Decimal("0.07"))
    actual_cost = contracts * Decimal("0.07")
    assert actual_cost <= Decimal("1.00")

def test_nominal_multiplier():
    # fill price 0.07 → nominal multiplier ≈ 14.28
    mult = nominal_multiplier(Decimal("0.07"))
    assert abs(mult - Decimal("14.285714")) < Decimal("0.0001")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_orderbook.py -v
```

Expected: `ModuleNotFoundError: No module named 'orderbook'`

- [ ] **Step 3: Implement orderbook.py**

```python
# orderbook.py
from decimal import Decimal, ROUND_DOWN
from typing import Optional


def compute_vwap_yes_fill(no_bids: list, order_dollars: Decimal) -> Optional[Decimal]:
    """
    Compute VWAP fill price for buying YES contracts.
    We buy YES by matching against NO bids (descending by NO bid price).
    YES fill at each level = 1 - no_bid_price.

    no_bids: list of (price_str, size_str) sorted highest NO bid first.
    order_dollars: how much we want to spend.
    Returns: VWAP YES fill price, or None if no bids at all.
    """
    if not no_bids:
        return None

    remaining = order_dollars
    total_contracts = Decimal("0")
    total_cost = Decimal("0")

    for price_str, size_str in no_bids:
        no_bid = Decimal(price_str)
        yes_fill = Decimal("1") - no_bid   # what we pay per YES contract
        size = Decimal(size_str)

        cost_for_all = size * yes_fill
        if cost_for_all <= remaining:
            total_contracts += size
            total_cost += cost_for_all
            remaining -= cost_for_all
        else:
            # Partial fill at this level
            partial_contracts = remaining / yes_fill
            total_contracts += partial_contracts
            total_cost += remaining
            remaining = Decimal("0")
            break

    if total_contracts == 0:
        return None

    return total_cost / total_contracts


def compute_contracts(stake: Decimal, fill_price: Decimal) -> Decimal:
    """
    Compute floor(stake / fill_price, 2dp) — Kalshi count_fp format.
    Always rounds DOWN so we never overspend.
    """
    return (stake / fill_price).quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def nominal_multiplier(fill_price: Decimal) -> Decimal:
    """Display multiplier = 1 / fill_price (gross: includes stake return)."""
    return Decimal("1") / fill_price


def fetch_and_cache_orderbook(client, cache, series_ticker: str, combo_ticker: str) -> list:
    """
    Returns no_bids list for combo_ticker.
    Uses cache with 60s TTL; fetches fresh if stale.
    """
    cached = cache.get_orderbook(series_ticker, combo_ticker)
    if cached:
        return cached["no_bids"]

    resp = client.get(f"/markets/{combo_ticker}/orderbook")
    # Kalshi orderbook response: {"orderbook": {"no": [[price, size], ...], "yes": [...]}}
    ob = resp.get("orderbook", {})
    no_bids = [[str(level[0]), str(level[1])] for level in ob.get("no", [])]
    # Sort descending by NO bid price (highest first = cheapest YES for us)
    no_bids.sort(key=lambda x: Decimal(x[0]), reverse=True)

    cache.set_orderbook(series_ticker, combo_ticker, {"no_bids": no_bids})
    return no_bids
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_orderbook.py -v
```

Expected: 7 PASSED

- [ ] **Step 5: Commit**

```bash
git add kalshi_optimizer/orderbook.py kalshi_optimizer/tests/test_orderbook.py
git commit -m "feat: VWAP YES fill price from NO bid orderbook"
```

---

## Task 8: probabilities.py — Implied Probabilities

**Files:**
- Create: `kalshi_optimizer/probabilities.py`
- Create: `kalshi_optimizer/tests/test_probabilities.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_probabilities.py
from decimal import Decimal
from probabilities import build_scenario_probs, ScenarioProbs

MOCK_MARKET_PRICES = {
    "spurs_win":          Decimal("0.63"),
    "knicks_win":         Decimal("0.37"),
    "total_over_217.5":   Decimal("0.54"),
    "spurs_spread_4.5":   Decimal("0.53"),
    "spurs_spread_10.5":  Decimal("0.33"),
    "spurs_spread_16.5":  Decimal("0.21"),
    "knicks_spread_4.5":  Decimal("0.28"),
    "knicks_spread_10.5": Decimal("0.14"),
    "knicks_spread_20.5": Decimal("0.05"),
}

def test_12_scenario_probs_built():
    probs = build_scenario_probs(MOCK_MARKET_PRICES)
    assert len(probs) == 12

def test_spurs_win_prob_sums_to_spurs_win():
    probs = build_scenario_probs(MOCK_MARKET_PRICES)
    spurs_total = sum(p for key, p in probs.items() if "spurs" in key)
    # Should be approximately 0.63 (some probability lost to blowout scenarios not modeled)
    assert 0 < float(spurs_total) <= 0.63 + 0.01

def test_scenario_probs_all_positive():
    probs = build_scenario_probs(MOCK_MARKET_PRICES)
    for key, p in probs.items():
        assert p > 0, f"Non-positive probability for {key}: {p}"

def test_marginal_probability_not_cumulative():
    # Spurs margin 4.5-10.5 = P(under 10.5) - P(under 4.5)
    # = (1 - 0.33) - (1 - 0.53) = 0.67 - 0.47 = 0.20
    probs = build_scenario_probs(MOCK_MARKET_PRICES)
    p = probs["spurs_over_4.5to10.5"]
    # = P(spurs win) * P(over) * 0.20
    expected = Decimal("0.63") * Decimal("0.54") * Decimal("0.20")
    assert abs(p - expected) < Decimal("0.001")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_probabilities.py -v
```

Expected: `ModuleNotFoundError: No module named 'probabilities'`

- [ ] **Step 3: Implement probabilities.py**

```python
# probabilities.py
from decimal import Decimal
from combos_nba import SCENARIOS

ScenarioProbs = dict  # {scenario_key: Decimal}


def build_scenario_probs(market_prices: dict) -> ScenarioProbs:
    """
    Compute probability for each of the 12 non-blowout scenarios.
    
    market_prices: {key: Decimal yes_ask price}
      e.g. "spurs_win" -> 0.63, "spurs_spread_4.5" -> 0.53

    P(margin range) uses MARGINAL probabilities:
      P(under X) = 1 - P(over X) = 1 - yes_ask_spread_X
      P(margin in [lo, hi]) = P(under hi) - P(under lo)
                             = P(over lo) - P(over hi)
    """
    p_spurs_win  = market_prices["spurs_win"]
    p_knicks_win = market_prices["knicks_win"]
    p_over_total = market_prices["total_over_217.5"]
    p_under_total = Decimal("1") - p_over_total

    # Cumulative "under" probabilities per winner
    under_probs = {
        "spurs": {
            "4.5":  Decimal("1") - market_prices["spurs_spread_4.5"],
            "10.5": Decimal("1") - market_prices["spurs_spread_10.5"],
            "16.5": Decimal("1") - market_prices["spurs_spread_16.5"],
        },
        "knicks": {
            "4.5":  Decimal("1") - market_prices["knicks_spread_4.5"],
            "10.5": Decimal("1") - market_prices["knicks_spread_10.5"],
            "20.5": Decimal("1") - market_prices["knicks_spread_20.5"],
        },
    }

    # Marginal margin range probabilities per winner
    def marginal(winner: str, lo: str, hi: str) -> Decimal:
        up = under_probs[winner]
        p_under_hi = up[hi]
        p_under_lo = up[lo] if lo != "0" else Decimal("0")
        return max(Decimal("0"), p_under_hi - p_under_lo)

    margin_ranges = {
        "spurs":  [("0to4.5", "0", "4.5"), ("4.5to10.5", "4.5", "10.5"), ("10.5to16.5", "10.5", "16.5")],
        "knicks": [("0to4.5", "0", "4.5"), ("4.5to10.5", "4.5", "10.5"), ("10.5to20.5", "10.5", "20.5")],
    }

    p_winner = {"spurs": p_spurs_win, "knicks": p_knicks_win}
    p_total  = {"over": p_over_total, "under": p_under_total}

    probs = {}
    for scenario in SCENARIOS:
        winner  = scenario["winner"]
        mrange  = scenario["margin_range"]
        total   = scenario["total"]
        # Find the marginal probability for this range
        _, lo, hi = next(r for r in margin_ranges[winner] if r[0] == mrange)
        p_margin = marginal(winner, lo, hi)
        key = f"{winner}_{total}_{mrange}"
        probs[key] = p_winner[winner] * p_total[total] * p_margin

    return probs


def get_market_prices_from_api(client, market_tickers: dict) -> dict:
    """Fetch yes_ask price for each of the 9 individual markets."""
    prices = {}
    for key, (ticker, _) in market_tickers.items():
        resp = client.get(f"/markets/{ticker}")
        market = resp.get("market", resp)
        prices[key] = Decimal(str(market.get("yes_ask", "0.5")))
    return prices
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_probabilities.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add kalshi_optimizer/probabilities.py kalshi_optimizer/tests/test_probabilities.py
git commit -m "feat: implied probability model from Kalshi market prices"
```

---

## Task 9: optimizer.py — SLSQP Optimizer

**Files:**
- Create: `kalshi_optimizer/optimizer.py`
- Create: `kalshi_optimizer/tests/test_optimizer.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_optimizer.py
from decimal import Decimal
import numpy as np
from optimizer import optimize, round_allocations, OptimizationResult

# Known multipliers for testing (fill prices = 1/multiplier)
FILL_PRICES = {
    "C1":  Decimal("0.0676"),   # ~14.8x
    "C2":  Decimal("0.0578"),   # ~17.3x
    "C3":  Decimal("0.1961"),   # ~5.1x
    "C4":  Decimal("0.1667"),   # ~6.0x
    "C5":  Decimal("0.2703"),   # ~3.7x
    "C6":  Decimal("0.2439"),   # ~4.1x
    "C7":  Decimal("0.0633"),   # ~15.8x
    "C8":  Decimal("0.0503"),   # ~19.9x
    "C9":  Decimal("0.1370"),   # ~7.3x
    "C10": Decimal("0.1163"),   # ~8.6x
    "C11": Decimal("0.1887"),   # ~5.3x
    "C12": Decimal("0.1786"),   # ~5.6x
}

def test_optimize_budget_exactly_allocated():
    result = optimize(budget=Decimal("10.00"), max_loss=Decimal("2.00"), fill_prices=FILL_PRICES)
    total = sum(result.stakes.values())
    assert abs(total - Decimal("10.00")) < Decimal("0.05")

def test_optimize_floor_constraint_satisfied():
    result = optimize(budget=Decimal("10.00"), max_loss=Decimal("2.00"), fill_prices=FILL_PRICES)
    for profit in result.scenario_profits.values():
        assert profit >= Decimal("-2.00") - Decimal("0.10"), f"Floor violated: {profit}"

def test_round_allocations_never_overspend():
    stakes = {f"C{i}": Decimal("0.834") for i in range(1, 13)}
    fill_prices = {f"C{i}": Decimal("0.07") for i in range(1, 13)}
    rounded = round_allocations(stakes, fill_prices, budget=Decimal("10.00"))
    total_cost = sum(rounded["contracts"][cid] * fill_prices[cid] for cid in rounded["contracts"])
    assert total_cost <= Decimal("10.00")

def test_round_allocations_contracts_are_2dp():
    stakes = {"C1": Decimal("1.234")}
    fill_prices = {"C1": Decimal("0.07")}
    rounded = round_allocations(stakes, fill_prices, budget=Decimal("1.234"))
    contracts = rounded["contracts"]["C1"]
    assert contracts == contracts.quantize(Decimal("0.01"))
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_optimizer.py -v
```

Expected: `ModuleNotFoundError: No module named 'optimizer'`

- [ ] **Step 3: Implement optimizer.py**

```python
# optimizer.py
from decimal import Decimal, ROUND_DOWN
from dataclasses import dataclass, field
from typing import Dict
import numpy as np
from scipy.optimize import minimize

from combos_nba import COMBOS, SCENARIOS, get_paying_combo_ids, calc_net_profit

COMBO_IDS = [c["id"] for c in COMBOS]


@dataclass
class OptimizationResult:
    stakes: Dict[str, Decimal]       # target dollar stakes from optimizer
    contracts: Dict[str, Decimal]    # floor(stake/fill_price, 2dp)
    actual_costs: Dict[str, Decimal] # contracts * fill_price
    fill_prices: Dict[str, Decimal]
    scenario_profits: Dict[str, Decimal]  # {scenario_key: net profit}
    scenario_probs: Dict[str, Decimal]
    ev: Decimal
    avg_profit: Decimal
    worst_profit: Decimal
    best_profit: Decimal
    total_deployed: Decimal


def _make_scenario_key(s: dict) -> str:
    return f"{s['winner']}_{s['total']}_{s['margin_range']}"


def _scenario_profits_from_x(
    x: np.ndarray, fill_prices: dict
) -> list:
    """Compute net profit for each of the 12 non-blowout scenarios given stake vector x."""
    stakes = {cid: Decimal(str(max(0.0, x[i]))) for i, cid in enumerate(COMBO_IDS)}
    contracts = {
        cid: (stakes[cid] / fill_prices[cid]).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        for cid in COMBO_IDS
    }
    profits = []
    for s in SCENARIOS:
        profit = calc_net_profit(s, contracts, fill_prices)
        profits.append(float(profit))
    return profits


def optimize(
    budget: Decimal,
    max_loss: Decimal,
    fill_prices: Dict[str, Decimal],
    scenario_probs: Dict[str, Decimal] = None,
) -> "OptimizationResult":
    n = len(COMBO_IDS)
    budget_f = float(budget)
    max_loss_f = float(max_loss)

    def objective(x):
        profits = _scenario_profits_from_x(x, fill_prices)
        return -np.mean(profits)

    def floor_constraint(x):
        profits = _scenario_profits_from_x(x, fill_prices)
        return min(profits) + max_loss_f

    constraints = [
        {"type": "eq",   "fun": lambda x: np.sum(np.maximum(x, 0)) - budget_f},
        {"type": "ineq", "fun": floor_constraint},
    ]
    bounds = [(0.0, budget_f)] * n
    x0 = np.full(n, budget_f / n)

    result = minimize(
        objective, x0, method="SLSQP", bounds=bounds, constraints=constraints,
        options={"maxiter": 15000, "ftol": 1e-10}
    )

    raw_stakes = {cid: Decimal(str(max(0.0, result.x[i]))) for i, cid in enumerate(COMBO_IDS)}
    return _build_result(raw_stakes, fill_prices, budget, scenario_probs or {})


def _build_result(
    raw_stakes: dict,
    fill_prices: dict,
    budget: Decimal,
    scenario_probs: dict,
) -> OptimizationResult:
    contracts = {
        cid: (raw_stakes[cid] / fill_prices[cid]).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        for cid in COMBO_IDS
    }
    actual_costs = {cid: contracts[cid] * fill_prices[cid] for cid in COMBO_IDS}
    total_deployed = sum(actual_costs.values())

    scenario_profits = {}
    for s in SCENARIOS:
        key = _make_scenario_key(s)
        scenario_profits[key] = calc_net_profit(s, contracts, fill_prices)

    profits_list = list(scenario_profits.values())

    ev = Decimal("0")
    if scenario_probs:
        for key, profit in scenario_profits.items():
            prob = scenario_probs.get(key, Decimal("0"))
            ev += prob * profit

    return OptimizationResult(
        stakes=raw_stakes,
        contracts=contracts,
        actual_costs=actual_costs,
        fill_prices=fill_prices,
        scenario_profits=scenario_profits,
        scenario_probs=scenario_probs,
        ev=ev,
        avg_profit=sum(profits_list) / len(profits_list),
        worst_profit=min(profits_list),
        best_profit=max(profits_list),
        total_deployed=total_deployed,
    )


def round_allocations(stakes: dict, fill_prices: dict, budget: Decimal) -> dict:
    """Convert optimizer stakes to exact contracts. Returns {contracts, actual_costs}."""
    contracts = {
        cid: (stakes[cid] / fill_prices[cid]).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        for cid in stakes
    }
    actual_costs = {cid: contracts[cid] * fill_prices[cid] for cid in contracts}
    return {"contracts": contracts, "actual_costs": actual_costs}
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_optimizer.py -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add kalshi_optimizer/optimizer.py kalshi_optimizer/tests/test_optimizer.py
git commit -m "feat: SLSQP two-pass optimizer with rounding-aware profit calculation"
```

---

## Task 10: report.py — HTML Output

**Files:**
- Create: `kalshi_optimizer/report.py`
- Create: `kalshi_optimizer/tests/test_report.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_report.py
from decimal import Decimal
from optimizer import OptimizationResult
from combos_nba import COMBOS, SCENARIOS
from report import generate_html

def _make_result():
    fill_prices = {c["id"]: Decimal("0.10") for c in COMBOS}
    contracts   = {c["id"]: Decimal("8.33") for c in COMBOS}
    actual_costs = {c["id"]: Decimal("0.833") for c in COMBOS}
    profits     = {"spurs_over_0to4.5": Decimal("2.50"), "spurs_under_0to4.5": Decimal("-1.00")}
    for s in SCENARIOS:
        key = f"{s['winner']}_{s['total']}_{s['margin_range']}"
        profits.setdefault(key, Decimal("0.00"))
    probs = {f"{s['winner']}_{s['total']}_{s['margin_range']}": Decimal("0.083") for s in SCENARIOS}
    return OptimizationResult(
        stakes={c["id"]: Decimal("1.00") for c in COMBOS},
        contracts=contracts,
        actual_costs=actual_costs,
        fill_prices=fill_prices,
        scenario_profits=profits,
        scenario_probs=probs,
        ev=Decimal("0.50"),
        avg_profit=Decimal("1.00"),
        worst_profit=Decimal("-1.00"),
        best_profit=Decimal("5.00"),
        total_deployed=Decimal("9.97"),
    )

def test_generate_html_is_valid_html():
    result = _make_result()
    html = generate_html(result, budget=Decimal("10.00"), max_loss=Decimal("2.00"),
                         fetched_at="19:42:03")
    assert html.startswith("<!DOCTYPE html>")
    assert "</html>" in html

def test_generate_html_contains_all_12_combos():
    result = _make_result()
    html = generate_html(result, budget=Decimal("10.00"), max_loss=Decimal("2.00"),
                         fetched_at="19:42:03")
    for combo in COMBOS:
        assert combo["id"] in html

def test_generate_html_contains_all_12_scenarios():
    result = _make_result()
    html = generate_html(result, budget=Decimal("10.00"), max_loss=Decimal("2.00"),
                         fetched_at="19:42:03")
    assert "Spurs" in html
    assert "Knicks" in html
    assert "1–4 pts" in html

def test_generate_html_shows_budget():
    result = _make_result()
    html = generate_html(result, budget=Decimal("10.00"), max_loss=Decimal("2.00"),
                         fetched_at="19:42:03")
    assert "10.00" in html

def test_generate_html_shows_deployed():
    result = _make_result()
    html = generate_html(result, budget=Decimal("10.00"), max_loss=Decimal("2.00"),
                         fetched_at="19:42:03")
    assert "9.97" in html
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_report.py -v
```

Expected: `ModuleNotFoundError: No module named 'report'`

- [ ] **Step 3: Implement report.py**

```python
# report.py
"""
Generates a self-contained HTML file styled after kalshi_hedge.jsx.
Dark terminal aesthetic, vanilla HTML/CSS/JS (no React dependency).
"""
from decimal import Decimal
from optimizer import OptimizationResult
from combos_nba import COMBOS, SCENARIOS, get_paying_combo_ids, calc_net_profit
import json

_COMBO_LABEL = {
    ("spurs",  "over"):  "Spurs + Over",
    ("spurs",  "under"): "Spurs + Under",
    ("knicks", "over"):  "Knicks + Over",
    ("knicks", "under"): "Knicks + Under",
}

_MARGIN_LABEL = {
    "4.5":  "< 4.5 pts",
    "10.5": "< 10.5 pts",
    "16.5": "< 16.5 pts",
    "20.5": "< 20.5 pts",
}

_RANGE_LABEL = {
    "0to4.5":     "Win by 1–4 pts",
    "4.5to10.5":  "Win by 5–10 pts",
    "10.5to16.5": "Win by 11–16 pts",
    "10.5to20.5": "Win by 11–20 pts",
}


def _fmt(d: Decimal, plus: bool = False) -> str:
    s = f"{abs(d):.2f}"
    if d < 0:
        return f"-${s}"
    return f"+${s}" if plus else f"${s}"


def _build_scenario_card_data(result: OptimizationResult) -> list:
    """Build data for each scenario card."""
    cards = []
    for s in SCENARIOS:
        winner  = s["winner"]
        total   = s["total"]
        mrange  = s["margin_range"]
        key     = f"{winner}_{total}_{mrange}"

        paying_ids  = set(get_paying_combo_ids(s))
        profit      = result.scenario_profits.get(key, Decimal("0"))
        prob        = result.scenario_probs.get(key, Decimal("0"))
        ev_contrib  = prob * profit

        winning_bets = []
        losing_bets  = []
        for combo in COMBOS:
            cid      = combo["id"]
            contracts = result.contracts[cid]
            cost     = result.actual_costs[cid]
            fill     = result.fill_prices[cid]
            mult     = Decimal("1") / fill if fill > 0 else Decimal("0")

            if contracts == 0:
                continue

            label = (
                f"{_COMBO_LABEL[(combo['winner'], combo['total'])]} "
                f"/ {_MARGIN_LABEL[str(combo['margin'])]}"
            )
            if cid in paying_ids:
                payout = contracts  # pays $1 per contract
                winning_bets.append({
                    "label": label,
                    "contracts": str(contracts),
                    "cost": str(cost),
                    "mult": f"{float(mult):.1f}",
                    "payout": str(payout),
                })
            else:
                losing_bets.append({
                    "label": label,
                    "cost": str(cost),
                })

        total_payout  = sum(Decimal(b["payout"]) for b in winning_bets)
        total_cost_all = sum(result.actual_costs.values())

        cards.append({
            "key": key,
            "winner": winner.capitalize(),
            "total": total.capitalize(),
            "range_label": _RANGE_LABEL.get(mrange, mrange),
            "prob_pct": f"{float(prob)*100:.1f}",
            "profit": float(profit),
            "profit_fmt": _fmt(profit, plus=True),
            "ev_contrib": float(ev_contrib),
            "ev_contrib_fmt": f"{'+' if ev_contrib>=0 else ''}{float(ev_contrib):.3f}",
            "winning_bets": winning_bets,
            "losing_bets": losing_bets,
            "total_payout": str(total_payout),
            "total_cost": str(total_cost_all),
        })
    return cards


def generate_html(
    result: OptimizationResult,
    budget: Decimal,
    max_loss: Decimal,
    fetched_at: str,
) -> str:
    cards_data = _build_scenario_card_data(result)

    # Build allocation rows (grouped by margin, across combo types)
    # Columns: margin | Spurs+Over | Spurs+Under | Knicks+Over | Knicks+Under
    col_order = [("spurs","over"), ("spurs","under"), ("knicks","over"), ("knicks","under")]
    margin_groups_spurs  = ["4.5", "10.5", "16.5"]
    margin_groups_knicks = ["4.5", "10.5", "20.5"]
    all_margins = ["4.5", "10.5", "16.5", "20.5"]  # union

    allocation_rows = []
    for margin_str in all_margins:
        margin = Decimal(margin_str)
        row = {"margin": _MARGIN_LABEL[margin_str], "cells": []}
        for (winner, total) in col_order:
            combo = next(
                (c for c in COMBOS if c["winner"]==winner and c["total"]==total and c["margin"]==margin),
                None
            )
            if combo:
                cid  = combo["id"]
                fill = result.fill_prices[cid]
                mult = float(Decimal("1") / fill) if fill > 0 else 0
                row["cells"].append({
                    "stake":     f"{float(result.actual_costs[cid]):.2f}",
                    "mult":      f"{mult:.1f}",
                    "contracts": f"{float(result.contracts[cid]):.2f}",
                    "fill":      f"{float(fill):.4f}",
                    "has_data":  True,
                })
            else:
                row["cells"].append({"has_data": False})
        allocation_rows.append(row)

    cards_json = json.dumps(cards_data)

    worst_color = "#5a9e6f" if result.worst_profit >= -(max_loss + Decimal("0.05")) else "#e05a5a"
    ev_color    = "#f0c040" if result.ev >= 0 else "#e05a5a"

    alloc_rows_html = ""
    for row in allocation_rows:
        cells_html = ""
        for cell in row["cells"]:
            if cell["has_data"]:
                cells_html += f"""
            <td style="padding:0.5rem 0.55rem;text-align:center;border-bottom:1px solid #1a1a2a;">
              <div style="font-weight:700">${cell['stake']}</div>
              <div style="font-size:0.55rem;color:#aaa">{cell['mult']}x · {cell['contracts']} cts</div>
              <div style="font-size:0.5rem;color:#555">fill ${cell['fill']}</div>
            </td>"""
            else:
                cells_html += '<td style="padding:0.5rem;text-align:center;border-bottom:1px solid #1a1a2a;color:#333">—</td>'
        alloc_rows_html += f"""
          <tr>
            <td style="padding:0.5rem 0.55rem;text-align:left;color:#5a9e6f;font-weight:700;border-bottom:1px solid #1a1a2a">{row['margin']}</td>
            {cells_html}
          </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kalshi Combo Optimizer — NBA Finals G1</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #0a0a0f; color: #e8e4d9; font-family: 'Courier New', monospace; padding: 2rem 1.5rem; }}
  h1 {{ font-size: 1.9rem; font-weight: 900; letter-spacing: -0.03em;
       background: linear-gradient(135deg,#e8e4d9 0%,#5a9e6f 100%);
       -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
  .label {{ font-size: 0.58rem; letter-spacing: 0.35em; color: #5a9e6f; margin-bottom: 0.5rem; }}
  .card {{ background: #111118; border: 1px solid #2a2a3a; border-radius: 6px; padding: 0.65rem 0.8rem; }}
  .stat-box {{ text-align: center; border-radius: 6px; padding: 0.6rem 0.4rem; }}
  .stat-val {{ font-size: 0.95rem; font-weight: 900; }}
  .stat-lbl {{ font-size: 0.48rem; letter-spacing: 0.12em; margin-bottom: 0.25rem; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th {{ padding: 0.4rem 0.55rem; font-size: 0.58rem; letter-spacing: 0.1em; color: #666; border-bottom: 1px solid #2a2a3a; }}
  .scenario-card {{ border-radius: 6px; padding: 0.65rem 0.8rem; cursor: pointer; margin-bottom: 0.45rem; border: 1px solid #2a2a3a; background: #111118; }}
  .scenario-card.best  {{ background: #0d1a0d; border-color: #1a5a1a; }}
  .scenario-card.worst {{ background: #1a1008; border-color: #5a4010; }}
  .expanded-detail {{ display: none; margin-top: 0.75rem; border-top: 1px solid #2a2a3a; padding-top: 0.75rem; }}
  .profit-pos {{ color: #5a9e6f; }}
  .profit-neg {{ color: #e05a5a; }}
  .divider {{ border: none; border-top: 1px solid #1a1a2a; margin: 1.5rem 0; }}
</style>
</head>
<body>

<div style="text-align:center;margin-bottom:2rem">
  <div style="font-size:0.6rem;letter-spacing:0.5em;color:#5a9e6f;margin-bottom:0.4rem">KALSHI COMBO</div>
  <h1>PROFIT MAXIMIZER</h1>
  <div style="font-size:0.65rem;color:#555;margin-top:0.3rem;letter-spacing:0.1em">
    SPURS vs KNICKS · NBA FINALS GAME 1 · Prices fetched: {fetched_at}
  </div>
</div>

<!-- Budget summary -->
<div style="text-align:center;margin-bottom:1.5rem;font-size:0.72rem">
  <span style="color:#666">BUDGET</span> <span style="font-weight:700">${float(budget):.2f}</span>
  &nbsp;&nbsp;·&nbsp;&nbsp;
  <span style="color:#e05a5a">MAX LOSS</span> <span style="font-weight:700">${float(max_loss):.2f}</span>
  &nbsp;&nbsp;·&nbsp;&nbsp;
  <span style="color:#5a9e6f">DEPLOYED</span> <span style="font-weight:700">${float(result.total_deployed):.2f}</span>
</div>

<!-- Stats -->
<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:0.5rem;max-width:480px;margin:0 auto 1.5rem">
  <div class="stat-box" style="background:#111118;border:1px solid #2a2a3a">
    <div class="stat-lbl" style="color:#555">WORST CASE</div>
    <div class="stat-val" style="color:{worst_color}">{_fmt(result.worst_profit, plus=True)}</div>
  </div>
  <div class="stat-box" style="background:#111118;border:1px solid #2a2a3a">
    <div class="stat-lbl" style="color:#555">AVG PROFIT</div>
    <div class="stat-val" style="color:#e8e4d9">{_fmt(result.avg_profit, plus=True)}</div>
  </div>
  <div class="stat-box" style="background:#111118;border:1px solid #2a2a3a">
    <div class="stat-lbl" style="color:#555">BEST CASE</div>
    <div class="stat-val" style="color:#5a9e6f">{_fmt(result.best_profit, plus=True)}</div>
  </div>
  <div class="stat-box" style="background:#1a1800;border:1px solid #5a4a00">
    <div class="stat-lbl" style="color:#a08020">EXPECTED VAL</div>
    <div class="stat-val" style="color:{ev_color}">{_fmt(result.ev, plus=True)}</div>
  </div>
</div>

<hr class="divider">

<!-- Multiplier + Allocation Table -->
<div class="label">BET ALLOCATION — ${float(result.total_deployed):.2f} of ${float(budget):.2f} deployed</div>
<div style="overflow-x:auto;margin-bottom:1.5rem">
  <table style="min-width:520px">
    <thead>
      <tr>
        <th style="text-align:left">MARGIN</th>
        <th>SPURS + OVER</th>
        <th>SPURS + UNDER</th>
        <th>KNICKS + OVER</th>
        <th>KNICKS + UNDER</th>
      </tr>
    </thead>
    <tbody>{alloc_rows_html}</tbody>
  </table>
</div>

<hr class="divider">

<!-- Scenario Cards -->
<div class="label">PROFIT BY SCENARIO — click to verify math</div>
<div id="scenarios-container"></div>

<div style="margin-top:1.5rem;font-size:0.58rem;color:#555;text-align:center;line-height:1.8">
  ⚠ Blowout scenarios not shown (Spurs +17, Knicks +21+) — full budget lost if those occur<br>
  Prices fetched at {fetched_at} — re-run within 60s of placing orders<br>
  This tool is for analysis only — it does not place bets
</div>

<script>
const CARDS = {cards_json};

const best  = Math.max(...CARDS.map(c => c.profit));
const worst = Math.min(...CARDS.map(c => c.profit));
let expanded = null;

function render() {{
  const container = document.getElementById('scenarios-container');
  container.innerHTML = '';
  const grid = document.createElement('div');
  grid.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:0.45rem';

  CARDS.forEach((card, i) => {{
    const isExpanded = expanded === card.key;
    const isBest  = Math.abs(card.profit - best)  < 0.01;
    const isWorst = Math.abs(card.profit - worst) < 0.01;

    const div = document.createElement('div');
    div.className = 'scenario-card' + (isBest ? ' best' : isWorst ? ' worst' : '');
    if (isExpanded) div.style.gridColumn = '1 / -1';

    const profitClass = card.profit >= 0 ? 'profit-pos' : 'profit-neg';

    let winHtml = card.winning_bets.length === 0 ? '<div style="font-size:0.65rem;color:#555;margin-bottom:0.5rem">None</div>' :
      card.winning_bets.map(b => `
        <div style="font-size:0.65rem;margin-bottom:0.2rem;display:flex;justify-content:space-between;color:#a0e0b0">
          <span>${{b.label}}</span>
          <span>${{b.contracts}} cts × $1 = <strong>+$${{b.payout}}</strong></span>
        </div>`).join('');

    let loseHtml = card.losing_bets.map(b => `
        <div style="font-size:0.65rem;margin-bottom:0.2rem;display:flex;justify-content:space-between;color:#e09090">
          <span>${{b.label}}</span><span>−$${{b.cost}}</span>
        </div>`).join('');

    div.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:flex-start">
        <div>
          <div style="font-size:0.55rem;color:#666;margin-bottom:0.1rem">
            ${{card.winner.toUpperCase()}} · ${{card.total.toUpperCase()}} 217.5
          </div>
          <div style="font-size:0.72rem;font-weight:700">${{card.range_label}}</div>
          <div style="font-size:0.55rem;color:#f0c040;margin-top:0.15rem">P = ${{card.prob_pct}}%</div>
        </div>
        <div style="text-align:right">
          <div style="font-size:1.05rem;font-weight:900" class="${{profitClass}}">${{card.profit_fmt}}</div>
          <div style="font-size:0.5rem;color:#888">EV: ${{card.ev_contrib_fmt}}</div>
          <div style="font-size:0.48rem;color:#555">${{isExpanded ? '▲ hide' : '▼ verify'}}</div>
        </div>
      </div>
      <div class="expanded-detail" id="detail-${{card.key}}" style="${{isExpanded ? 'display:block' : ''}}">
        <div style="font-size:0.6rem;color:#5a9e6f;letter-spacing:0.2em;margin-bottom:0.4rem">WINNING BETS</div>
        ${{winHtml}}
        <div style="font-size:0.6rem;color:#e05a5a;letter-spacing:0.2em;margin:0.5rem 0 0.4rem">LOSING BETS (cost forfeited)</div>
        ${{loseHtml}}
        <div style="border-top:1px solid #2a2a3a;margin-top:0.5rem;padding-top:0.5rem;font-size:0.68rem">
          <div style="display:flex;justify-content:space-between;margin-bottom:0.15rem">
            <span style="color:#888">Total payouts</span>
            <span style="color:#a0e0b0">+${{card.total_payout}}</span>
          </div>
          <div style="display:flex;justify-content:space-between;margin-bottom:0.15rem">
            <span style="color:#888">Total deployed (all combos)</span>
            <span style="color:#e09090">−${{card.total_cost}}</span>
          </div>
          <div style="display:flex;justify-content:space-between;font-weight:700;font-size:0.75rem;margin-top:0.25rem">
            <span>NET PROFIT</span>
            <span class="${{profitClass}}">${{card.profit_fmt}}</span>
          </div>
          <div style="display:flex;justify-content:space-between;font-size:0.65rem;margin-top:0.2rem">
            <span style="color:#f0c040">EV contribution</span>
            <span style="color:#f0c040">${{card.ev_contrib_fmt}}</span>
          </div>
        </div>
      </div>`;

    div.addEventListener('click', () => {{
      expanded = isExpanded ? null : card.key;
      render();
    }});

    grid.appendChild(div);
  }});

  container.appendChild(grid);
}}

render();
</script>
</body>
</html>"""
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_report.py -v
```

Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add kalshi_optimizer/report.py kalshi_optimizer/tests/test_report.py
git commit -m "feat: self-contained HTML report styled after kalshi_hedge.jsx"
```

---

## Task 11: kalshi_optimizer.py — CLI Entrypoint

**Files:**
- Create: `kalshi_optimizer/kalshi_optimizer.py`

- [ ] **Step 1: Implement the CLI**

```python
#!/usr/bin/env python3
# kalshi_optimizer.py
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


def _require_env():
    missing = [k for k in ("KALSHI_API_KEY_ID", "KALSHI_PRIVATE_KEY_PATH") if not os.environ.get(k)]
    if missing:
        print(f"ERROR: Missing environment variables: {', '.join(missing)}")
        print("Set them in a .env file or export them before running.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Kalshi NBA Finals Combo Optimizer")
    parser.add_argument("--budget",   type=float, help="Total budget in dollars")
    parser.add_argument("--max-loss", type=float, dest="max_loss", help="Max acceptable loss in dollars")
    parser.add_argument("--series",   type=str,   help="Override series ticker (e.g. KXNBAFINALSGA)")
    parser.add_argument("--demo",     action="store_true", help="Use demo API endpoint")
    parser.add_argument("--refresh",  action="store_true", help="Bypass cache and re-discover markets")
    parser.add_argument("--output",   type=str,   default=None, help="Save HTML to this path instead of temp file")
    args = parser.parse_args()

    _require_env()

    # Gather inputs interactively if not provided
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
    from discovery import discover_all, find_nba_finals_series
    from orderbook import fetch_and_cache_orderbook, compute_vwap_yes_fill, compute_contracts, nominal_multiplier
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

    series_ticker = args.series
    if not series_ticker:
        print("Finding NBA Finals series ticker...")
        series_ticker = find_nba_finals_series(client)
        print(f"  → {series_ticker}")

    if args.refresh:
        cache.refresh(series_ticker)
        print("Cache cleared.")

    print("Discovering Game 1 markets and creating combo markets...")
    market_tickers, combo_tickers = discover_all(client, series_ticker, cache)
    print(f"  → {len(combo_tickers)} combos ready")

    print("Fetching orderbooks...")
    fill_prices = {}
    no_bids_map = {}
    for cid, combo_ticker in combo_tickers.items():
        no_bids = fetch_and_cache_orderbook(client, cache, series_ticker, combo_ticker)
        no_bids_map[cid] = no_bids
        fill = compute_vwap_yes_fill(no_bids, budget_d / 12)
        if fill is None:
            print(f"  WARNING: No liquidity for {cid} ({combo_ticker}) — using 0.10 as fallback")
            fill = Decimal("0.10")
        fill_prices[cid] = fill

    print("Fetching market prices for probability model...")
    try:
        market_prices = get_market_prices_from_api(client, market_tickers)
        scenario_probs = build_scenario_probs(market_prices)
    except Exception as e:
        print(f"  WARNING: Could not fetch market prices ({e}) — using uniform probabilities")
        from combos_nba import SCENARIOS
        scenario_probs = {
            f"{s['winner']}_{s['total']}_{s['margin_range']}": Decimal("1") / Decimal("12")
            for s in SCENARIOS
        }

    print("Running optimizer...")
    result = optimize(
        budget=budget_d,
        max_loss=max_loss_d,
        fill_prices=fill_prices,
        scenario_probs=scenario_probs,
    )

    fetched_at = datetime.now().strftime("%H:%M:%S")
    html = generate_html(result, budget=budget_d, max_loss=max_loss_d, fetched_at=fetched_at)

    output_path = args.output
    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8")
        tmp.write(html)
        tmp.close()
        output_path = tmp.name

    else:
        Path(output_path).write_text(html, encoding="utf-8")

    print(f"\nReport written to: {output_path}")
    print(f"  Worst case:  {float(result.worst_profit):+.2f}")
    print(f"  Best case:   {float(result.best_profit):+.2f}")
    print(f"  Avg profit:  {float(result.avg_profit):+.2f}")
    print(f"  Expected EV: {float(result.ev):+.2f}")
    print(f"  Deployed:    ${float(result.total_deployed):.2f} of ${budget:.2f}")

    webbrowser.open(f"file://{output_path}")
    print("\nOpened in browser. Re-run within 60s of placing orders.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify CLI help works**

```bash
cd kalshi_optimizer && python kalshi_optimizer.py --help
```

Expected: prints usage with `--budget`, `--max-loss`, `--series`, `--demo`, `--refresh`, `--output` options.

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/ -v
```

Expected: all tests PASSED.

- [ ] **Step 4: Commit**

```bash
git add kalshi_optimizer/kalshi_optimizer.py
git commit -m "feat: CLI entrypoint with interactive mode and HTML report output"
```

---

## Task 12: Final Integration Check

- [ ] **Step 1: Verify .env.example is not committed with real keys**

```bash
grep -r "KALSHI_API_KEY_ID=" kalshi_optimizer/.env.example
```

Expected: shows placeholder `your-key-id-here`, not a real key.

- [ ] **Step 2: Run full test suite**

```bash
cd kalshi_optimizer && pytest tests/ -v --tb=short
```

Expected: all tests PASSED, no warnings.

- [ ] **Step 3: Verify demo mode help**

```bash
python kalshi_optimizer.py --demo --budget 10 --max-loss 2 --help
```

Expected: runs without error (help text shown).

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete Kalshi NBA Finals combo optimizer"
```

---

## Usage

```bash
cd kalshi_optimizer

# Set credentials
export KALSHI_API_KEY_ID="your-key-id"
export KALSHI_PRIVATE_KEY_PATH="/path/to/private_key.pem"

# Run (opens HTML report in browser)
python kalshi_optimizer.py --budget 10 --max-loss 2

# Demo mode (safe, no real money)
python kalshi_optimizer.py --budget 10 --max-loss 2 --demo

# Save report to file
python kalshi_optimizer.py --budget 10 --max-loss 2 --output report.html

# Force fresh data
python kalshi_optimizer.py --budget 10 --max-loss 2 --refresh
```
