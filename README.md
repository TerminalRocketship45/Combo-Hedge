# Combo-Hedge

**Live site:** https://terminalrocketship45.github.io/Combo-Hedge/

---

## What it does

A browser-based optimizer for [Kalshi](https://kalshi.com) combo bets. You paste in the multipliers from the Kalshi app, set a budget and a minimum guaranteed profit floor, and the optimizer tells you exactly how many dollars to put on each combo — so that regardless of which outcome hits (within the hedged margin range), you meet your floor.

---

## Directory

```
index.html          — the entire app (single self-contained file, no build step)
input_data/         — example CSV files with Kalshi multipliers
```

`index.html` has zero external dependencies except two CDN-loaded libraries:
- [D3.js v7](https://d3js.org) — sensitivity analysis charts
- [JetBrains Mono](https://fonts.google.com/specimen/JetBrains+Mono) — font

---

## How the optimizer works

### Problem setup

You have a fixed budget and a grid of bets. Each bet is a *(margin bracket) × (team + total)* combination — e.g. "Under 10.5 pts / Spurs + Over 217.5." Each bet has a multiplier (e.g. 5.1×) and a Kalshi price (e.g. $0.20/contract).

The game outcome lands in exactly one *scenario* — defined by winner, winning margin range, and whether the total went over or under. Every bet either pays out or loses depending on which scenario hits.

The optimizer finds the dollar allocation across all bets such that:

1. **All money is deployed** — allocations sum to budget.
2. **Floor guarantee is met** — net profit in the worst-case hedged scenario ≥ your minimum.
3. **Average profit is maximized** — subject to (1) and (2).

### Kalshi rounding

Kalshi prices are in $0.01 steps. Contracts are **integer-floored**:

```
contracts = floor(stake / price)
actual_charge = contracts × price          # ≤ stake, difference returned unspent
payout_if_wins = contracts × $1.00
```

Example: $1.81 at $0.33/contract → 5 contracts → $1.65 charged, $5.00 payout, $0.16 returned.

The optimizer accounts for this throughout — scenario profits, floor checks, and the allocation table all use actual post-rounding values.

### Algorithm: projected gradient ascent with floor penalty

The optimizer runs a fixed number of iterations (default 100,000) of the following loop:

**1. Normalize**
Scale all allocations so they sum exactly to the budget:
```
x[i] = x[i] / sum(x) × budget
```

**2. Compute scenario profits**
For each hedgeable scenario, calculate net profit given current allocations:
```
profit[s] = sum(payout[i] for winning bets i in scenario s)
           − sum(actual_charge[i] for ALL bets i)
```

**3. Compute gradient**
For each bet `i`, estimate how increasing its allocation improves the average:
```
grad[i] = mean over all hedgeable scenarios s of:
    (multiplier[i] − 1)   if bet i wins in scenario s
    −1                     if bet i loses in scenario s
```
Bets that win in many scenarios with high multipliers get a positive gradient. Bets that lose in most scenarios get a negative gradient and drift toward $0.

**4. Floor penalty**
If any scenario is below the floor target, identify the worst-performing scenario(s) and apply a large penalty (500×) to the gradient for all bets involved — sharply increasing allocation to bets that win in those scenarios:
```
if min(profit) < floor:
    grad[i] += 500 × (same win/lose formula, for worst scenarios only)
```

**5. Step and clamp**
```
x[i] = max(0, x[i] + lr × grad[i])
```
Learning rate: `0.00003` for the first half of iterations, `0.000005` for the second half (coarse exploration then fine-tuning).

### Why some bets go to zero

The gradient for a bet that loses in 10 out of 12 scenarios is strongly negative regardless of its multiplier. The algorithm drives those allocations to near-zero. This is why narrow-coverage bets (e.g. "Under 4.5" — only pays when the team wins by 1–4 points) get small or zero allocation unless their multiplier is high enough to overcome the per-scenario penalty.

### Convergence and iterations

The algorithm is a heuristic — it does not guarantee a global optimum. More iterations produce tighter convergence:

| Iterations | ~Time | Notes |
|---|---|---|
| 10,000 | 0.1 s | Rough estimate |
| 100,000 | 1 s | Default, good for 3–4 rows |
| 500,000 | 5 s | Recommended when adding many rows |
| 1,000,000 | 10 s | Near-converged for most inputs |

Adding rows with low multipliers that the optimizer cannot profitably use increases variable count and slows convergence without improving the solution. Keep your CSV to rows with multipliers worth hedging.

### Sensitivity analysis

The charts at the bottom sweep the *min guaranteed profit* parameter across −budget to +budget. Each point is computed by running the full optimizer at that floor value. Click anywhere on a chart to compute that point.
