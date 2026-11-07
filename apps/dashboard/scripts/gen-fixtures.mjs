// One-off generator for the large synthetic fixtures (presence map, hazard series, eval report).
// Output goes to src/fixtures/*.json. Everything is synthetic and deterministic (seeded).
// Run: node scripts/gen-fixtures.mjs
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const out = (name, obj) => writeFileSync(join(here, "..", "src", "fixtures", name), JSON.stringify(obj, null, 1) + "\n");

function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rnd = mulberry32(20261107);
const r = (x, d = 3) => Math.round(x * 10 ** d) / 10 ** d;
const GEN = "2026-11-07T14:40:00Z";

/* -- Presence: night-owl persona, 21 days, 15-minute bins ------------------ */
// True curve: piecewise-linear key points of (hour -> p) per day type. Dow 0 = Monday.
const WEEKDAY = [[0, 0.78], [1.5, 0.62], [2.75, 0.2], [3.75, 0.04], [10, 0.04], [11.5, 0.2], [12.5, 0.55], [14.5, 0.5], [15.5, 0.2], [18, 0.14], [19.5, 0.5], [21, 0.86], [24, 0.8]];
const WEEKEND = [[0, 0.84], [2.5, 0.72], [4, 0.22], [5, 0.04], [11, 0.04], [13, 0.14], [16, 0.22], [19, 0.3], [21, 0.76], [24, 0.84]];
function curve(pts, h) {
  for (let i = 1; i < pts.length; i++) {
    if (h <= pts[i][0]) {
      const [h0, p0] = pts[i - 1], [h1, p1] = pts[i];
      return p0 + ((p1 - p0) * (h - h0)) / (h1 - h0);
    }
  }
  return pts[pts.length - 1][1];
}
const truth = [];
for (let d = 0; d < 7; d++) {
  const row = [];
  for (let s = 0; s < 96; s++) row.push(curve(d >= 5 || d === 4 ? (d === 4 ? WEEKDAY : WEEKEND) : WEEKDAY, (s + 0.5) / 4));
  truth.push(row);
}
const WEEKS = 3;
const obs = truth.map((row) => row.map((p) => { let k = 0; for (let w = 0; w < WEEKS; w++) if (rnd() < p) k++; return k; }));
const bins = [];
let idleSum = 0, idleVar = 0;
const quiet = { start: "03:00", end: "10:00", days: [0, 1, 2, 3, 4, 5, 6] };
const inQuiet = (s) => s >= 12 && s < 40;
const typeOf = (d) => (d >= 5 ? [5, 6] : [0, 1, 2, 3, 4]);
for (let d = 0; d < 7; d++) {
  for (let s = 0; s < 96; s++) {
    // Own observations (weight 1) plus the same day-type pooled at half weight, smoothed over +-2 neighbouring bins.
    let k = 0, n = 0;
    for (const o of [-2, -1, 0, 1, 2]) {
      const ss = s + o;
      if (ss < 0 || ss > 95) continue;
      k += obs[d][ss]; n += WEEKS;
      for (const d2 of typeOf(d)) if (d2 !== d) { k += 0.5 * obs[d2][ss] * (1 / 1); n += 0.5 * WEEKS; }
    }
    const p = (k + 0.5) / (n + 1);
    const sd = Math.sqrt((p * (1 - p)) / (n + 1));
    const lo = Math.max(0, p - 1.96 * sd), hi = Math.min(1, p + 1.96 * sd);
    bins.push({ dow: d, slot: s, p: r(p), lo: r(lo), hi: r(hi) });
    if (!inQuiet(s)) { idleSum += (1 - p) * 0.25; idleVar += 0.0625 * sd * sd; }
  }
}
const idleSd = Math.sqrt(idleVar) * 3.2; // widen for correlation between neighbouring bins
const forecast = [];
const S = (x) => 0.55 * Math.exp(-x / 45) + 0.45 * Math.exp(-x / 380);
for (let m = 0; m <= 360; m += 10) {
  const s = S(m), se = Math.sqrt((s * (1 - s)) / 41);
  forecast.push({ d_min: m, survival: r(s, 4), lo: r(Math.max(0, s - 1.96 * se), 4), hi: r(Math.min(1, s + 1.96 * se), 4) });
}
out("presence.json", {
  meta: { origin: "synthetic", n: 21, n_unit: "days", split: "3 weeks of one night-owl persona; posterior per 15-minute bin, smoothed over neighbours", interval_level: 0.95, note: "Synthetic persona 'night owl'. The schedule change on day 15 is not modelled here.", generated_at: GEN },
  data: { bins, idle_capacity_h: { mean: r(idleSum, 1), lo: r(idleSum - 1.96 * idleSd, 1), hi: r(idleSum + 1.96 * idleSd, 1) }, quiet_hours: quiet, forecast, decision_threshold: 0.4 },
});

/* -- Hazard: one novice episode in 30 s bins, plus reliability ------------- */
const series = [];
const ep = [0.06, 0.07, 0.09, 0.14, 0.22, 0.28, 0.2, 0.17, 0.19, 0.31, 0.46, 0.52, 0.4, 0.3, 0.26, 0.33, 0.24];
ep.forEach((p, i) => series.push({ t: i * 30, p }));
const calibration = [
  [0.04, 0.05, 412], [0.12, 0.1, 318], [0.22, 0.2, 244], [0.31, 0.34, 176], [0.42, 0.4, 131], [0.52, 0.55, 94], [0.63, 0.6, 71], [0.74, 0.79, 48], [0.84, 0.81, 33], [0.93, 0.9, 19],
].map(([p_mean, freq, n]) => ({ p_mean, freq, n }));
const hazard = {
  meta: { origin: "synthetic", n: 1546, n_unit: "episodes", split: "leave-one-person-out", interval_level: 0.95, note: "1546 scored 30-second bins from synthetic apprentices with injected deficits. Not yet validated on real traces.", generated_at: GEN },
  data: { series, model: { log_loss: 0.412, brier: 0.131, ece: 0.031, ci_log_loss: [0.371, 0.458] }, baselines: { base_rate: { log_loss: 0.628, brier: 0.215, ece: 0.012 }, time_since_progress: { log_loss: 0.514, brier: 0.168, ece: 0.047 } }, calibration, false_alarms_per_hour: 1.8, split: "leave-one-person-out" },
};
out("hazard.json", hazard);

/* -- Eval report ------------------------------------------------------------ */
const M = (origin, n, n_unit, split, note = null) => ({ origin, n, n_unit, split, interval_level: 0.95, note, generated_at: GEN });
const riskCov = [];
for (let c = 0.1; c <= 1.0001; c += 0.05) {
  const risk = 0.006 + 0.15 * Math.pow(c, 2.6);
  const w = 0.012 + 0.04 * c * (1 - 0.3 * c);
  riskCov.push({ coverage: r(c, 2), risk: r(risk, 4), ci: [r(Math.max(0, risk - w), 4), r(risk + w, 4)] });
}
const stub = (status, reason, meta) => ({ status, reason, meta });
const report = {
  generated_at: GEN,
  mock: true,
  sections: {
    deficit_recovery: { meta: M("synthetic", 24, "personas", "6 injected deficit types, 16 synthetic novices against 8 experts", "Which deficit was injected, and what it costs, recovered from the traces alone."), rows: [
      { deficit: "skip_check", label: "Skips the cliff check", injected_price_s: 96, recovered_price_s: 91, ci: [66, 118], precision: 0.92, recall: 0.88 },
      { deficit: "search_loop", label: "Searches in loops", injected_price_s: 97, recovered_price_s: 96.9, ci: [71, 122], precision: 0.95, recall: 0.94 },
      { deficit: "idle_before_enter", label: "Pauses before entering", injected_price_s: 38.6, recovered_price_s: 38.6, ci: [18, 59], precision: 0.9, recall: 0.86 },
      { deficit: "repeated_read", label: "Reads the same page again", injected_price_s: 24, recovered_price_s: 23.5, ci: [12, 36], precision: 0.7, recall: 0.82 },
      { deficit: "copy_error", label: "Copies a wrong figure", injected_price_s: 15, recovered_price_s: 15.2, ci: [6, 26], precision: 0.88, recall: 0.71 },
      { deficit: "slow_reconcile", label: "Slow reconcile", injected_price_s: 22, recovered_price_s: 24, ci: [12, 35], precision: 0.86, recall: 0.8 } ], overall: { precision: 0.87, recall: 0.84 } },
    routines: { meta: M("synthetic", 4, "personas", "planted routines per persona, found by the routine finder", "Raw precision is low until the value gate removes routines that would not pay for themselves; proposals are what the worker sees."), rows: [
      { persona: "Nine to five", planted: 3, found: 3, precision: 0.25, recall: 1.0 },
      { persona: "Night owl", planted: 3, found: 3, precision: 0.2, recall: 1.0 },
      { persona: "Shift worker", planted: 3, found: 2, precision: 0.22, recall: 0.67 },
      { persona: "Irregular", planted: 3, found: 3, precision: 0.2, recall: 1.0 } ], overall: { precision: 0.22, recall: 0.92 }, proposals_after_value_gate: { proposed: 8, real: 8 } },
    null_placebo: { meta: M("synthetic", 24, "people", "cluster bootstrap by person, 1000 draws", "Expert against expert, and shuffled labels, should show about zero."), real: { gap_s: 230, ci: [193, 273] }, placebo: { gap_s: 7.1, ci: [-3.1, 18.4] }, null: { gap_s: 46, ci: [-36, 117] } },
    hazard: hazard,
    ope: { meta: M("synthetic", 5000, "episodes", "simulator with known ground truth, 200 resamples", "Coaching-policy value. The true value is known because the simulator is ours."), true_value: 0.412, estimators: [
      { name: "naive", label: "Naive on-policy average", value: 0.521, ci: [0.503, 0.540] },
      { name: "ips", label: "Inverse propensity (IPS)", value: 0.389, ci: [0.318, 0.462] },
      { name: "snips", label: "Self-normalised IPS", value: 0.405, ci: [0.366, 0.444] },
      { name: "dr", label: "Doubly robust", value: 0.415, ci: [0.389, 0.441] } ] },
    routing: { meta: M("synthetic", 600, "households", "calibration 300 / held-out 300", "Auto-approve the safest cases and send the rest to an expert."), alpha: 0.05, chosen_coverage: 0.7, held_out_error: 0.034, held_out_ci: [0.016, 0.058], bound_held: true, curve: riskCov, expert_minutes_per_case: 2.4 },
    ski_rental: { meta: M("synthetic", 400, "days", "simulated workdays, 50 routines"), hindsight_regret: 1.0, rows: [
      { rule: "buy-now", label: "Build now", regret: 1.9, ci: [1.7, 2.2] },
      { rule: "break-even", label: "Build at break-even", regret: 1.5, ci: [1.4, 1.7] },
      { rule: "predictions", label: "Ski rental with predictions", lambda: 0.5, regret: 1.2, ci: [1.1, 1.3] } ] },
    presence: { meta: M("synthetic", 84, "days", "4 personas x 21 days, last 7 held out", "The two baselines are start policies, not forecasts, so they have no Brier score. The map is worse than its baseline for the shift worker."), brier: 0.171, brier_prior_only: 0.2, interruption_rate: 0.04, cap: 0.05, idle_time_used: 0.46,
      baselines: { fixed_overnight: { interruption_rate: 0.09, idle_time_used: 0.31 }, idle_5min: { interruption_rate: 0.21, idle_time_used: 0.74 } },
      reliability: [{ p_mean: 0.08, freq: 0.07, n: 210 }, { p_mean: 0.25, freq: 0.29, n: 156 }, { p_mean: 0.45, freq: 0.41, n: 122 }, { p_mean: 0.65, freq: 0.68, n: 97 }, { p_mean: 0.85, freq: 0.82, n: 71 }, { p_mean: 0.95, freq: 0.96, n: 44 }] },
    agent_claims: { meta: M("synthetic", 120, "episodes", "20 households x 3 sites x 2 variants", "The code check catches every false claim by construction: it decides success, not the model. This section measures how well the claim itself can be predicted."), brier: 0.071, base_rate: 0.058,
      reliability: [{ p_mean: 0.04, freq: 0.03, n: 70 }, { p_mean: 0.2, freq: 0.24, n: 25 }, { p_mean: 0.5, freq: 0.44, n: 14 }, { p_mean: 0.8, freq: 0.86, n: 11 }] },
    redteam: { meta: M("synthetic", 96, "episodes", "8 attack types x 12 runs per row, sandbox sites", "The planner is a script, not a real model, so these rows show what each layer does when the planner always falls for the attack."), false_pause_rate: 0.021, false_pause_ci: [0.006, 0.07], rows: [
      { ablation: "all_on", label: "All layers on", attack_success: 0.0, attack_ci: [0.0, 0.038], task_success: 0.89, task_ci: [0.81, 0.94] },
      { ablation: "no_reader", label: "Without the quarantined reader", attack_success: 0.17, attack_ci: [0.1, 0.27], task_success: 0.9, task_ci: [0.82, 0.95] },
      { ablation: "no_detector", label: "Without the injection detector", attack_success: 0.1, attack_ci: [0.05, 0.19], task_success: 0.9, task_ci: [0.82, 0.95] },
      { ablation: "no_gate", label: "Without the action gate", attack_success: 0.24, attack_ci: [0.16, 0.34], task_success: 0.9, task_ci: [0.82, 0.95] },
      { ablation: "no_dataflow", label: "Without data-flow rules", attack_success: 0.08, attack_ci: [0.04, 0.16], task_success: 0.9, task_ci: [0.82, 0.95] },
      { ablation: "all_off", label: "All layers off", attack_success: 0.52, attack_ci: [0.42, 0.62], task_success: 0.91, task_ci: [0.83, 0.95] } ] },
    redteam_live: { meta: M("synthetic", 12, "episodes", "real model on the sandbox pages, 3 attack types x 4 runs", "A real model, with a very small n. A spot check, not a rate."), false_pause_rate: 0.0, false_pause_ci: [0.0, 0.3], rows: [
      { ablation: "all_on", label: "All layers on", attack_success: 0.0, attack_ci: [0.0, 0.26], task_success: 0.83, task_ci: [0.55, 0.95] },
      { ablation: "all_off", label: "All layers off", attack_success: 0.33, attack_ci: [0.14, 0.61], task_success: 0.92, task_ci: [0.65, 0.99] } ] },
    pooling: { meta: M("synthetic", 4, "personas", "leave one person out"), note: "Mean absolute error of the predicted idle window, in minutes, after this many episodes of a new person.", rows: [
      { n_episodes: 0, no_pooling: 41.0, partial_pooling: 24.0, complete_pooling: 22.5, ci: { no_pooling: [30, 52], partial_pooling: [18, 31], complete_pooling: [17, 28] } },
      { n_episodes: 1, no_pooling: 33.0, partial_pooling: 20.1, complete_pooling: 22.4, ci: { no_pooling: [24, 42], partial_pooling: [15, 26], complete_pooling: [17, 28] } },
      { n_episodes: 3, no_pooling: 22.0, partial_pooling: 16.3, complete_pooling: 22.4, ci: { no_pooling: [16, 28], partial_pooling: [12, 21], complete_pooling: [17, 28] } },
      { n_episodes: 10, no_pooling: 14.0, partial_pooling: 12.9, complete_pooling: 22.3, ci: { no_pooling: [10, 18], partial_pooling: [9, 17], complete_pooling: [17, 28] } } ] },
    study: stub("not_run", "The live study with the four teammates has not run yet, so there are no human results here.", M("real", 0, "people", null, "n = 4 when it runs. Treat every number as a case study.")),
    limitations: [
      { id: "L1", text: "Most results come from synthetic apprentices and synthetic personas. Synthetic results carry a badge. They show the method recovers what we planted, not that real workers behave this way.", severity: "high", source: "all synthetic sections" },
      { id: "L2", text: "The live study has n = 4 teammates, and it has not run yet. Intervals will be wide and the sample is not representative of benefits processors.", severity: "high", source: "study" },
      { id: "L3", text: "The shuffled-label control is not tight: about +46 s with an interval from -36 to +117 s, against a real gap of 230 s. Read the gap with that in mind.", severity: "medium", source: "null_placebo" },
      { id: "L4", text: "The expert reference is one scripted person per task. A different expert would draw a different ribbon.", severity: "medium", source: "genome" },
      { id: "L5", text: "Off-policy results come from a simulator we wrote. They test the estimators, not the policy on real people.", severity: "medium", source: "ope" },
      { id: "L6", text: "Presence is learned from 3 weeks of one persona per map. The map is worse than its baseline for the shift worker, and a new job or holiday breaks it until it relearns.", severity: "medium", source: "presence" },
      { id: "L7", text: "The agent runs on local sandbox sites and synthetic households. Real calculators change layout and may block automation.", severity: "medium", source: "agent_claims" },
      { id: "L8", text: "The red-team suite uses a scripted planner on our own pages, plus a very small run with a real model. It is not a security proof.", severity: "low", source: "redteam" },
      { id: "L9", text: "Autonomy rung A3 needs a Wilson lower bound of 0.95 (about 75 clean runs). The demo does not reach it, and says so.", severity: "low", source: "routines" } ],
  },
};
// eval-report.json is owned by scripts/sync-eval-fixture.mjs (the real report from the eval harness); `report` above is kept only as a hand-made shape reference.
void report;
console.log("fixtures written: presence idle", r(idleSum, 1), "h; bins", bins.length);
