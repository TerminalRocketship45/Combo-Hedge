"""Generate a self-contained dark-terminal HTML report and CSV for the Kalshi combo optimizer."""

from __future__ import annotations

import csv
import io
import json
from decimal import Decimal
from typing import TYPE_CHECKING

from combos_nba import COMBOS, SCENARIOS, get_paying_combo_ids

if TYPE_CHECKING:
    from optimizer import OptimizationResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt(d: Decimal, decimals: int = 2) -> str:
    return f"{float(d):.{decimals}f}"


def _signed(d: Decimal, decimals: int = 2) -> str:
    val = float(d)
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.{decimals}f}"


def _scenario_key(s: dict) -> str:
    return f"{s['winner']}_{s['total']}_{s['margin_range']}"


# Human-readable margin range labels (using en-dash U+2013)
_MARGIN_LABELS: dict[str, str] = {
    "0to4.5":     "1–4 pts",
    "4.5to10.5":  "5–10 pts",
    "10.5to16.5": "11–16 pts",
    "10.5to20.5": "11–20 pts",
    "16.5to999":  "17+ pts",
    "20.5to999":  "21+ pts",
}


def _margin_label(margin_range: str) -> str:
    return _MARGIN_LABELS.get(margin_range, margin_range)


# ---------------------------------------------------------------------------
# Allocation table
# ---------------------------------------------------------------------------

# Rows keyed by the margin threshold stored on each combo (Decimal)
_MARGIN_ROW_ORDER = [Decimal("4.5"), Decimal("10.5"), Decimal("16.5"), Decimal("20.5")]
_MARGIN_ROW_LABELS = {
    Decimal("4.5"):  "< 4.5 pts",
    Decimal("10.5"): "< 10.5 pts",
    Decimal("16.5"): "< 16.5 pts",
    Decimal("20.5"): "< 20.5 pts",
}

# Four column groups: (winner, total)
_COLUMNS = [
    ("spurs",  "over",  "SPURS + OVER"),
    ("spurs",  "under", "SPURS + UNDER"),
    ("knicks", "over",  "KNICKS + OVER"),
    ("knicks", "under", "KNICKS + UNDER"),
]


def _build_combo_index() -> dict[tuple, str]:
    """Map (winner, total, margin_decimal) -> combo_id."""
    idx: dict[tuple, str] = {}
    for c in COMBOS:
        idx[(c["winner"], c["total"], c["margin"])] = c["id"]
    return idx


def _render_allocation_table(result: "OptimizationResult", is_estimated: bool = True) -> str:
    combo_idx = _build_combo_index()
    est_badge = ' <span class="est-badge">EST</span>' if is_estimated else ' <span class="live-badge">LIVE</span>'

    header_cells = "".join(
        f'<th class="th-col">{label}</th>' for _, _, label in _COLUMNS
    )
    header_row = f'<tr><th class="th-margin">MARGIN</th>{header_cells}</tr>'

    rows_html = ""
    for margin in _MARGIN_ROW_ORDER:
        row_label = _MARGIN_ROW_LABELS[margin]
        cells = ""
        for winner, total, _ in _COLUMNS:
            cid = combo_idx.get((winner, total, margin))
            if cid is None:
                cells += '<td class="alloc-cell alloc-na">—</td>'
                continue
            fp          = result.fill_prices[cid]
            contracts   = result.contracts[cid]
            actual_cost = result.actual_costs[cid]
            multiplier  = Decimal("1") / fp
            cells += (
                f'<td class="alloc-cell">'
                f'<div class="alloc-mult">{_fmt(multiplier, 2)}x{est_badge}</div>'
                f'<div class="alloc-stake">stake ${_fmt(actual_cost)}</div>'
                f'<div class="alloc-detail">{_fmt(contracts)} contracts</div>'
                f'<div class="alloc-detail combo-id">{cid}</div>'
                f'</td>'
            )
        rows_html += f'<tr><td class="td-margin">{row_label}</td>{cells}</tr>'

    return f'<table class="alloc-table">{header_row}{rows_html}</table>'


# ---------------------------------------------------------------------------
# CSV generator
# ---------------------------------------------------------------------------

def generate_csv(result: "OptimizationResult", is_estimated: bool = True) -> str:
    """Return a CSV string with one row per combo."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([
        "combo_id", "description", "winner", "margin_threshold", "total",
        "multiplier", "price_source", "fill_price",
        "recommended_stake", "contracts", "payout_if_win",
    ])
    for combo in COMBOS:
        cid  = combo["id"]
        fp   = result.fill_prices[cid]
        mult = Decimal("1") / fp
        cost = result.actual_costs[cid]
        ctrs = result.contracts[cid]
        desc = f"{combo['winner'].capitalize()} win + under {combo['margin']} pts + {combo['total']} 217.5"
        writer.writerow([
            cid,
            desc,
            combo["winner"].capitalize(),
            f"under {combo['margin']}",
            combo["total"],
            f"{float(mult):.2f}x",
            "ESTIMATED" if is_estimated else "LIVE",
            f"{float(fp):.4f}",
            f"{float(cost):.2f}",
            f"{float(ctrs):.2f}",
            f"{float(ctrs):.2f}",  # payout = contracts * $1
        ])
    return out.getvalue()


# ---------------------------------------------------------------------------
# Scenario cards JSON data
# ---------------------------------------------------------------------------

def _build_scenario_data(result: "OptimizationResult") -> list[dict]:
    """Build a list of scenario dicts for embedding in JS."""
    data = []
    for s in SCENARIOS:
        key = _scenario_key(s)
        winner = s["winner"].capitalize()
        total_dir = s["total"].capitalize()
        margin_range = s["margin_range"]
        label = _margin_label(margin_range)
        prob = result.scenario_probs.get(key, Decimal("0"))
        profit = result.scenario_profits.get(key, Decimal("0"))

        paying_ids = set(get_paying_combo_ids(s))
        losing_ids = [c["id"] for c in COMBOS if c["id"] not in paying_ids]

        winning_bets = []
        for cid in sorted(paying_ids):
            contracts = result.contracts.get(cid, Decimal("0"))
            payout = contracts  # $1 per contract at settlement
            winning_bets.append({
                "combo": cid,
                "contracts": float(contracts),
                "payout": float(payout),
            })

        losing_bets = []
        for cid in losing_ids:
            contracts = result.contracts.get(cid, Decimal("0"))
            fp = result.fill_prices.get(cid, Decimal("0"))
            cost = contracts * fp
            losing_bets.append({
                "combo": cid,
                "cost": float(cost),
            })

        total_deployed = float(result.total_deployed)

        data.append({
            "key": key,
            "winner": winner,
            "total": total_dir,
            "margin_label": label,
            "prob_pct": float(prob) * 100,
            "profit": float(profit),
            "winning_bets": winning_bets,
            "losing_bets": losing_bets,
            "total_deployed": total_deployed,
        })

    return data


# ---------------------------------------------------------------------------
# Main HTML generator
# ---------------------------------------------------------------------------

def generate_html(
    result: "OptimizationResult",
    budget: Decimal,
    max_loss: Decimal,
    fetched_at: str,
    is_estimated: bool = True,
) -> str:
    """Return a complete, self-contained HTML string for the optimizer report."""

    scenario_data_json = json.dumps(_build_scenario_data(result), indent=2)
    allocation_table_html = _render_allocation_table(result, is_estimated=is_estimated)
    price_banner = (
        '<div class="est-banner">ESTIMATED PRICES &mdash; multipliers are calculated from individual market '
        'leg probabilities because no market makers have posted quotes on these combos yet. '
        'Re-run closer to tipoff for live quotes.</div>'
        if is_estimated else
        '<div class="live-banner">LIVE PRICES &mdash; multipliers sourced from live Kalshi orderbook.</div>'
    )

    worst_class = "neg" if result.worst_profit < 0 else "pos"
    avg_class = "pos" if result.avg_profit >= 0 else "neg"
    best_class = "pos"
    ev_class = "pos" if result.ev >= 0 else "neg"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Kalshi Combo Optimizer — NBA Finals</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    :root {{
      --bg:       #0a0a0f;
      --surface:  #12121a;
      --border:   #2a2a3a;
      --text:     #e8e4d9;
      --muted:    #6b6b7a;
      --green:    #5a9e6f;
      --red:      #e05a5a;
      --gold:     #f0c040;
      --blue:     #5a8ae0;
      --font:     'Courier New', monospace;
    }}

    body {{
      background: var(--bg);
      color: var(--text);
      font-family: var(--font);
      font-size: 13px;
      line-height: 1.5;
      padding: 24px;
      max-width: 1200px;
      margin: 0 auto;
    }}

    /* ---- Header ---- */
    .header {{
      border-bottom: 1px solid var(--border);
      padding-bottom: 16px;
      margin-bottom: 24px;
    }}
    .header-title {{
      font-size: 18px;
      font-weight: bold;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--gold);
    }}
    .header-sub {{
      font-size: 13px;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: var(--muted);
      margin-top: 4px;
    }}
    .header-meta {{
      margin-top: 8px;
      font-size: 11px;
      color: var(--muted);
      letter-spacing: 0.06em;
    }}

    /* ---- Stats row ---- */
    .stats-row {{
      display: flex;
      gap: 16px;
      flex-wrap: wrap;
      margin-bottom: 28px;
    }}
    .stat-card {{
      flex: 1;
      min-width: 140px;
      background: var(--surface);
      border: 1px solid var(--border);
      padding: 14px 16px;
    }}
    .stat-label {{
      font-size: 10px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 6px;
    }}
    .stat-value {{
      font-size: 22px;
      font-weight: bold;
    }}
    .pos {{ color: var(--green); }}
    .neg {{ color: var(--red); }}
    .gold {{ color: var(--gold); }}
    .muted {{ color: var(--muted); }}

    /* ---- Section heading ---- */
    .section-title {{
      font-size: 11px;
      letter-spacing: 0.16em;
      text-transform: uppercase;
      color: var(--muted);
      border-bottom: 1px solid var(--border);
      padding-bottom: 6px;
      margin-bottom: 16px;
    }}

    /* ---- Budget info bar ---- */
    .budget-bar {{
      display: flex;
      gap: 24px;
      flex-wrap: wrap;
      margin-bottom: 20px;
      font-size: 12px;
    }}
    .budget-item {{ color: var(--muted); }}
    .budget-item span {{ color: var(--text); }}

    /* ---- Allocation table ---- */
    .alloc-table {{
      width: 100%;
      border-collapse: collapse;
      margin-bottom: 32px;
      font-size: 12px;
    }}
    .alloc-table th, .alloc-table td {{
      border: 1px solid var(--border);
      padding: 8px 10px;
      vertical-align: top;
    }}
    .th-margin, .th-col {{
      background: var(--surface);
      font-size: 10px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted);
      font-weight: normal;
    }}
    .td-margin {{
      background: var(--surface);
      font-size: 11px;
      letter-spacing: 0.10em;
      color: var(--muted);
      white-space: nowrap;
    }}
    .alloc-cell {{
      background: var(--bg);
    }}
    .alloc-na {{
      background: var(--surface);
      color: var(--muted);
      text-align: center;
    }}
    .combo-id {{
      font-size: 10px;
      letter-spacing: 0.12em;
      color: var(--gold);
    }}
    .alloc-mult {{
      font-size: 20px;
      font-weight: bold;
      color: var(--green);
      letter-spacing: -0.02em;
    }}
    .alloc-stake {{
      font-size: 13px;
      font-weight: bold;
      color: var(--text);
      margin-top: 3px;
    }}
    .alloc-detail {{
      font-size: 10px;
      color: var(--muted);
      margin-top: 1px;
    }}
    .est-badge {{
      font-size: 8px;
      background: #3a2a00;
      color: var(--gold);
      padding: 1px 4px;
      letter-spacing: 0.12em;
      vertical-align: middle;
    }}
    .live-badge {{
      font-size: 8px;
      background: #0a2a0a;
      color: var(--green);
      padding: 1px 4px;
      letter-spacing: 0.12em;
      vertical-align: middle;
    }}
    .est-banner {{
      background: #1a1500;
      border: 1px solid #5a4a00;
      color: var(--gold);
      font-size: 11px;
      padding: 10px 14px;
      margin-bottom: 20px;
      letter-spacing: 0.04em;
      line-height: 1.6;
    }}
    .live-banner {{
      background: #0a1a0a;
      border: 1px solid #1a5a1a;
      color: var(--green);
      font-size: 11px;
      padding: 10px 14px;
      margin-bottom: 20px;
      letter-spacing: 0.04em;
    }}

    /* ---- Scenario cards ---- */
    .scenarios-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 12px;
      margin-bottom: 32px;
    }}
    .scenario-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      padding: 14px;
      cursor: pointer;
      transition: border-color 0.15s;
    }}
    .scenario-card:hover {{
      border-color: var(--gold);
    }}
    .scenario-card.expanded {{
      border-color: var(--gold);
    }}
    .sc-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
    }}
    .sc-winner {{
      font-size: 14px;
      font-weight: bold;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }}
    .sc-winner.spurs  {{ color: var(--blue); }}
    .sc-winner.knicks {{ color: var(--green); }}
    .sc-total {{
      font-size: 10px;
      letter-spacing: 0.12em;
      color: var(--muted);
      margin-top: 2px;
    }}
    .sc-profit {{
      font-size: 18px;
      font-weight: bold;
      text-align: right;
    }}
    .sc-meta {{
      display: flex;
      justify-content: space-between;
      margin-top: 8px;
      font-size: 11px;
      color: var(--muted);
    }}
    .sc-margin-label {{
      letter-spacing: 0.08em;
    }}
    .sc-prob {{
      color: var(--muted);
    }}
    .sc-expand-hint {{
      text-align: right;
      font-size: 10px;
      color: var(--border);
      margin-top: 8px;
      letter-spacing: 0.10em;
    }}

    /* ---- Expanded detail ---- */
    .sc-detail {{
      display: none;
      margin-top: 12px;
      border-top: 1px solid var(--border);
      padding-top: 10px;
    }}
    .scenario-card.expanded .sc-detail {{ display: block; }}
    .detail-section-label {{
      font-size: 10px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--muted);
      margin-bottom: 4px;
      margin-top: 8px;
    }}
    .detail-section-label:first-child {{ margin-top: 0; }}
    .detail-row {{
      display: flex;
      justify-content: space-between;
      font-size: 11px;
      padding: 2px 0;
    }}
    .detail-row .dr-label {{ color: var(--muted); }}
    .detail-row .dr-val   {{ color: var(--text); }}
    .detail-row .dr-val.pos {{ color: var(--green); }}
    .detail-row .dr-val.neg {{ color: var(--red); }}
    .net-profit-line {{
      display: flex;
      justify-content: space-between;
      font-size: 13px;
      font-weight: bold;
      border-top: 1px solid var(--border);
      margin-top: 8px;
      padding-top: 6px;
    }}
    .net-profit-line .np-label {{ color: var(--muted); letter-spacing: 0.08em; }}

    /* ---- Footer ---- */
    .footer {{
      border-top: 1px solid var(--border);
      padding-top: 16px;
      margin-top: 8px;
    }}
    .warning-box {{
      background: #1a0f0f;
      border: 1px solid #5a2020;
      padding: 12px 16px;
      font-size: 11px;
      color: #c08080;
      letter-spacing: 0.04em;
      line-height: 1.6;
    }}
    .warning-box strong {{
      color: var(--red);
      text-transform: uppercase;
      letter-spacing: 0.12em;
    }}
    .footer-note {{
      margin-top: 10px;
      font-size: 10px;
      color: var(--muted);
      letter-spacing: 0.06em;
    }}
  </style>
</head>
<body>

  <!-- ============================================================ HEADER -->
  <header class="header">
    <div class="header-title">KALSHI COMBO OPTIMIZER &mdash; NBA Finals Game 1</div>
    <div class="header-sub">SPURS vs KNICKS</div>
    <div class="header-meta">
      FETCHED AT {fetched_at} &nbsp;&bull;&nbsp;
      BUDGET ${ _fmt(budget) } &nbsp;&bull;&nbsp;
      MAX LOSS ${ _fmt(max_loss) }
    </div>
  </header>

  <!-- ============================================================ STATS -->
  <div class="stats-row">
    <div class="stat-card">
      <div class="stat-label">WORST CASE</div>
      <div class="stat-value {worst_class}">{ _signed(result.worst_profit) }</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">AVG PROFIT</div>
      <div class="stat-value {avg_class}">{ _signed(result.avg_profit) }</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">BEST CASE</div>
      <div class="stat-value {best_class}">{ _signed(result.best_profit) }</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">EXPECTED VALUE</div>
      <div class="stat-value {ev_class}">{ _signed(result.ev) }</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">DEPLOYED</div>
      <div class="stat-value gold">${ _fmt(result.total_deployed) }</div>
    </div>
  </div>

  <!-- ============================================================ ALLOCATION -->
  <div class="section-title">ALLOCATION TABLE &mdash; BET SIZES &amp; MULTIPLIERS</div>
  { price_banner }

  <div class="budget-bar">
    <div class="budget-item">BUDGET: <span>${ _fmt(budget) }</span></div>
    <div class="budget-item">DEPLOYED: <span>${ _fmt(result.total_deployed) }</span></div>
    <div class="budget-item">UNUSED: <span>${ _fmt(budget - result.total_deployed) }</span></div>
    <div class="budget-item">MAX LOSS: <span>${ _fmt(max_loss) }</span></div>
  </div>

  { allocation_table_html }

  <!-- ============================================================ SCENARIOS -->
  <div class="section-title">SCENARIO ANALYSIS</div>
  <div class="scenarios-grid" id="scenarios-grid"></div>

  <!-- ============================================================ FOOTER -->
  <footer class="footer">
    <div class="warning-box">
      <strong>Warning &mdash; Blowout Scenarios Not Covered:</strong>
      This portfolio covers the 12 combination scenarios up to the margin thresholds
      above. Blowout outcomes (margins beyond the highest threshold in each quadrant)
      are <em>not</em> individually hedged. In a blowout scenario the payout from the
      widest-margin combo in the winning direction partially offsets total deployed
      capital, but may not recover the full budget. Review worst-case figures carefully
      before placing orders.
    </div>
    <div class="footer-note">
      All figures in USD &bull; Kalshi binary contracts settle at $1.00 per contract &bull;
      Fill prices are VWAP estimates from live orderbook data
    </div>
  </footer>

  <!-- ============================================================ JS -->
  <script>
    var SCENARIO_DATA = { scenario_data_json };

    var MARGIN_LABELS = {{
      "0to4.5":     "1–4 pts",
      "4.5to10.5":  "5–10 pts",
      "10.5to16.5": "11–16 pts",
      "10.5to20.5": "11–20 pts",
      "16.5to999":  "17+ pts",
      "20.5to999":  "21+ pts"
    }};

    function fmt2(n) {{
      return (n >= 0 ? "+" : "") + n.toFixed(2);
    }}

    function renderScenarios() {{
      var grid = document.getElementById("scenarios-grid");
      SCENARIO_DATA.forEach(function(s) {{
        var card = document.createElement("div");
        card.className = "scenario-card";
        card.dataset.key = s.key;

        var profitClass = s.profit >= 0 ? "pos" : "neg";
        var winnerClass = s.winner.toLowerCase();

        // Winning bets detail rows
        var winRows = "";
        s.winning_bets.forEach(function(b) {{
          winRows += '<div class="detail-row">' +
            '<span class="dr-label">' + b.combo + ' &times; ' + b.contracts.toFixed(2) + ' cts</span>' +
            '<span class="dr-val pos">+$' + b.payout.toFixed(2) + '</span>' +
            '</div>';
        }});
        if (!winRows) winRows = '<div class="detail-row"><span class="dr-label muted">none</span></div>';

        // Losing bets detail rows
        var loseRows = "";
        s.losing_bets.forEach(function(b) {{
          loseRows += '<div class="detail-row">' +
            '<span class="dr-label">' + b.combo + ' cost forfeited</span>' +
            '<span class="dr-val neg">-$' + b.cost.toFixed(2) + '</span>' +
            '</div>';
        }});
        if (!loseRows) loseRows = '<div class="detail-row"><span class="dr-label muted">none</span></div>';

        var netClass = s.profit >= 0 ? "pos" : "neg";

        card.innerHTML =
          '<div class="sc-header">' +
            '<div>' +
              '<div class="sc-winner ' + winnerClass + '">' + s.winner + '</div>' +
              '<div class="sc-total">' + s.total + ' total</div>' +
            '</div>' +
            '<div class="sc-profit ' + profitClass + '">' + fmt2(s.profit) + '</div>' +
          '</div>' +
          '<div class="sc-meta">' +
            '<span class="sc-margin-label">' + s.margin_label + '</span>' +
            '<span class="sc-prob">' + s.prob_pct.toFixed(1) + '%</span>' +
          '</div>' +
          '<div class="sc-expand-hint">CLICK TO EXPAND</div>' +
          '<div class="sc-detail">' +
            '<div class="detail-section-label">WINNING BETS</div>' +
            winRows +
            '<div class="detail-section-label">LOSING BETS (COST FORFEITED)</div>' +
            loseRows +
            '<div class="net-profit-line">' +
              '<span class="np-label">NET PROFIT = PAYOUT &minus; DEPLOYED</span>' +
              '<span class="sc-profit ' + netClass + '">' + fmt2(s.profit) + '</span>' +
            '</div>' +
          '</div>';

        card.addEventListener("click", function() {{
          this.classList.toggle("expanded");
        }});

        grid.appendChild(card);
      }});
    }}

    renderScenarios();
  </script>
</body>
</html>"""

    return html
