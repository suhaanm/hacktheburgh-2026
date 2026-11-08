// Generator for the Growth screen's example data (three stories). Deterministic (seeded). Run from apps/dashboard:
//   node src/fixtures/growth-gen.mjs
// Writes growth.json (a learner who improves), growth-plateau.json, growth-sparse.json. Each file holds what the engine would
// answer: `overall` and `skills[id]` are GET /growth envelopes, `ledger` is GET /cue/ledger. Everything is SYNTHETIC: invented
// learners with planted learning curves, never people. The numbers inside are computed from the generated rows (Wilson shares,
// Theil-Sen trend with a bootstrap interval, medians with bootstrap intervals), so the file agrees with itself.
// The field names follow what CUE-ENGINE agreed with GROWTH on 7 Nov 2026. Where the engine's own method differs, its fixture wins.
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const out = (name, obj) => writeFileSync(join(here, name), JSON.stringify(obj) + "\n");

function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const r3 = (x) => Math.round(x * 1000) / 1000;
const r1 = (x) => Math.round(x * 10) / 10;
const AS_OF = "2026-11-07T17:30:00Z";
const AS_OF_MS = Date.parse(AS_OF);
const DAY = 86400000;

const SKILLS = [
  { id: "reads-error-first", label: "Read the error message before retrying", name: "reading the error first" },
  { id: "enter-household-once", label: "Enter the household once, accurately, then reuse it", name: "entering the household once" },
  { id: "check-the-cliff", label: "Probe the cliff edge on every calculator", name: "the cliff check" },
  { id: "reconcile-before-noting", label: "Reconcile the results before writing the note", name: "reconciling before the note" },
  { id: "note-with-evidence", label: "Write the note with the figures and what was checked", name: "the case note" },
];
const STEPS = { "reads-error-first": "read_error", "enter-household-once": "enter_household", "check-the-cliff": "cliff_a", "reconcile-before-noting": "reconcile", "note-with-evidence": "copy_note" };

/* -- Statistics ------------------------------------------------------------------------------- */
function wilson(k, n, z = 1.96) {
  if (n <= 0) return [0, 1];
  const p = k / n, z2 = z * z;
  const c = p + z2 / (2 * n);
  const m = z * Math.sqrt((p * (1 - p)) / n + z2 / (4 * n * n));
  return [Math.max(0, (c - m) / (1 + z2 / n)), Math.min(1, (c + m) / (1 + z2 / n))];
}
const mean = (a) => a.reduce((x, y) => x + y, 0) / a.length;
const median = (a) => { const s = [...a].sort((x, y) => x - y); const m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
const quant = (a, q) => { const s = [...a].sort((x, y) => x - y); return s[Math.min(s.length - 1, Math.max(0, Math.floor(q * s.length)))]; };
function theilSen(xs, ys) {
  const sl = [];
  for (let i = 0; i < xs.length; i++) for (let j = i + 1; j < xs.length; j++) if (xs[j] !== xs[i]) sl.push((ys[j] - ys[i]) / (xs[j] - xs[i]));
  return sl.length ? median(sl) : null;
}

/* -- One learner ------------------------------------------------------------------------------ */
// spec: { person, seed, origin_detail, perSkill: [{n, start, floor, tau, from}], noteOrigin }
function simulate(spec) {
  const rnd = mulberry32(spec.seed);
  const ln = (med, sd) => med * Math.exp(sd * (rnd() + rnd() + rnd() + rnd() - 2) * 1.7);
  const pick = (w) => { let u = rnd(), t = 0; for (const [k, p] of w) { t += p; if (u <= t) return k; } return w[w.length - 1][0]; };
  const occ = [];
  SKILLS.forEach((s, si) => {
    const cfg = spec.perSkill[si];
    if (!cfg || cfg.n === 0) return;
    // spread this skill's occurrences over its days, sorted
    const times = Array.from({ length: cfg.n }, () => cfg.from + rnd() * (cfg.to - cfg.from)).sort((a, b) => a - b);
    times.forEach((day, idx) => occ.push({ si, idx, day }));
  });
  occ.sort((a, b) => a.day - b.day || a.si - b.si);
  const mast = SKILLS.map(() => 0.25);
  const lastT = SKILLS.map(() => null);
  const taughtAt = SKILLS.map(() => []); // [{t, rowIndex}]
  const rows = [];
  let seq = 0;
  for (const o of occ) {
    const cfg = spec.perSkill[o.si];
    const t = spec.t0 + o.day * DAY + (9 + rnd() * 8) * 3600000;
    // idle decay of mastery
    if (lastT[o.si] != null) mast[o.si] *= Math.exp(-((t - lastT[o.si]) / DAY) / 60);
    const before = mast[o.si];
    const level = (m) => (m < 0.35 ? 1 : m < 0.6 ? 2 : m < 0.8 ? 3 : 4);
    const lb = level(before);
    let outcome, accepted = false, dismissed = false, trigger = "none", tier = 0, ttp = null;
    const scripted = cfg.script?.[o.idx];
    const pa = cfg.ramp ? cfg.floor + (cfg.start - cfg.floor) * Math.max(0, 1 - o.idx / cfg.ramp) : cfg.floor + (cfg.start - cfg.floor) * Math.exp(-o.idx / cfg.tau);
    const u = rnd();
    const kind = scripted ?? (u < pa ? "assisted" : u < pa + 0.03 ? "error" : u < pa + 0.04 ? "abandoned" : "clean");
    const retrieval = lb >= 3 && lastT[o.si] != null && (t - lastT[o.si]) / DAY >= 3 && kind === "clean";
    const tierW = { 1: [[2, 0.35], [3, 0.45], [4, 0.2]], 2: [[1, 0.4], [2, 0.45], [3, 0.15]], 3: [[1, 0.8], [2, 0.2]], 4: [[1, 1]] }[lb];
    if (kind === "assisted") {
      outcome = "assisted"; accepted = true; trigger = rnd() < 0.7 ? "auto" : "asked"; tier = pick(tierW);
      ttp = ln(Math.max(5, 20 * Math.exp(-o.idx / 25) + 6), 0.3);
    } else if (kind === "clean") {
      outcome = "clean";
      if (!retrieval && lb <= 2 && rnd() < 0.2) { dismissed = true; trigger = "auto"; tier = pick([[1, 0.6], [2, 0.4]]); ttp = ln(8, 0.25); }
    } else { outcome = kind; if (rnd() < 0.5) { trigger = "auto"; tier = pick([[1, 0.5], [2, 0.5]]); ttp = ln(24, 0.3); } }
    const lost = outcome === "clean" ? ln(Math.max(1.5, 3 + 14 * Math.exp(-o.idx / 14)), 0.35)
      : outcome === "assisted" ? ln(Math.max(8, 14 + 30 * Math.exp(-o.idx / 20)), 0.3)
      : ln(45, 0.3);
    // mastery update: independent success pulls up; leaning on a cue pulls it down a little; errors pull down more
    mast[o.si] = Math.min(0.99, outcome === "clean" ? mast[o.si] + (1 - mast[o.si]) * 0.14 : outcome === "assisted" ? mast[o.si] * 0.93 : mast[o.si] * 0.88);
    const taught = outcome === "assisted" && (taughtAt[o.si].length === 0 || t - taughtAt[o.si].at(-1).t > 5 * DAY);
    const row = {
      id: `a_${spec.person.slice(-6)}_${String(++seq).padStart(4, "0")}`,
      person: spec.person,
      origin: "synthetic",
      t_hour: new Date(t).toISOString().slice(0, 13),
      role: "benefits-processor",
      skill: SKILLS[o.si].id,
      step: STEPS[SKILLS[o.si].id],
      stream: "assist",
      trigger,
      stuck_bucket: tier === 0 ? null : pick([["p60_79", 0.4], ["p80_94", 0.4], ["p95_100", 0.2]]),
      tier,
      options_shown: trigger === "auto" && tier >= 2 && rnd() < 0.3 ? 3 : 0,
      answer_id: null,
      accepted,
      dismissed,
      seconds_to_progress: ttp == null ? null : r1(ttp),
      lost_s: r1(lost),
      outcome,
      level_before: lb,
      level_after: level(mast[o.si]),
      taught,
      retrieval,
      origin_detail: spec.origin_detail,
    };
    if (row.options_shown) row.answer_id = pick([[row.step, 0.8], ["other", 0.2]]);
    if (taught) taughtAt[o.si].push({ t, row: rows.length });
    lastT[o.si] = t;
    rows.push({ ...row, _t: t, _mast: [...mast] });
  }
  return rows;
}

/* -- The numbers the engine would compute ----------------------------------------------------- */
const NEEDED = 10, WINDOW = 20, BASE_N = 5;

function retentionTrials(rows) {
  // For each teaching event, the first occurrence of that skill 3 or more days later: a trial; unaided means success.
  const out = [];
  for (const sk of new Set(rows.map((r) => r.skill))) {
    const mine = rows.filter((r) => r.skill === sk);
    for (const tr of mine.filter((r) => r.taught)) {
      const after = mine.find((r) => r._t >= tr._t + 3 * DAY);
      if (after) out.push(after.outcome === "clean");
    }
  }
  return out;
}

function analyse(rows, seed, skill, allSkillRows) {
  const rnd = mulberry32(seed);
  const mine = skill ? rows.filter((r) => r.skill === skill) : rows;
  const n = mine.length;
  const unaided = (r) => r.outcome === "clean";
  const ready = n >= NEEDED;
  const tierOf = (r) => (r.tier ?? 0);
  // curve: sliding window ending at each occurrence from NEEDED
  const curve = [];
  if (ready) {
    for (let i = NEEDED; i <= n; i++) {
      const win = mine.slice(Math.max(0, i - WINDOW), i);
      const k = win.filter(unaided).length;
      const [lo, hi] = wilson(k, win.length);
      const tiers = [0, 0, 0, 0, 0];
      win.forEach((r) => { tiers[tierOf(r)]++; });
      const levels = skill ? [mine[i - 1].level_after] : null;
      let level;
      if (skill) level = levels[0];
      else {
        const latest = {};
        rows.slice(0, rows.indexOf(mine[i - 1]) + 1).forEach((r) => { latest[r.skill] = r.level_after; });
        const v = Object.values(latest);
        level = Math.round(mean(v));
      }
      curve.push({ i, t_hour: mine[i - 1].t_hour, independence: r3(k / win.length), lo: r3(lo), hi: r3(hi), n: win.length, level, tiers });
    }
  }
  const baseRows = mine.slice(0, BASE_N);
  const baseline = n >= BASE_N ? (() => { const k = baseRows.filter(unaided).length; return { k, n: BASE_N, share: r3(k / BASE_N), wilson: wilson(k, BASE_N).map(r3) }; })() : null;
  const lastWin = mine.slice(Math.max(0, n - WINDOW));
  const kLast = lastWin.filter(unaided).length;
  const wLast = wilson(kLast, lastWin.length);
  const independence = n ? { k: kLast, n: lastWin.length, share: r3(kLast / lastWin.length), wilson: wLast.map(r3), lower: r3(wLast[0]) } : null;

  // mastery: replay to now (the generator kept a running vector), decayed to as_of
  const lastRow = mine.at(-1);
  const masteryNow = (si) => {
    const sk = SKILLS[si].id;
    const lr = [...rows].reverse().find((r) => r.skill === sk);
    if (!lr) return null;
    return lr._mast[si] * Math.exp(-((AS_OF_MS - lr._t) / DAY) / 60);
  };
  const bySkillMastery = {};
  SKILLS.forEach((s, si) => { const m = masteryNow(si); if (m != null) bySkillMastery[s.id] = r3(m); });
  const mastery = n ? (skill ? bySkillMastery[skill] ?? null : r3(mean(Object.values(bySkillMastery)))) : null;

  // gap closure: first 5 vs last 5 seconds lost against the pack's expert median
  let gap = null;
  if (n >= 2 * BASE_N) {
    const f = mine.slice(0, BASE_N).map((r) => r.lost_s), l = mine.slice(-BASE_N).map((r) => r.lost_s);
    const clos = (a, b) => (mean(a) - mean(b)) / mean(a);
    const bs = [];
    for (let b = 0; b < 600; b++) {
      const fa = f.map(() => f[(rnd() * f.length) | 0]), la = l.map(() => l[(rnd() * l.length) | 0]);
      bs.push(clos(fa, la));
    }
    gap = { value: r3(clos(f, l)), first5_lost_s: r1(mean(f)), last5_lost_s: r1(mean(l)), ci: [r3(quant(bs, 0.025)), r3(quant(bs, 0.975))], n_first: BASE_N, n_last: BASE_N };
  }
  // retention
  const trials = retentionTrials(mine);
  const retention = trials.length
    ? { value: r3(trials.filter(Boolean).length / trials.length), k: trials.filter(Boolean).length, n: trials.length, wilson: wilson(trials.filter(Boolean).length, trials.length).map(r3) }
    : { value: null, k: 0, n: 0, wilson: null };

  // trend: assisted share per block, Theil-Sen slope per 10 occurrences, bootstrap interval
  const B = 10; // non-overlapping blocks of 10, as the engine does
  const blocks = [];
  for (let s = 0; s + B <= n; s += B) {
    const seg = mine.slice(s, s + B);
    blocks.push({ i: s + B, n: B, assisted_share: r3(seg.filter((r) => !unaided(r)).length / B) });
  }
  const xs = blocks.map((b) => (b.i / 10)), ys = blocks.map((b) => b.assisted_share);
  let trend;
  if (!ready || blocks.length < 3) trend = { slope_per_10: null, ci: null, direction: "too_early", blocks, needed_more: Math.max(0, 30 - n) || null, power_note: `A trend needs 30 occurrences (three blocks of 10); there are ${n} so far.` };
  else {
    const slope = theilSen(xs, ys);
    const bs = [];
    // bootstrap over occurrences inside each block, so the interval reflects the sampling noise of the shares
    const blockRows = blocks.map((b) => mine.slice(b.i - B, b.i).map((r) => (unaided(r) ? 0 : 1)));
    for (let b = 0; b < 500; b++) {
      const yb = blockRows.map((bl) => mean(bl.map(() => bl[(rnd() * bl.length) | 0])));
      const s = theilSen(xs, yb);
      if (s != null) bs.push(s);
    }
    const ci = [quant(bs, 0.025), quant(bs, 0.975)];
    const dir = ci[1] < 0 ? "less_help" : ci[0] > 0 ? "more_help" : "steady";
    trend = { slope_per_10: r3(slope), ci: ci.map(r3), direction: dir, blocks, needed_more: null, power_note: dir === "steady" ? "Cannot tell yet: with this many occurrences a real fall in help need is often missed, so this is not evidence of no change." : null };
  }

  // time to progress after a cue
  const cued = mine.filter((r) => r.seconds_to_progress != null);
  const ttp = cued.length >= 3 ? (() => {
    const v = cued.map((r) => r.seconds_to_progress);
    const bs = [];
    for (let b = 0; b < 500; b++) bs.push(median(v.map(() => v[(rnd() * v.length) | 0])));
    return { median_s: r1(median(v)), ci: [r1(quant(bs, 0.025)), r1(quant(bs, 0.975))], n: v.length };
  })() : null;

  // composite
  const W = { independence_lb: 0.4, mastery: 0.3, gap_closure: 0.2, retention: 0.1 };
  let composite = null, composite_ci = null, partial = false, avail = 1, used = null;
  if (ready) {
    const parts = {
      independence_lb: [independence.lower, independence.lower, independence.wilson[1]],
      mastery: [mastery, Math.max(0, mastery - 0.06), Math.min(1, mastery + 0.06)],
      gap_closure: gap ? [Math.max(0, gap.value), Math.max(0, gap.ci[0]), Math.max(0, gap.ci[1])] : null,
      retention: retention.value != null ? [retention.value, retention.wilson[0], retention.wilson[1]] : null,
    };
    const have = Object.keys(parts).filter((k) => parts[k]);
    avail = have.reduce((a, k) => a + W[k], 0);
    partial = have.length < 4;
    used = Object.fromEntries(Object.keys(W).map((k) => [k, parts[k] ? r3(W[k] / avail) : 0]));
    const comp = (j) => 100 * have.reduce((a, k) => a + (W[k] / avail) * parts[k][j], 0);
    composite = Math.round(comp(0)); composite_ci = [Math.round(comp(1)), Math.round(comp(2))];
    if (composite < composite_ci[0]) composite_ci[0] = composite;
    if (composite > composite_ci[1]) composite_ci[1] = composite;
  }

  // per-skill rows always cover every skill that has occurrences
  const by_skill = SKILLS.map((s) => {
    const sr = allSkillRows.filter((r) => r.skill === s.id);
    if (!sr.length) return null;
    const a = analyseLite(sr, seed + s.id.length);
    return a ? { skill: s.id, label: s.label, name: s.name, ...a } : null;
  }).filter(Boolean);

  const ofd = (stream) => rows.filter((r) => r.stream === stream).length;
  return {
    person: mine[0]?.person ?? rows[0]?.person, skill: skill ?? null, window: WINDOW,
    origin_detail: rows[0]?.origin_detail,
    readiness: { occurrences: n, needed: NEEDED, ready, trend_needed: 30 },
    baseline,
    score: { composite_experimental: composite, composite_experimental_ci: composite_ci, composite_partial: partial, available_weight: r3(avail), weights: W, used_weights: partial ? used : null, weights_note: "Stated assumptions, not fitted.", composite_caveat: "Experimental. On generated learners whose skill did not change, this score still rose in a sizeable share of cases, so it is shown with its parts and is not a finding." },
    components: { independence, mastery: n ? { value: mastery, by_skill: bySkillMastery } : null, gap_closure: gap, retention },
    trend, curve,
    occurrences: { total: n, unaided: mine.filter(unaided).length, assisted: mine.filter((r) => r.outcome === "assisted").length, errors: mine.filter((r) => r.outcome === "error").length, abandoned: mine.filter((r) => r.outcome === "abandoned").length },
    time_to_progress: ttp ? { after_cue: ttp, no_cue: null } : null,
    by_skill,
    _lastRow: lastRow,
  };
}

// Per-skill figures for the row list (the skill's own occurrences only).
function analyseLite(sr, seed) {
  const a = analyse(sr, seed, sr[0].skill, []);
  const n = sr.length;
  const unaided = sr.filter((r) => r.outcome === "clean").length;
  const lastRow = sr.at(-1);
  const lastGapDays = (AS_OF_MS - lastRow._t) / DAY;
  const mastery = a.components.mastery?.value ?? null;
  const recent = (arr) => ({ n: arr.length, assisted: arr.filter((r) => r.outcome !== "clean").length });
  return {
    n, independent: unaided, assisted: sr.filter((r) => r.outcome === "assisted").length,
    independence_lower: a.components.independence?.lower ?? null,
    mastery, level: lastRow.level_after, direction: a.trend.direction,
    first10: n >= 20 ? recent(sr.slice(0, 10)) : null,
    last10: n >= 20 ? recent(sr.slice(-10)) : null,
    time_to_progress: a.time_to_progress,
    retention: a.components.retention.n ? a.components.retention : { value: null, k: 0, n: 0, wilson: null },
    retrieval_due: lastRow.level_after >= 3 && lastGapDays >= 3,
  };
}

function bundle(story, spec, label) {
  const rows = simulate(spec);
  const meta = (n) => ({ origin: "synthetic", n, n_unit: "occurrences", split: `sliding window of ${WINDOW} occurrences`, interval_level: 0.95, note: `Example data: ${spec.note}`, generated_at: AS_OF });
  const finish = (a, off) => {
    const { _lastRow, ...rest } = a;
    // FIXTURE PLACEHOLDER: the engine states needed_more from its own power simulation. Here a fixed figure lets the screen show how
    // "cannot tell yet" reads with a number. It is not a measurement.
    if (spec.needMore && rest.trend.direction === "steady") {
      rest.trend.needed_more = spec.needMore;
      rest.trend.power_note = `Cannot tell yet: about ${spec.needMore} more occurrences would usually be needed to see a fall of 0.3 in the share that needed help. This is not evidence of no change.`;
    }
    return { meta: meta(rest.occurrences.total), data: { ...rest, offloaded: off } };
  };
  const delegated = spec.delegated.map((d, i) => ({ stream: "delegated", day: d.day, skill: d.skill, outcome: d.outcome, i }));
  const automation = spec.automation.map((d, i) => ({ stream: "automation", day: d.day, skill: d.skill, outcome: d.outcome, i }));
  const offRows = [...delegated, ...automation].map((d, k) => ({
    id: `${d.stream[0]}_${spec.person.slice(-6)}_${String(k + 1).padStart(3, "0")}`, person: spec.person, origin: "synthetic",
    t_hour: new Date(spec.t0 + d.day * DAY + (d.stream === "automation" ? 2 : 11 + (k % 5)) * 3600000).toISOString().slice(0, 13),
    role: "benefits-processor", skill: d.skill, step: STEPS[d.skill], stream: d.stream, trigger: "none", stuck_bucket: null, tier: 0, options_shown: 0,
    answer_id: null, accepted: false, dismissed: false, seconds_to_progress: null, lost_s: null, outcome: d.outcome, level_before: null, level_after: null,
    taught: false, retrieval: false, origin_detail: spec.origin_detail,
  }));
  const by = {};
  offRows.forEach((r) => { by[r.skill] = (by[r.skill] ?? 0) + 1; });
  const off = { delegated: delegated.length, automation: automation.length, by_skill: by, note: "Work the agent did for you. It never changes the score." };

  const overall = finish(analyse(rows, spec.seed + 1, null, rows), off);
  const skills = {};
  SKILLS.forEach((s, si) => {
    if (!rows.some((r) => r.skill === s.id)) return;
    skills[s.id] = finish(analyse(rows, spec.seed + 10 + si, s.id, rows), { ...off, delegated: offRows.filter((r) => r.stream === "delegated" && r.skill === s.id).length, automation: offRows.filter((r) => r.stream === "automation" && r.skill === s.id).length });
  });
  const clean = ({ _t, _mast, ...r }) => r;
  const ledgerRows = [...rows.map(clean), ...offRows].sort((a, b) => (a.t_hour < b.t_hour ? 1 : a.t_hour > b.t_hour ? -1 : a.id < b.id ? 1 : -1));
  const ledger = {
    meta: meta(rows.length),
    data: { rows: ledgerRows, counts: { assist: rows.length, delegated: delegated.length, automation: automation.length }, offloaded: { delegated: delegated.length, automation: automation.length } },
  };
  return { story, label, person: spec.person, role: "benefits-processor", overall, skills, ledger };
}

/* -- Three stories ---------------------------------------------------------------------------- */
const T0 = Date.parse("2026-09-26T00:00:00Z");

const improves = bundle("improves", {
  person: "p_example_improves", seed: 20261107, t0: T0, origin_detail: "synthetic_learner",
  note: "a generated learner with a planted learning curve, 6 weeks.",
  perSkill: [
    { n: 34, start: 0.9, floor: 0.06, ramp: 22, from: 0, to: 41 },
    { n: 38, start: 0.9, floor: 0.08, ramp: 26, from: 3, to: 41 },
    { n: 30, start: 0.92, floor: 0.1, ramp: 22, from: 8, to: 41 },
    { n: 26, start: 0.9, floor: 0.12, ramp: 20, from: 13, to: 41 },
    { n: 22, start: 0.86, floor: 0.34, ramp: 30, from: 18, to: 41 },
  ],
  delegated: [{ day: 31, skill: "enter-household-once", outcome: "clean" }, { day: 36, skill: "note-with-evidence", outcome: "clean" }, { day: 39, skill: "enter-household-once", outcome: "clean" }, { day: 40, skill: "reconcile-before-noting", outcome: "error" }],
  automation: Array.from({ length: 13 }, (_, i) => ({ day: 27 + i, skill: i % 3 === 0 ? "enter-household-once" : i % 3 === 1 ? "reconcile-before-noting" : "note-with-evidence", outcome: i === 5 ? "abandoned" : "clean" })),
}, "A learner who improves");

const plateau = bundle("plateau", {
  person: "p_example_plateau", seed: 77031, t0: T0, origin_detail: "simulated_participants", needMore: 60,
  note: "a language-model participant whose help need levels off, 6 weeks.",
  perSkill: [
    { n: 30, start: 0.84, floor: 0.34, tau: 7, from: 0, to: 41 },
    { n: 32, start: 0.82, floor: 0.58, tau: 8, from: 2, to: 41 },
    { n: 30, start: 0.8, floor: 0.7, tau: 5, from: 7, to: 41 },
    { n: 26, start: 0.78, floor: 0.46, tau: 9, from: 12, to: 41 },
    { n: 22, start: 0.8, floor: 0.5, tau: 8, from: 17, to: 41 },
  ],
  delegated: [{ day: 35, skill: "note-with-evidence", outcome: "clean" }],
  automation: Array.from({ length: 6 }, (_, i) => ({ day: 34 + i, skill: "reconcile-before-noting", outcome: i === 2 ? "failed" : "clean" })).map((x) => ({ ...x, outcome: x.outcome === "failed" ? "error" : x.outcome })),
}, "A learner whose help need levels off");

const sparse = bundle("sparse", {
  person: "p_example_new", seed: 4141, t0: T0, origin_detail: "synthetic_learner",
  note: "a generated learner on day 3 of using the system.",
  perSkill: [
    { n: 3, start: 0.8, floor: 0.8, tau: 5, from: 40, to: 42, script: ["assisted", "assisted", "clean"] },
    { n: 2, start: 0.8, floor: 0.8, tau: 5, from: 41, to: 43, script: ["assisted", "assisted"] },
    { n: 1, start: 0.8, floor: 0.8, tau: 5, from: 42, to: 43, script: ["assisted"] },
    { n: 0 }, { n: 0 },
  ],
  delegated: [{ day: 42, skill: "enter-household-once", outcome: "clean" }],
  automation: [],
}, "A learner with little data");

const getting = bundle("getting-going", {
  person: "p_example_going", seed: 9091, t0: T0, origin_detail: "synthetic_learner",
  note: "a generated learner with 20 occurrences: enough for a curve, not yet for a trend.",
  perSkill: [
    { n: 9, start: 0.85, floor: 0.3, ramp: 14, from: 28, to: 42 },
    { n: 7, start: 0.85, floor: 0.35, ramp: 12, from: 30, to: 42 },
    { n: 4, start: 0.85, floor: 0.5, ramp: 10, from: 36, to: 42 },
    { n: 0 }, { n: 0 },
  ],
  delegated: [{ day: 40, skill: "enter-household-once", outcome: "clean" }],
  automation: [{ day: 40, skill: "reconcile-before-noting", outcome: "clean" }, { day: 41, skill: "reconcile-before-noting", outcome: "clean" }],
}, "A learner with an early curve");

out("growth.json", improves);
out("growth-going.json", getting);
out("growth-plateau.json", plateau);
out("growth-sparse.json", sparse);
for (const b of [improves, plateau, getting, sparse]) {
  const o = b.overall.data;
  console.log(b.story, "n", o.occurrences.total, "base", JSON.stringify(o.baseline), "indep", JSON.stringify(o.components.independence), "trend", o.trend.direction, o.trend.slope_per_10, JSON.stringify(o.trend.ci), "composite", o.score.composite_experimental, JSON.stringify(o.score.composite_experimental_ci), "partial", o.score.composite_partial, "ret", JSON.stringify(o.components.retention), "gap", JSON.stringify(o.components.gap_closure), "ttp", JSON.stringify(o.time_to_progress));
  console.log("  skills:", o.by_skill.map((s) => `${s.skill}:${s.n}/${s.independent}/L${s.level}/${s.direction}/${s.retrieval_due ? "due" : "-"}`).join(" "));
}
