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
const report = {
  generated_at: GEN,
  mock: true,
  sections: {
    deficit_recovery: { meta: M("synthetic", 24, "personas", "6 injected deficit types x 4 synthetic apprentices", "Which deficit was injected, and what it costs."), precision: 0.92, recall: 0.83, rows: [
      { deficit: "Skips the cliff check", true_s: 96, est_s: 91, ci: [66, 118] },
      { deficit: "Hunts for the calculators", true_s: 45, est_s: 44, ci: [31, 59] },
      { deficit: "Freezes before the result", true_s: 30, est_s: 34, ci: [18, 51] },
      { deficit: "Slow household entry", true_s: 24, est_s: 21, ci: [11, 33] },
      { deficit: "Slow reconcile", true_s: 20, est_s: 24, ci: [13, 35] },
      { deficit: "Re-reads the case file", true_s: 12, est_s: 6, ci: [-2, 15] } ] },
    null_placebo: { meta: M("synthetic", 24, "personas", "cluster bootstrap by person, B = 2000", "Expert against expert, and shuffled labels, should show about zero."), real: { gap_s: 276, ci: [221, 334] }, placebo: { gap_s: 3.1, ci: [-6.0, 12.4] }, null: { gap_s: -1.8, ci: [-14.5, 10.9] } },
    hazard: hazard,
    ope: { meta: M("synthetic", 5000, "episodes", "simulator with known ground truth, 200 resamples", "Coaching-policy value. The true value is known because the simulator is ours."), true_value: 0.412, estimators: [
      { name: "Naive on-policy average", value: 0.521, ci: [0.503, 0.540] },
      { name: "Inverse propensity (IPS)", value: 0.389, ci: [0.318, 0.462] },
      { name: "Self-normalised IPS", value: 0.405, ci: [0.366, 0.444] },
      { name: "Doubly robust", value: 0.415, ci: [0.389, 0.441] } ] },
    routing: { meta: M("synthetic", 600, "households", "calibration 300 / held-out 300", "Auto-approve the safest cases and send the rest to an expert."), alpha: 0.05, chosen_coverage: 0.7, held_out_error: 0.034, held_out_ci: [0.016, 0.058], bound_held: true, curve: riskCov, expert_minutes_per_case: 2.4 },
    ski_rental: { meta: M("synthetic", 400, "days", "simulated workdays, 50 routines"), hindsight: 1.0, rows: [
      { rule: "Build now", regret: 1.9, ci: [1.7, 2.2] },
      { rule: "Build at break-even", regret: 1.5, ci: [1.4, 1.7] },
      { rule: "Ski rental with predictions", regret: 1.2, ci: [1.1, 1.3] } ] },
    presence: { meta: M("synthetic", 84, "days", "4 personas x 21 days, last 7 held out"), brier: 0.092, brier_baseline_overnight: 0.171, brier_baseline_idle5: 0.139, interruption_rate: 0.04, interruption_cap: 0.05, calibration: [
      { p_mean: 0.08, freq: 0.07, n: 210 }, { p_mean: 0.25, freq: 0.29, n: 156 }, { p_mean: 0.45, freq: 0.41, n: 122 }, { p_mean: 0.65, freq: 0.68, n: 97 }, { p_mean: 0.85, freq: 0.82, n: 71 }, { p_mean: 0.95, freq: 0.96, n: 44 } ] },
    agent_claims: { meta: M("synthetic", 120, "episodes", "20 households x 3 sites x 2 variants"), false_claims: 7, claims: 120, false_claim_rate: 0.058, false_claim_ci: [0.028, 0.116], caught_by_code_check: 7, brier: 0.071 },
    redteam: { meta: M("synthetic", 96, "episodes", "8 attack types x 12 runs per row, sandbox sites"), false_pause_rate: 0.021, false_pause_ci: [0.006, 0.07], rows: [
      { ablation: "All layers on", attack_success: 0.0, attack_ci: [0.0, 0.038], task_success: 0.89, task_ci: [0.81, 0.94] },
      { ablation: "Without the quarantined reader", attack_success: 0.17, attack_ci: [0.1, 0.27], task_success: 0.9, task_ci: [0.82, 0.95] },
      { ablation: "Without the injection detector", attack_success: 0.1, attack_ci: [0.05, 0.19], task_success: 0.9, task_ci: [0.82, 0.95] },
      { ablation: "Without the action gate", attack_success: 0.24, attack_ci: [0.16, 0.34], task_success: 0.9, task_ci: [0.82, 0.95] },
      { ablation: "Without data-flow rules", attack_success: 0.08, attack_ci: [0.04, 0.16], task_success: 0.9, task_ci: [0.82, 0.95] },
      { ablation: "All layers off", attack_success: 0.52, attack_ci: [0.42, 0.62], task_success: 0.91, task_ci: [0.83, 0.95] } ] },
    study: { meta: M("real", 4, "people", "within-subject, counterbalanced, teammates only", "n = 4. Treat every number here as a case study, not a result."), rows: [
      { participant: "Teammate A", unassisted_before_s: 512, unassisted_after_s: 418 },
      { participant: "Teammate B", unassisted_before_s: 466, unassisted_after_s: 431 },
      { participant: "Teammate C", unassisted_before_s: 540, unassisted_after_s: 444 },
      { participant: "Teammate D", unassisted_before_s: 489, unassisted_after_s: 472 } ], mean_change_s: -59.5, mean_change_ci: [-118.0, -1.0] },
    limitations: [
      { id: "L1", text: "Most results come from synthetic apprentices and synthetic personas. Synthetic results carry a badge. They show the method recovers what we planted, not that real workers behave this way.", severity: "high" },
      { id: "L2", text: "The live study has n = 4 teammates. Intervals are wide and the sample is not representative of benefits processors.", severity: "high" },
      { id: "L3", text: "The expert reference is one scripted person per task. A different expert would draw a different ribbon.", severity: "medium" },
      { id: "L4", text: "Off-policy results come from a simulator we wrote. They test the estimators, not the policy on real people.", severity: "medium" },
      { id: "L5", text: "Presence is learned from 3 weeks of one persona per map. Real schedules drift, and a new job or holiday breaks the map until it relearns.", severity: "medium" },
      { id: "L6", text: "The agent runs on local sandbox sites and synthetic households. Real calculators change layout and may block automation.", severity: "medium" },
      { id: "L7", text: "Autonomy rung A3 needs a Wilson lower bound of 0.95 (about 75 clean runs). The demo does not reach it, and says so.", severity: "low" },
      { id: "L8", text: "The red-team suite covers eight attack types on our own pages. It is not a security proof.", severity: "low" } ],
  },
};
out("eval-report.json", report);
console.log("fixtures written: presence idle", r(idleSum, 1), "h; bins", bins.length);
