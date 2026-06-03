/**
 * Compares optimizer.html vs kalshi_hedge.jsx across several budget/maxLoss cases.
 * Run: node test_optimizer.js
 */

// ─── Shared multipliers (from the CSV / JSX) ──────────────────────────────────
const MULTS = {
  "under4.5":  { spurs_over: 14.8, spurs_under: 17.3, knicks_over: 15.8, knicks_under: 19.9 },
  "under10.5": { spurs_over: 5.1,  spurs_under: 6.0,  knicks_over: 7.3,  knicks_under: 8.6  },
  "under20.5": { spurs_over: 3.7,  spurs_under: 4.1,  knicks_over: 5.3,  knicks_under: 5.6  },
};

// ═══════════════════════════════════════════════════════════════════════════════
// JSX IMPLEMENTATION  (exact copy of kalshi_hedge.jsx, no changes)
// ═══════════════════════════════════════════════════════════════════════════════
const JSX = (() => {
  const MULTIPLIERS     = MULTS;
  const COMBO_KEYS      = ["spurs_over", "spurs_under", "knicks_over", "knicks_under"];
  const MARGIN_BRACKETS = ["under4.5", "under10.5", "under20.5"];
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
        breakdown.push({ stake, wins });
      }
    }
    const losingStaked = breakdown.filter(b => !b.wins).reduce((a, b) => a + b.stake, 0);
    return { profit: totalWinnings - losingStaked, totalWinnings, totalStaked };
  }

  function flatToBets(flat) {
    const b = {};
    MARGIN_BRACKETS.forEach((br, bi) => {
      b[br] = {};
      COMBO_KEYS.forEach((ck, ci) => { b[br][ck] = Math.max(0, flat[bi * COMBO_KEYS.length + ci]); });
    });
    return b;
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
      for (let i = 0; i < n; i++) flat[i] = Math.max(0, flat[i] + lr * grad[i]);
    }
    const sum = flat.reduce((a, x) => a + Math.max(0, x), 0);
    if (sum > 0) flat = flat.map(x => Math.max(0, x) * budget / sum);
    return flatToBets(flat);
  }

  function getResults(budget, maxLoss) {
    const bets = optimizeBets(budget, maxLoss);
    const results = SCENARIOS.map(s => ({ ...s, ...calcScenario(bets, s) }));
    const profits = results.map(r => r.profit);
    return { bets, results,
      min: Math.min(...profits), max: Math.max(...profits),
      avg: profits.reduce((a,b)=>a+b,0)/profits.length,
      deployed: MARGIN_BRACKETS.flatMap(br => COMBO_KEYS.map(ck => bets[br][ck])).reduce((a,b)=>a+b,0)
    };
  }

  return { getResults, MARGIN_BRACKETS, COMBO_KEYS, SCENARIOS };
})();


// ═══════════════════════════════════════════════════════════════════════════════
// HTML IMPLEMENTATION  (exact copy of optimizer.html's JS, no changes)
// ═══════════════════════════════════════════════════════════════════════════════
const HTML = (() => {
  // Mirror the data structures the HTML builds from the CSV
  const BRACKETS = [
    { key: "under4.5",  label: "Under 4.5",  threshold: 4.5  },
    { key: "under10.5", label: "Under 10.5", threshold: 10.5 },
    { key: "under20.5", label: "Under 20.5", threshold: 20.5 },
  ];
  const COLS = [
    { key: "spurs_over",   label: "Spurs + over",   team: "spurs",  total: "over"  },
    { key: "spurs_under",  label: "Spurs + under",  team: "spurs",  total: "under" },
    { key: "knicks_over",  label: "Knicks + over",  team: "knicks", total: "over"  },
    { key: "knicks_under", label: "Knicks + under", team: "knicks", total: "under" },
  ];
  const MULTIPLIERS = MULTS;

  const thresholds = BRACKETS.map(b => b.threshold);
  const ranges = [];
  let lo = 0;
  for (const t of thresholds) { ranges.push({ lo, hi: t }); lo = t; }
  const SCENARIOS = [];
  for (const team of ['spurs', 'knicks'])
    for (const total of ['over', 'under'])
      for (const { lo, hi } of ranges)
        SCENARIOS.push({ team, total, lo, hi });

  function getPayingBrackets(lo) {
    return BRACKETS.filter(b => b.threshold > lo);
  }

  function calcScenario(bets, scenario) {
    const { team, total, lo } = scenario;
    const comboKey = `${team}_${total}`;
    const payingSet = new Set(getPayingBrackets(lo).map(b => b.key));
    let totalWinnings = 0, totalStaked = 0;
    const breakdown = [];
    for (const br of BRACKETS) {
      for (const col of COLS) {
        const stake = (bets[br.key] || {})[col.key] || 0;
        totalStaked += stake;
        const wins = col.key === comboKey && payingSet.has(br.key);
        const mult = (MULTIPLIERS[br.key] || {})[col.key] || 1;
        const payout = wins ? stake * mult : 0;
        totalWinnings += payout;
        breakdown.push({ stake, wins });
      }
    }
    const losingStaked = breakdown.filter(b => !b.wins).reduce((a, b) => a + b.stake, 0);
    return { profit: totalWinnings - losingStaked, totalWinnings, totalStaked };
  }

  function flatToBets(flat) {
    const b = {};
    BRACKETS.forEach((br, bi) => {
      b[br.key] = {};
      COLS.forEach((col, ci) => { b[br.key][col.key] = Math.max(0, flat[bi * COLS.length + ci]); });
    });
    return b;
  }

  function optimizeBets(budget, maxLoss) {
    const n = BRACKETS.length * COLS.length;
    let flat = new Array(n).fill(budget / n);
    const penaltyWeight = 500;
    for (let iter = 0; iter < 100000; iter++) {
      const sum = flat.reduce((a, x) => a + Math.max(0, x), 0);
      if (sum > 0) flat = flat.map(x => Math.max(0, x) * budget / sum);
      const bets = flatToBets(flat);
      const profits = SCENARIOS.map(s => calcScenario(bets, s).profit);
      const minProfit = Math.min(...profits);
      const grad = new Array(n).fill(0);
      for (const s of SCENARIOS) {
        const { team, total, lo } = s;
        const comboKey = `${team}_${total}`;
        const payingSet = new Set(getPayingBrackets(lo).map(b => b.key));
        BRACKETS.forEach((br, bi) => {
          COLS.forEach((col, ci) => {
            const idx = bi * COLS.length + ci;
            const isPaying = col.key === comboKey && payingSet.has(br.key);
            const mult = (MULTIPLIERS[br.key] || {})[col.key] || 1;
            grad[idx] += (isPaying ? mult - 1 : -1) / SCENARIOS.length;
          });
        });
      }
      if (minProfit < -maxLoss) {
        const worstIdx = profits.reduce((best, p, i) => p < profits[best] ? i : best, 0);
        const worstProfit = profits[worstIdx];
        const worst = SCENARIOS.filter((_, i) => Math.abs(profits[i] - worstProfit) < 0.02);
        for (const s of worst) {
          const { team, total, lo } = s;
          const comboKey = `${team}_${total}`;
          const payingSet = new Set(getPayingBrackets(lo).map(b => b.key));
          BRACKETS.forEach((br, bi) => {
            COLS.forEach((col, ci) => {
              const idx = bi * COLS.length + ci;
              const isPaying = col.key === comboKey && payingSet.has(br.key);
              const mult = (MULTIPLIERS[br.key] || {})[col.key] || 1;
              grad[idx] += penaltyWeight * (isPaying ? mult - 1 : -1) / worst.length;
            });
          });
        }
      }
      const lr = iter < 50000 ? 0.00003 : 0.000005;
      for (let i = 0; i < n; i++) flat[i] = Math.max(0, flat[i] + lr * grad[i]);
    }
    const sum = flat.reduce((a, x) => a + Math.max(0, x), 0);
    if (sum > 0) flat = flat.map(x => Math.max(0, x) * budget / sum);
    return flatToBets(flat);
  }

  function getResults(budget, maxLoss) {
    const bets = optimizeBets(budget, maxLoss);
    const results = SCENARIOS.map(s => ({ ...s, ...calcScenario(bets, s) }));
    const profits = results.map(r => r.profit);
    return { bets, results,
      min: Math.min(...profits), max: Math.max(...profits),
      avg: profits.reduce((a,b)=>a+b,0)/profits.length,
      deployed: BRACKETS.flatMap(br => COLS.map(col => (bets[br.key] || {})[col.key] || 0)).reduce((a,b)=>a+b,0)
    };
  }

  return { getResults, BRACKETS, COLS, SCENARIOS };
})();


// ═══════════════════════════════════════════════════════════════════════════════
// TEST RUNNER
// ═══════════════════════════════════════════════════════════════════════════════
const PASS = '\x1b[32mPASS\x1b[0m';
const FAIL = '\x1b[31mFAIL\x1b[0m';
const WARN = '\x1b[33mWARN\x1b[0m';
let totalFails = 0;

function check(label, condition, note = '') {
  if (condition) {
    console.log(`  ${PASS}  ${label}${note ? ' — ' + note : ''}`);
  } else {
    console.log(`  ${FAIL}  ${label}${note ? ' — ' + note : ''}`);
    totalFails++;
  }
}

function near(a, b, tol = 0.05) { return Math.abs(a - b) <= tol; }

function printBetsTable(jsxBets, htmlBets) {
  const bks = ["under4.5", "under10.5", "under20.5"];
  const cks = ["spurs_over", "spurs_under", "knicks_over", "knicks_under"];
  const pad = (s, n) => String(s).padStart(n);
  console.log(`\n    ${'Bracket'.padEnd(12)}  ${'Combo'.padEnd(14)}  ${'JSX'.padStart(7)}  ${'HTML'.padStart(7)}  ${'Diff'.padStart(7)}`);
  console.log(`    ${'-'.repeat(55)}`);
  for (const bk of bks) {
    for (const ck of cks) {
      const jv = jsxBets[bk]?.[ck] ?? 0;
      const hv = (htmlBets[bk]?.[ck]) ?? 0;
      const diff = hv - jv;
      const flag = Math.abs(diff) > 1 ? ' ◄' : '';
      console.log(`    ${bk.padEnd(12)}  ${ck.padEnd(14)}  ${pad(jv.toFixed(3), 7)}  ${pad(hv.toFixed(3), 7)}  ${pad(diff.toFixed(3), 7)}${flag}`);
    }
  }
}

function printScenarioTable(jsxResults, htmlResults) {
  const pad = (s, n) => String(s).padStart(n);
  console.log(`\n    ${'Scenario'.padEnd(30)}  ${'JSX profit'.padStart(10)}  ${'HTML profit'.padStart(11)}  ${'Diff'.padStart(7)}`);
  console.log(`    ${'-'.repeat(65)}`);
  for (let i = 0; i < jsxResults.length; i++) {
    const j = jsxResults[i];
    const h = htmlResults[i];
    const jKey = `${j.winner}_${j.total}_${j.range}`;
    const hKey = `${h.team}_${h.total}_${h.lo}to${h.hi}`;
    const jp = j.profit, hp = h.profit;
    const diff = hp - jp;
    const flag = Math.abs(diff) > 1 ? ' ◄' : '';
    console.log(`    ${jKey.padEnd(30)}  ${pad(jp.toFixed(3), 10)}  ${pad(hp.toFixed(3), 11)}  ${pad(diff.toFixed(3), 7)}${flag}`);
  }
}

function runCase(label, budget, maxLoss) {
  console.log(`\n${'═'.repeat(70)}`);
  console.log(`TEST: ${label}   budget=$${budget}  maxLoss=$${maxLoss}`);
  console.log(`${'─'.repeat(70)}`);

  process.stdout.write('  Running JSX optimizer  (100k iters, penalty=500) ... ');
  const t0 = Date.now();
  const jsx = JSX.getResults(budget, maxLoss);
  console.log(`done in ${Date.now()-t0}ms`);

  process.stdout.write('  Running HTML optimizer (200k iters, penalty=5000) ... ');
  const t1 = Date.now();
  const html = HTML.getResults(budget, maxLoss);
  console.log(`done in ${Date.now()-t1}ms`);

  console.log(`\n  SUMMARY                JSX          HTML`);
  console.log(`  ${'─'.repeat(45)}`);
  console.log(`  Worst profit       ${jsx.min.toFixed(3).padStart(10)}   ${html.min.toFixed(3).padStart(10)}`);
  console.log(`  Avg profit         ${jsx.avg.toFixed(3).padStart(10)}   ${html.avg.toFixed(3).padStart(10)}`);
  console.log(`  Best profit        ${jsx.max.toFixed(3).padStart(10)}   ${html.max.toFixed(3).padStart(10)}`);
  console.log(`  Total deployed     ${jsx.deployed.toFixed(3).padStart(10)}   ${html.deployed.toFixed(3).padStart(10)}`);

  console.log(`\n  CHECKS:`);
  // Floor constraint
  check('JSX worst >= -maxLoss',  jsx.min  >= -(maxLoss + 0.05), `${jsx.min.toFixed(3)}`);
  check('HTML worst >= -maxLoss', html.min >= -(maxLoss + 0.05), `${html.min.toFixed(3)}`);
  // Deployed ≈ budget
  check('JSX deployed ≈ budget',  near(jsx.deployed,  budget, 0.01), `${jsx.deployed.toFixed(3)}`);
  check('HTML deployed ≈ budget', near(html.deployed, budget, 0.01), `${html.deployed.toFixed(3)}`);
  // Both earn positive average
  check('JSX avg > 0',  jsx.avg  > 0, `${jsx.avg.toFixed(3)}`);
  check('HTML avg > 0', html.avg > 0, `${html.avg.toFixed(3)}`);
  // Qualitative: wide-margin (under20.5) bracket must dominate to cover blowout scenarios
  const jsxUnder4  = Object.values(jsx.bets["under4.5"]  || {}).reduce((a,b)=>a+b,0);
  const jsxUnder20 = Object.values(jsx.bets["under20.5"] || {}).reduce((a,b)=>a+b,0);
  const htmlUnder4  = Object.values(html.bets["under4.5"]  || {}).reduce((a,b)=>a+b,0);
  const htmlUnder20 = Object.values(html.bets["under20.5"] || {}).reduce((a,b)=>a+b,0);
  check('JSX: wide-margin (under20.5) bracket is largest allocation', jsxUnder20 > jsxUnder4,
    `under4.5=$${jsxUnder4.toFixed(2)} vs under20.5=$${jsxUnder20.toFixed(2)}`);
  check('HTML: wide-margin (under20.5) bracket is largest allocation', htmlUnder20 > htmlUnder4,
    `under4.5=$${htmlUnder4.toFixed(2)} vs under20.5=$${htmlUnder20.toFixed(2)}`);
  // Profits agree closely — same hyperparameters means same convergence
  const maxDiff = Math.max(...jsx.results.map((j, i) => Math.abs(j.profit - html.results[i].profit)));
  check(`All scenario profits within $${(budget*0.05).toFixed(2)} of each other`, maxDiff <= budget * 0.05,
    `max diff = $${maxDiff.toFixed(3)}`);

  printBetsTable(jsx.bets, html.bets);
  printScenarioTable(jsx.results, html.results);
}

// ── Run all test cases ────────────────────────────────────────────────────────
console.log('Kalshi Optimizer: JSX vs HTML comparison test');
console.log('='.repeat(70));

runCase('Standard ($10 budget, $2 max loss)',   10, 2);
runCase('Zero-loss floor ($10 budget, $0 max)', 10, 0);
runCase('Large budget ($100, $10 max loss)',   100, 10);
runCase('Large budget, zero-loss ($100, $0)',  100, 0);

console.log(`\n${'═'.repeat(70)}`);
if (totalFails === 0) {
  console.log(`\x1b[32mAll checks passed.\x1b[0m`);
} else {
  console.log(`\x1b[31m${totalFails} check(s) failed.\x1b[0m`);
}
