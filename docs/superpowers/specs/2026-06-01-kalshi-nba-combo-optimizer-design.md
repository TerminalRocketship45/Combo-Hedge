# Kalshi NBA Finals Combo Optimizer — Design Spec

## Goal

A Python CLI tool that discovers Kalshi market tickers for the NBA Finals Game 1 (Spurs vs Knicks), creates all 12 valid combo markets via the Kalshi API, fetches live orderbook prices, and runs a constrained optimizer that recommends how to allocate a fixed budget across combos to maximize profit subject to a maximum-loss floor — using exact contract-count math to account for Kalshi's rounding behavior.

## Architecture

Three layers:

1. **API layer** (`auth.py`, `client.py`, `discovery.py`) — RSA-PSS signing, rate-limited HTTP, market ticker discovery, combo creation via POST.
2. **Math layer** (`orderbook.py`, `optimizer.py`, `combos_nba.py`) — slippage-adjusted fill prices via VWAP, exact contract-count profit calculation, two-pass SLSQP optimizer.
3. **Presentation layer** (`report.py`, `kalshi_optimizer.py`) — rich terminal tables, CLI entrypoint.

A thin `cache.py` sits between layers 1 and 2, persisting combo tickers (game-day TTL) and orderbook snapshots (60-second TTL) to avoid redundant API calls on re-runs.

## Tech Stack

Python 3.11+, `cryptography` (RSA-PSS), `requests`, `tenacity` (retry/backoff), `scipy` + `numpy` (SLSQP optimizer), `rich` (terminal output), `decimal` (all monetary math).

---

## Combo Definitions

### The 12 Hardcoded Combos

Every combo has exactly 3 legs:

| Leg | Kalshi market type | Side |
|-----|--------------------|------|
| Game lines | "Spurs win Game 1" or "Knicks win Game 1" | YES |
| Spread | "[Team] wins by OVER X.5 pts" | NO (betting under) |
| Total | "Over 217.5 total points" | YES (over) or NO (under) |

| # | Winner | Spread threshold | Total side |
|---|--------|-----------------|------------|
| 1 | Spurs | Under 4.5 | Over 217.5 |
| 2 | Spurs | Under 4.5 | Under 217.5 |
| 3 | Spurs | Under 10.5 | Over 217.5 |
| 4 | Spurs | Under 10.5 | Under 217.5 |
| 5 | Spurs | Under 16.5 | Over 217.5 |
| 6 | Spurs | Under 16.5 | Under 217.5 |
| 7 | Knicks | Under 4.5 | Over 217.5 |
| 8 | Knicks | Under 4.5 | Under 217.5 |
| 9 | Knicks | Under 10.5 | Over 217.5 |
| 10 | Knicks | Under 10.5 | Under 217.5 |
| 11 | Knicks | Under 20.5 | Over 217.5 |
| 12 | Knicks | Under 20.5 | Under 217.5 |

### Why these combos and not others

- You cannot combine "Team A wins" with "Team A wins by OVER X.5" on Kalshi — the API only allows NO-side spread legs in winner combos.
- Spurs spread caps at 16.5, Knicks at 20.5 — any larger margin is a "blowout" scenario the system intentionally does not cover.

---

## Scenario Model

### The 16 Mutually Exclusive Scenarios

| # | Winner | Margin range | Total |
|---|--------|-------------|-------|
| S1 | Spurs | 1–4 pts | Over |
| S2 | Spurs | 1–4 pts | Under |
| S3 | Spurs | 5–10 pts | Over |
| S4 | Spurs | 5–10 pts | Under |
| S5 | Spurs | 11–16 pts | Over |
| S6 | Spurs | 11–16 pts | Under |
| S7 | Spurs | 17+ pts (blowout) | Over |
| S8 | Spurs | 17+ pts (blowout) | Under |
| S9 | Knicks | 1–4 pts | Over |
| S10 | Knicks | 1–4 pts | Under |
| S11 | Knicks | 5–10 pts | Over |
| S12 | Knicks | 5–10 pts | Under |
| S13 | Knicks | 11–20 pts | Over |
| S14 | Knicks | 11–20 pts | Under |
| S15 | Knicks | 21+ pts (blowout) | Over |
| S16 | Knicks | 21+ pts (blowout) | Under |

### Which combos pay out in each scenario (margin stacking)

"Under X.5" pays out for any actual margin below X.5. A combo with threshold 10.5 wins in both the 1–4 AND 5–10 ranges. Blowout scenarios (S7, S8, S15, S16) pay out nothing — the user loses the full budget.

| Scenario | Paying combos |
|----------|--------------|
| S1 (Spurs, 1–4, Over) | C1, C3, C5 |
| S2 (Spurs, 1–4, Under) | C2, C4, C6 |
| S3 (Spurs, 5–10, Over) | C3, C5 |
| S4 (Spurs, 5–10, Under) | C4, C6 |
| S5 (Spurs, 11–16, Over) | C5 |
| S6 (Spurs, 11–16, Under) | C6 |
| S7 (Spurs, 17+, Over) | — |
| S8 (Spurs, 17+, Under) | — |
| S9 (Knicks, 1–4, Over) | C7, C9, C11 |
| S10 (Knicks, 1–4, Under) | C8, C10, C12 |
| S11 (Knicks, 5–10, Over) | C9, C11 |
| S12 (Knicks, 5–10, Under) | C10, C12 |
| S13 (Knicks, 11–20, Over) | C11 |
| S14 (Knicks, 11–20, Under) | C12 |
| S15 (Knicks, 21+, Over) | — |
| S16 (Knicks, 21+, Under) | — |

---

## Profit Calculation (Rounding-Aware)

Kalshi charges by contract count × fill price, and pays $1 per contract on resolution. The nominal multiplier is not used directly in P&L math.

```
For each combo i with VWAP fill price p_i and target stake s_i:

  contracts_i = floor(s_i / p_i, 2dp)     # Kalshi count_fp
  actual_cost_i = contracts_i × p_i        # what Kalshi charges
  payout_i = contracts_i × $1.00           # what Kalshi pays on win

Net profit in scenario j =
    sum(contracts_i × $1.00  for all i where combo i wins in scenario j)
  − sum(actual_cost_i         for all i)
```

Total actual spend = sum(actual_cost_i) ≤ budget (due to floor rounding). Undeployed cents are shown in the report.

---

## API Flow

### Discovery (run once per game day, cached)

1. `GET /series` → find NBA Finals series ticker (e.g. `KXNBAFINALSGA`)
2. `GET /events?series_ticker=X&with_nested_markets=true` → get all individual markets for Game 1
3. Parse markets into 3 buckets by category: game_lines, spread, total
4. Extract the 9 needed market tickers:
   - Spurs win, Knicks win (game_lines)
   - Spurs by over 4.5, 10.5, 16.5 (spread, NO side)
   - Knicks by over 4.5, 10.5, 20.5 (spread, NO side)
   - Over 217.5 (total — YES = over, NO = under)
5. `GET /multivariate_event_collections?series_ticker=X` → get collection ticker
6. For each of the 12 combos: `POST /multivariate_event_collections/{collection_ticker}` with 3 legs → get combo market ticker

### Orderbook (60-second TTL cache)

For each combo market ticker: `GET /markets/{ticker}/orderbook`

Since we are buying YES on these combos (all legs hit = we win), YES buyers are matched against NO bids:
- Walk NO bid side from highest price to lowest
- YES fill price at each level = (1 - no_bid_price)
- Compute VWAP YES fill = sum((1-no_bid_k) × contracts_k) / total_contracts for our order size

### Rate limiting

- 20 reads / 10 writes per second (Basic tier)
- `tenacity` retry with exponential backoff on 429 responses
- Parallel orderbook fetches with a semaphore (max 10 concurrent)

---

## Optimizer

### Two-pass SLSQP

Decision variables: `x[i]` = target stake on combo i (dollars, float for scipy)

**Pass 1 — maximize simple average profit:**
```
minimize  -mean(scenario_profit(x) for all 16 scenarios)
subject to:
  sum(x) == budget
  min(scenario_profit(x)) >= -max_loss
  x[i] >= 0.01 for all i
```

**Pass 2 — maximize probability-weighted EV:**
Same constraints, but objective = -sum(p_j × scenario_profit_j(x)) where p_j comes from implied Kalshi market prices.

### Scenario probability from market prices

```
P(scenario j) = P(winner) × P(total_side) × P(margin_range)

P(margin in range [lo, hi]) = P(over lo.5) − P(over hi.5)
  where P(over X.5) = YES ask price of "[Team] wins by over X.5" market

Blowout margin P = P(over last_threshold)
```

### Post-optimization rounding

After each optimizer pass:
1. Convert float stakes → Decimal
2. Compute `contracts_i = floor(stake_i / fill_price_i, 2dp)`
3. Compute `actual_cost_i = contracts_i × fill_price_i`
4. Recompute all 16 scenario profits with actual contract counts
5. Verify `min(scenario_profit) >= -max_loss` still holds (warn if rounding breaks the floor)

---

## Cache

File: `~/.kalshi_optimizer/{series_ticker}/{YYYY-MM-DD}.json`

```json
{
  "combo_tickers": {
    "C1": "KXNBA-...",
    ...
  },
  "orderbooks": {
    "KXNBA-...": {
      "fetched_at": 1748812345.0,
      "no_bids": [["0.9300", "150.00"], ...]
    }
  },
  "market_tickers": {
    "spurs_win": "KXNBA-...",
    ...
  }
}
```

- `combo_tickers` and `market_tickers`: valid for the calendar day (re-POST at midnight)
- `orderbooks`: stale after 60 seconds; re-fetched transparently
- `--refresh` flag: deletes today's cache file and re-runs full discovery

---

## CLI

```
python kalshi_optimizer.py [OPTIONS]

Options:
  --budget FLOAT      Total dollars to allocate (required)
  --max-loss FLOAT    Maximum acceptable loss in any scenario (required)
  --demo              Use demo API (https://demo-api.kalshi.co/trade-api/v2)
  --refresh           Bypass cache and re-discover all markets
  --series TEXT       Override series ticker (default: auto-detect NBA Finals)
```

Interactive mode (no args): prompts for budget and max-loss.

---

## Output

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 KALSHI COMBO OPTIMIZER — NBA Finals Game 1
 Spurs vs Knicks  |  Prices fetched: 19:42:03
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 BUDGET: $10.00   MAX LOSS: $2.00   DEPLOYED: $9.97

PASS 1 — MAX AVERAGE PROFIT          PASS 2 — MAX EXPECTED VALUE
┌──────────────────────┬────────┬───────┐  ┌──────────────────────┬────────┬───────┐
│ Combo                │ Stake  │ Ctrs  │  │ Combo                │ Stake  │ Ctrs  │
├──────────────────────┼────────┼───────┤  ├──────────────────────┼────────┼───────┤
│ Spurs +<4.5 Over     │ $1.23  │ 17.57 │  │ Spurs +<4.5 Over     │ $1.05  │ 15.00 │
│ ...                  │ ...    │ ...   │  │ ...                  │ ...    │ ...   │
└──────────────────────┴────────┴───────┘  └──────────────────────┴────────┴───────┘

SCENARIO OUTCOMES (shown for whichever pass the user selects)
┌───────────────────────────────┬───────┬──────────┬─────────────┐
│ Scenario                      │ Prob  │ Profit   │ EV Contrib  │
├───────────────────────────────┼───────┼──────────┼─────────────┤
│ Spurs win, 1-4 pts, Over      │ 14.1% │ +$8.23   │ +$1.161     │
│ Spurs win, 17+ pts (blowout)  │  3.2% │ -$9.97 ⚠ │ -$0.319     │
│ ...                           │  ...  │ ...      │ ...         │
└───────────────────────────────┴───────┴──────────┴─────────────┘

SUMMARY — PASS 1        SUMMARY — PASS 2
  Worst case:  -$1.83     Worst case:  -$1.91
  Best case:   +$8.23     Best case:   +$7.44
  Avg profit:  +$1.47     EV:          +$0.94
  Floor ok:    ✓          Floor ok:    ✓

[⚠ Blowout scenarios not covered — full budget lost if margin exceeds threshold]
[Prices fetched 8s ago — re-run within 60s of placing orders]
```

---

## Security

- Credentials read from environment variables only (`KALSHI_API_KEY_ID`, `KALSHI_PRIVATE_KEY_PATH`)
- `.env.example` committed; real `.env` in `.gitignore`
- Private key loaded once at startup, never logged or printed
- Cache file contains no credentials
