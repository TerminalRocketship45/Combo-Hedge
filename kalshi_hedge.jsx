import { useState } from "react";

// ── Payout multipliers from the Kalshi table ──────────────────────────────────
const MULTIPLIERS = {
  "under4.5":  { spurs_over: 14.8, spurs_under: 17.3, knicks_over: 15.8, knicks_under: 19.9 },
  "under10.5": { spurs_over: 5.1,  spurs_under: 6.0,  knicks_over: 7.3,  knicks_under: 8.6  },
  "under20.5": { spurs_over: 3.7,  spurs_under: 4.1,  knicks_over: 5.3,  knicks_under: 5.6  },
};

const COMBO_KEYS      = ["spurs_over", "spurs_under", "knicks_over", "knicks_under"];
const MARGIN_BRACKETS = ["under4.5", "under10.5", "under20.5"];

const COMBO_LABELS = {
  spurs_over:   "Spurs + Over",
  spurs_under:  "Spurs + Under",
  knicks_over:  "Knicks + Over",
  knicks_under: "Knicks + Under",
};

const SCENARIO_LABELS = {
  "0to4.5":    "Win by 1–4 pts",
  "4.5to10.5": "Win by 5–10 pts",
  "10.5to20.5":"Win by 11–20 pts",
};

// ── Probability model ─────────────────────────────────────────────────────────
//
// All from Kalshi screenshots (Jun 1 2026). User bets NO on "wins by over X"
// so margin probs = 1 - shown%.
//
// Winner:  Spurs 63%,  Knicks 37%
// Total:   Over 54%,   Under 46%
//
// Cumulative margin "under" probs:
//   Spurs: <4.5 = 47%,  <10.5 = 67%,  <20.5 = 79%
//   Knicks:<4.5 = 72%,  <10.5 = 86%,  <20.5 = 95%
//
// Marginal (mutually exclusive) ranges:
//   Spurs  1-4 pts:  47%    Knicks  1-4 pts:  72%
//   Spurs  5-10 pts: 20%    Knicks  5-10 pts: 14%
//   Spurs 11-20 pts: 12%    Knicks 11-20 pts:  9%
//
// Scenario P = P(winner) x P(total) x P(marginal range)
// PROBABILITIES ARE ONLY USED FOR EV/DISPLAY — not the optimizer.

function buildProbabilities() {
  const winnerProb = { spurs: 0.63, knicks: 0.37 };
  const totalProb  = { over: 0.54,  under: 0.46  };

  // Marginal ranges derived from cumulative "under" probs
  const marginProb = {
    spurs: {
      "0to4.5":     0.47,
      "4.5to10.5":  0.67 - 0.47,  // 0.20
      "10.5to20.5": 0.79 - 0.67,  // 0.12
    },
    knicks: {
      "0to4.5":     0.72,
      "4.5to10.5":  0.86 - 0.72,  // 0.14
      "10.5to20.5": 0.95 - 0.86,  // 0.09
    },
  };

  // winnerTotal kept for display in breakdown panel
  const winnerTotal = {
    spurs_over:   winnerProb.spurs  * totalProb.over,
    spurs_under:  winnerProb.spurs  * totalProb.under,
    knicks_over:  winnerProb.knicks * totalProb.over,
    knicks_under: winnerProb.knicks * totalProb.under,
  };

  const scenarioProbs = {};
  for (const winner of ["spurs", "knicks"]) {
    for (const total of ["over", "under"]) {
      for (const range of ["0to4.5", "4.5to10.5", "10.5to20.5"]) {
        scenarioProbs[`${winner}_${total}_${range}`] =
          winnerProb[winner] * totalProb[total] * marginProb[winner][range];
      }
    }
  }
  return { scenarioProbs, marginProb, winnerTotal };
}

const { scenarioProbs, marginProb, winnerTotal } = buildProbabilities();

// ── Scenarios ─────────────────────────────────────────────────────────────────
const SCENARIOS = [];
for (const winner of ["spurs", "knicks"])
  for (const total of ["over", "under"])
    for (const range of ["0to4.5", "4.5to10.5", "10.5to20.5"])
      SCENARIOS.push({ winner, total, range });

function getPayingBrackets(range) {
  if (range === "0to4.5")      return ["under4.5", "under10.5", "under20.5"];
  if (range === "4.5to10.5")   return ["under10.5", "under20.5"];
  if (range === "10.5to20.5")  return ["under20.5"];
  return [];
}

function calcScenario(bets, scenario) {
  const { winner, total, range } = scenario;
  const comboKey = `${winner}_${total}`;
  const payingBrackets = getPayingBrackets(range);
  let totalWinnings = 0, totalStaked = 0;
  const breakdown = [];
  for (const bracket of MARGIN_BRACKETS) {
    for (const key of COMBO_KEYS) {
      const stake = bets[bracket][key];
      totalStaked += stake;
      const wins = key === comboKey && payingBrackets.includes(bracket);
      const payout = wins ? stake * MULTIPLIERS[bracket][key] : 0;
      totalWinnings += payout;
      breakdown.push({
        label: `${COMBO_LABELS[key]} / ${bracket === "under4.5" ? "<4.5" : bracket === "under10.5" ? "<10.5" : "<20.5"}`,
        stake, multiplier: MULTIPLIERS[bracket][key], payout, wins,
      });
    }
  }
  const losingStaked = breakdown.filter(b => !b.wins).reduce((a, b) => a + b.stake, 0);
  const profit = totalWinnings - losingStaked;
  return { profit, totalWinnings, totalStaked, losingStaked, breakdown };
}

function flatToBets(flat) {
  const b = {};
  MARGIN_BRACKETS.forEach((br, bi) => {
    b[br] = {};
    COMBO_KEYS.forEach((ck, ci) => { b[br][ck] = Math.max(0, flat[bi * COMBO_KEYS.length + ci]); });
  });
  return b;
}

function computeEV(bets) {
  let ev = 0;
  for (const s of SCENARIOS) {
    const key  = `${s.winner}_${s.total}_${s.range}`;
    const prob = scenarioProbs[key];
    const { profit } = calcScenario(bets, s);
    ev += prob * profit;
  }
  return ev;
}

function optimizeBets(budget, maxLoss) {
  const n = COMBO_KEYS.length * MARGIN_BRACKETS.length;
  let flat = new Array(n).fill(budget / n);
  const penaltyWeight = 500;

  for (let iter = 0; iter < 100000; iter++) {
    const sum = flat.reduce((a, x) => a + Math.max(0, x), 0);
    if (sum > 0) flat = flat.map(x => Math.max(0, x) * budget / sum);

    const bets    = flatToBets(flat);
    const profits = SCENARIOS.map(s => calcScenario(bets, s).profit);
    const minProfit = Math.min(...profits);
    const grad = new Array(n).fill(0);

    // Maximise average profit equally across all scenarios (NO probability weighting)
    // Probabilities are used only for EV display, not here
    for (const s of SCENARIOS) {
      const { winner, total, range } = s;
      const comboKey = `${winner}_${total}`;
      const payingBrackets = getPayingBrackets(range);
      MARGIN_BRACKETS.forEach((br, bi) => {
        COMBO_KEYS.forEach((ck, ci) => {
          const idx = bi * COMBO_KEYS.length + ci;
          const isPaying = ck === comboKey && payingBrackets.includes(br);
          grad[idx] += (isPaying ? MULTIPLIERS[br][ck] - 1 : -1) / SCENARIOS.length;
        });
      });
    }

    // Floor penalty
    if (minProfit < -maxLoss) {
      const worstScenarios = SCENARIOS.filter((s, i) => Math.abs(profits[i] - minProfit) < 0.02);
      for (const s of worstScenarios) {
        const { winner, total, range } = s;
        const comboKey = `${winner}_${total}`;
        const payingBrackets = getPayingBrackets(range);
        MARGIN_BRACKETS.forEach((br, bi) => {
          COMBO_KEYS.forEach((ck, ci) => {
            const idx = bi * COMBO_KEYS.length + ci;
            const isPaying = ck === comboKey && payingBrackets.includes(br);
            grad[idx] += penaltyWeight * (isPaying ? MULTIPLIERS[br][ck] - 1 : -1) / worstScenarios.length;
          });
        });
      }
    }

    const lr = iter < 50000 ? 0.00003 : 0.000005;
    for (let i = 0; i < n; i++) { flat[i] = Math.max(0, flat[i] + lr * grad[i]); }
  }
  const sum = flat.reduce((a, x) => a + Math.max(0, x), 0);
  if (sum > 0) flat = flat.map(x => Math.max(0, x) * budget / sum);
  return flatToBets(flat);
}

// ── Component ─────────────────────────────────────────────────────────────────
export default function KalshiOptimizer() {
  const [budgetStr,  setBudgetStr]  = useState("10");
  const [maxLossStr, setMaxLossStr] = useState("2");
  const budget  = parseFloat(budgetStr)  || 0;
  const maxLoss = parseFloat(maxLossStr) || 0;

  const [bets,            setBets]            = useState(null);
  const [scenarioResults, setScenarioResults] = useState(null);
  const [running,         setRunning]         = useState(false);
  const [stats,           setStats]           = useState(null);
  const [expandedScenario,setExpandedScenario]= useState(null);
  const [showProbBreakdown, setShowProbBreakdown] = useState(false);

  const runOptimizer = () => {
    setRunning(true); setBets(null); setScenarioResults(null); setExpandedScenario(null);
    setTimeout(() => {
      const result   = optimizeBets(budget, maxLoss);
      const results  = SCENARIOS.map(s => ({ ...s, ...calcScenario(result, s), prob: scenarioProbs[`${s.winner}_${s.total}_${s.range}`] }));
      const profitVals = results.map(r => r.profit);
      const ev = computeEV(result);
      setBets(result);
      setScenarioResults(results);
      setStats({ min: Math.min(...profitVals), max: Math.max(...profitVals), avg: profitVals.reduce((a,b)=>a+b,0)/profitVals.length, ev });
      setRunning(false);
    }, 50);
  };

  const totalBet = bets ? MARGIN_BRACKETS.flatMap(br => COMBO_KEYS.map(ck => bets[br][ck])).reduce((a,b)=>a+b,0) : 0;

  const inputStyle = {
    background:"#0a0a0f", border:"1px solid #3a3a4a", borderRadius:"4px",
    color:"#e8e4d9", fontSize:"1.2rem", fontFamily:"'Courier New',monospace",
    fontWeight:"700", padding:"0.5rem 0.75rem", outline:"none",
    width:"100%", boxSizing:"border-box",
  };

  return (
    <div style={{ minHeight:"100vh", background:"#0a0a0f", color:"#e8e4d9", fontFamily:"'Courier New',monospace", padding:"2rem 1.5rem" }}>

      {/* Header */}
      <div style={{ textAlign:"center", marginBottom:"2rem" }}>
        <div style={{ fontSize:"0.6rem", letterSpacing:"0.5em", color:"#5a9e6f", marginBottom:"0.4rem" }}>KALSHI COMBO</div>
        <h1 style={{ fontSize:"1.9rem", fontWeight:"900", margin:0, letterSpacing:"-0.03em", background:"linear-gradient(135deg,#e8e4d9 0%,#5a9e6f 100%)", WebkitBackgroundClip:"text", WebkitTextFillColor:"transparent" }}>
          PROFIT MAXIMIZER
        </h1>
        <div style={{ fontSize:"0.65rem", color:"#555", marginTop:"0.3rem", letterSpacing:"0.1em" }}>
          SPURS vs KNICKS · EV-WEIGHTED OPTIMIZER
        </div>
      </div>

      {/* Prob sources banner */}
      <div
        onClick={() => setShowProbBreakdown(!showProbBreakdown)}
        style={{ background:"#0d1a12", border:"1px solid #1a4a2a", borderRadius:"6px", padding:"0.6rem 1rem", maxWidth:"440px", margin:"0 auto 1.25rem", cursor:"pointer" }}
      >
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center" }}>
          <div style={{ fontSize:"0.6rem", letterSpacing:"0.25em", color:"#5a9e6f" }}>PROBABILITY SOURCES</div>
          <div style={{ fontSize:"0.6rem", color:"#555" }}>{showProbBreakdown ? "▲ hide" : "▼ show"}</div>
        </div>
        {showProbBreakdown && (
          <div style={{ marginTop:"0.75rem", fontSize:"0.65rem", lineHeight:1.7 }}>
            <div style={{ color:"#aaa", marginBottom:"0.4rem" }}>
              <span style={{ color:"#5a9e6f" }}>Winner</span> — Kalshi Game lines screen
            </div>
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"0.2rem 1rem", marginBottom:"0.6rem" }}>
              <span style={{ color:"#e8e4d9" }}>Spurs win</span><span style={{ color:"#5a9e6f" }}>63%</span>
              <span style={{ color:"#e8e4d9" }}>Knicks win</span><span style={{ color:"#5a9e6f" }}>37%</span>
            </div>
            <div style={{ color:"#aaa", marginBottom:"0.4rem" }}>
              <span style={{ color:"#5a9e6f" }}>Over / Under 217.5</span> — Kalshi Total screen
            </div>
            <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:"0.2rem 1rem", marginBottom:"0.6rem" }}>
              <span style={{ color:"#e8e4d9" }}>Over 217.5</span><span style={{ color:"#5a9e6f" }}>54%</span>
              <span style={{ color:"#e8e4d9" }}>Under 217.5</span><span style={{ color:"#5a9e6f" }}>46%</span>
            </div>
            <div style={{ color:"#aaa", marginBottom:"0.4rem" }}>
              <span style={{ color:"#5a9e6f" }}>Margin ranges</span> — Kalshi Spread screen (1 − "wins by over X%"), marginal slices
            </div>
            <table style={{ width:"100%", fontSize:"0.6rem", borderCollapse:"collapse" }}>
              <thead>
                <tr>
                  <th style={{ textAlign:"left", color:"#666", paddingBottom:"0.2rem" }}>Range</th>
                  <th style={{ color:"#666", paddingBottom:"0.2rem" }}>Spurs</th>
                  <th style={{ color:"#666", paddingBottom:"0.2rem" }}>Knicks</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { range:"0to4.5",     spurs:0.47, knicks:0.72 },
                  { range:"4.5to10.5",  spurs:0.20, knicks:0.14 },
                  { range:"10.5to20.5", spurs:0.12, knicks:0.09 },
                ].map(row => (
                  <tr key={row.range}>
                    <td style={{ color:"#aaa", paddingRight:"0.5rem" }}>{SCENARIO_LABELS[row.range]}</td>
                    <td style={{ textAlign:"center", color:"#5a9e6f" }}>{(row.spurs*100).toFixed(0)}%</td>
                    <td style={{ textAlign:"center", color:"#5a9e6f" }}>{(row.knicks*100).toFixed(0)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{ color:"#555", marginTop:"0.5rem", fontSize:"0.58rem" }}>
              Probabilities used for EV display only — bet allocation is unaffected.
            </div>
          </div>
        )}
      </div>

      {/* Inputs */}
      <div style={{ background:"#111118", border:"1px solid #2a2a3a", borderRadius:"8px", padding:"1.25rem", maxWidth:"440px", margin:"0 auto 1.5rem", display:"flex", flexDirection:"column", gap:"0.9rem" }}>
        <div>
          <label style={{ fontSize:"0.6rem", letterSpacing:"0.3em", color:"#5a9e6f", display:"block", marginBottom:"0.35rem" }}>TOTAL BUDGET ($)</label>
          <input type="number" min="0" step="0.50" value={budgetStr} onChange={e => setBudgetStr(e.target.value)} style={inputStyle} />
        </div>
        <div>
          <label style={{ fontSize:"0.6rem", letterSpacing:"0.3em", color:"#e05a5a", display:"block", marginBottom:"0.35rem" }}>MAX WILLING TO LOSE ($)</label>
          <input type="number" min="0" step="0.50" value={maxLossStr} onChange={e => setMaxLossStr(e.target.value)} style={{ ...inputStyle, borderColor:"#5a3a3a" }} />
          <div style={{ fontSize:"0.58rem", color:"#555", marginTop:"0.25rem" }}>$0 = break-even floor. Higher = more risk, more upside.</div>
        </div>
        <button onClick={runOptimizer} disabled={running} style={{
          background: running ? "#2a3a2a" : "linear-gradient(135deg,#3a7a50,#5a9e6f)",
          border:"none", borderRadius:"4px", color:"#e8e4d9", fontSize:"0.78rem",
          fontWeight:"700", letterSpacing:"0.2em", padding:"0.8rem",
          cursor: running ? "not-allowed" : "pointer", fontFamily:"'Courier New',monospace",
        }}>
          {running ? "SOLVING..." : "OPTIMIZE"}
        </button>
      </div>

      {/* Stats — now 4 boxes */}
      {stats && (
        <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:"0.5rem", maxWidth:"440px", margin:"0 auto 1.5rem" }}>
          {[
            { label:"WORST CASE",   value:stats.min, color: stats.min >= -(maxLoss+0.05) ? "#5a9e6f" : "#e05a5a" },
            { label:"AVG PROFIT",   value:stats.avg, color:"#e8e4d9" },
            { label:"BEST CASE",    value:stats.max, color:"#5a9e6f" },
            { label:"EXPECTED VAL", value:stats.ev,  color: stats.ev >= 0 ? "#f0c040" : "#e05a5a", highlight: true },
          ].map(({ label, value, color, highlight }) => (
            <div key={label} style={{ background: highlight ? "#1a1800" : "#111118", border:`1px solid ${highlight ? "#5a4a00" : "#2a2a3a"}`, borderRadius:"6px", padding:"0.6rem 0.4rem", textAlign:"center" }}>
              <div style={{ fontSize:"0.48rem", letterSpacing:"0.12em", color: highlight ? "#a08020" : "#555", marginBottom:"0.25rem" }}>{label}</div>
              <div style={{ fontSize:"0.95rem", fontWeight:"900", color }}>{value >= 0 ? "+" : ""}{value.toFixed(2)}</div>
            </div>
          ))}
        </div>
      )}

      {/* EV explanation */}
      {stats && (
        <div style={{ maxWidth:"440px", margin:"0 auto 1.5rem", fontSize:"0.6rem", color:"#666", lineHeight:1.6, background:"#0d0d14", border:"1px solid #1a1a2a", borderRadius:"6px", padding:"0.65rem 0.9rem" }}>
          <span style={{ color:"#f0c040" }}>Expected Value</span> = Σ (scenario profit × probability of that scenario). A positive EV means on average, across many repetitions of this bet, you come out ahead.
        </div>
      )}

      {/* Bet allocation table */}
      {bets && (
        <div style={{ overflowX:"auto", marginBottom:"1.5rem" }}>
          <div style={{ fontSize:"0.58rem", letterSpacing:"0.35em", color:"#5a9e6f", marginBottom:"0.5rem" }}>BET ALLOCATION — total ${totalBet.toFixed(2)}</div>
          <table style={{ width:"100%", borderCollapse:"collapse", fontSize:"0.73rem", minWidth:"460px" }}>
            <thead>
              <tr>
                <th style={{ ...thStyle, textAlign:"left" }}>MARGIN</th>
                {COMBO_KEYS.map(ck => <th key={ck} style={thStyle}>{COMBO_LABELS[ck]}</th>)}
              </tr>
            </thead>
            <tbody>
              {MARGIN_BRACKETS.map(br => (
                <tr key={br}>
                  <td style={{ ...tdStyle, textAlign:"left", color:"#5a9e6f", fontWeight:"700" }}>
                    {br === "under4.5" ? "< 4.5 pts" : br === "under10.5" ? "< 10.5 pts" : "< 20.5 pts"}
                  </td>
                  {COMBO_KEYS.map(ck => (
                    <td key={ck} style={tdStyle}>
                      <div style={{ fontWeight:"700" }}>${bets[br][ck].toFixed(2)}</div>
                      <div style={{ fontSize:"0.55rem", color:"#555" }}>{MULTIPLIERS[br][ck]}×</div>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Scenario cards */}
      {scenarioResults && (
        <div style={{ marginBottom:"2rem" }}>
          <div style={{ fontSize:"0.58rem", letterSpacing:"0.35em", color:"#5a9e6f", marginBottom:"0.5rem" }}>
            PROFIT BY SCENARIO — tap to verify math
          </div>
          <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fill,minmax(200px,1fr))", gap:"0.45rem" }}>
            {scenarioResults.map((s, i) => {
              const key        = `${s.winner}_${s.total}_${s.range}`;
              const isExpanded = expandedScenario === key;
              const isWorst    = Math.abs(s.profit - stats.min) < 0.01;
              const isBest     = Math.abs(s.profit - stats.max) < 0.01;
              const winningBets= s.breakdown.filter(b => b.wins);
              const losingBets = s.breakdown.filter(b => !b.wins && b.stake > 0.001);
              const probPct    = (s.prob * 100).toFixed(1);

              return (
                <div key={i}
                  onClick={() => setExpandedScenario(isExpanded ? null : key)}
                  style={{
                    background: isWorst ? "#1a1008" : isBest ? "#0d1a0d" : "#111118",
                    border:`1px solid ${isWorst ? "#5a4010" : isBest ? "#1a5a1a" : "#2a2a3a"}`,
                    borderRadius:"6px", padding:"0.65rem 0.8rem",
                    cursor:"pointer", gridColumn: isExpanded ? "1 / -1" : undefined,
                  }}
                >
                  <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start" }}>
                    <div>
                      <div style={{ fontSize:"0.55rem", color:"#666", marginBottom:"0.1rem" }}>
                        {s.winner.toUpperCase()} · {s.total.toUpperCase()} 217.5
                      </div>
                      <div style={{ fontSize:"0.72rem", fontWeight:"700" }}>{SCENARIO_LABELS[s.range]}</div>
                      {/* Probability badge */}
                      <div style={{ fontSize:"0.55rem", color:"#f0c040", marginTop:"0.15rem" }}>
                        P = {probPct}%
                      </div>
                    </div>
                    <div style={{ textAlign:"right" }}>
                      <div style={{ fontSize:"1.05rem", fontWeight:"900", color: s.profit >= 0 ? "#5a9e6f" : "#e05a5a" }}>
                        {s.profit >= 0 ? "+" : ""}{s.profit.toFixed(2)}
                      </div>
                      <div style={{ fontSize:"0.5rem", color:"#888" }}>
                        EV: {(s.profit * s.prob >= 0 ? "+" : "")}{(s.profit * s.prob).toFixed(3)}
                      </div>
                      <div style={{ fontSize:"0.48rem", color:"#555" }}>{isExpanded ? "▲ hide" : "▼ verify"}</div>
                    </div>
                  </div>

                  {isExpanded && (
                    <div style={{ marginTop:"0.75rem", borderTop:"1px solid #2a2a3a", paddingTop:"0.75rem" }}>
                      <div style={{ fontSize:"0.58rem", color:"#f0c040", marginBottom:"0.5rem" }}>
                        Probability breakdown: {(winnerTotal[`${s.winner}_${s.total}`]*100).toFixed(1)}% (winner×total) × {(marginProb[s.winner][s.range]*100).toFixed(1)}% (margin) = {probPct}%
                      </div>

                      <div style={{ fontSize:"0.6rem", color:"#5a9e6f", letterSpacing:"0.2em", marginBottom:"0.4rem" }}>WINNING BETS</div>
                      {winningBets.length === 0 && <div style={{ fontSize:"0.65rem", color:"#555", marginBottom:"0.5rem" }}>None</div>}
                      {winningBets.map((b, j) => (
                        <div key={j} style={{ fontSize:"0.65rem", marginBottom:"0.2rem", display:"flex", justifyContent:"space-between", color:"#a0e0b0" }}>
                          <span>{b.label}</span>
                          <span>${b.stake.toFixed(2)} × {b.multiplier} = <strong>+${b.payout.toFixed(2)}</strong></span>
                        </div>
                      ))}

                      <div style={{ fontSize:"0.6rem", color:"#e05a5a", letterSpacing:"0.2em", margin:"0.5rem 0 0.4rem" }}>LOSING BETS (stake forfeited)</div>
                      {losingBets.map((b, j) => (
                        <div key={j} style={{ fontSize:"0.65rem", marginBottom:"0.2rem", display:"flex", justifyContent:"space-between", color:"#e09090" }}>
                          <span>{b.label}</span><span>−${b.stake.toFixed(2)}</span>
                        </div>
                      ))}

                      <div style={{ borderTop:"1px solid #2a2a3a", marginTop:"0.5rem", paddingTop:"0.5rem", fontSize:"0.68rem" }}>
                        <div style={{ display:"flex", justifyContent:"space-between", marginBottom:"0.15rem" }}>
                          <span style={{ color:"#888" }}>Total winnings</span>
                          <span style={{ color:"#a0e0b0" }}>+${s.totalWinnings.toFixed(2)}</span>
                        </div>
                        <div style={{ display:"flex", justifyContent:"space-between", marginBottom:"0.15rem" }}>
                          <span style={{ color:"#888" }}>Losing stakes forfeited</span>
                          <span style={{ color:"#e09090" }}>−${s.losingStaked.toFixed(2)}</span>
                        </div>
                        <div style={{ display:"flex", justifyContent:"space-between", fontWeight:"700", fontSize:"0.75rem", marginTop:"0.25rem" }}>
                          <span>NET PROFIT</span>
                          <span style={{ color: s.profit >= 0 ? "#5a9e6f" : "#e05a5a" }}>
                            {s.profit >= 0 ? "+" : ""}{s.profit.toFixed(2)}
                          </span>
                        </div>
                        <div style={{ display:"flex", justifyContent:"space-between", fontSize:"0.65rem", marginTop:"0.2rem" }}>
                          <span style={{ color:"#f0c040" }}>EV contribution</span>
                          <span style={{ color:"#f0c040" }}>{(s.profit*s.prob >= 0 ? "+" : "")}{(s.profit*s.prob).toFixed(4)}</span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {!bets && !running && (
        <div style={{ textAlign:"center", color:"#333", fontSize:"0.8rem", marginTop:"3rem" }}>
          Set your budget, set your max loss, hit OPTIMIZE
        </div>
      )}
    </div>
  );
}

const thStyle = { padding:"0.4rem 0.55rem", textAlign:"center", fontSize:"0.58rem", letterSpacing:"0.1em", color:"#666", borderBottom:"1px solid #2a2a3a" };
const tdStyle = { padding:"0.5rem 0.55rem", textAlign:"center", borderBottom:"1px solid #1a1a2a" };
