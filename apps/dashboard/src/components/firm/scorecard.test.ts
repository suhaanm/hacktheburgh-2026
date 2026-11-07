import { describe, expect, it } from "vitest";
import report from "../../fixtures/eval-report.json";
import exampleV2 from "../../fixtures/predictions-mlv2.json";
import {
  CLOSE_POINTS, THIN_N, baselineLine, binReadout, budgetVerdict, budgetWords, estFrom, estOf, gapOf, pair, readBins, readScorecard, relate,
  reliabilityLine, summariseBins, verdictWord, wilson, type Bin, type Scorecard,
} from "./scorecard";

const ready = (r: ReturnType<typeof readScorecard>): Scorecard => {
  if (r.kind !== "ready") throw new Error(`not ready: ${r.reason}`);
  return r.card;
};
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T;

describe("wilson", () => {
  it("matches known values", () => {
    const [lo, hi] = wilson(0.5, 10) as [number, number];
    expect(lo).toBeCloseTo(0.2366, 3);
    expect(hi).toBeCloseTo(0.7634, 3);
    const [l0, h0] = wilson(0, 10) as [number, number];
    expect(l0).toBe(0);
    expect(h0).toBeCloseTo(0.2775, 3);
    const [l1, h1] = wilson(1, 10) as [number, number];
    expect(l1).toBeCloseTo(0.7225, 3);
    expect(h1).toBe(1);
  });
  it("narrows as n grows and has no answer for no cases", () => {
    const a = wilson(0.4, 20) as [number, number];
    const b = wilson(0.4, 2000) as [number, number];
    expect(b[1] - b[0]).toBeLessThan(a[1] - a[0]);
    expect(wilson(0.4, 0)).toBeNull();
    expect(wilson(Number.NaN, 10)).toBeNull();
  });
});

describe("reading estimates", () => {
  it("takes {value, ci}, {value, interval}, {point, lo, hi} and bare numbers", () => {
    expect(estOf({ value: 1, ci: [0.5, 2] })).toEqual({ value: 1, ci: [0.5, 2] });
    expect(estOf({ value: 1, interval: [2, 0.5] })).toEqual({ value: 1, ci: [0.5, 2] });
    expect(estOf({ point: 3, lo: 2, hi: 4 })).toEqual({ value: 3, ci: [2, 4] });
    expect(estOf(0.7)).toEqual({ value: 0.7, ci: null });
    expect(estOf(null)).toBeNull();
    expect(estOf({ nothing: 1 })).toBeNull();
  });
  it("reads a bare number with a sibling interval, and never invents one", () => {
    expect(estFrom({ x: 1.2, x_ci: [0.9, 1.5] }, "x")).toEqual({ value: 1.2, ci: [0.9, 1.5] });
    expect(estFrom({ ci_x: [0.9, 1.5], x: 1.2 }, "x")).toEqual({ value: 1.2, ci: [0.9, 1.5] });
    expect(estFrom({ x: 1.2 }, "x")).toEqual({ value: 1.2, ci: null });
    expect(estFrom({ x: 1.2, x_ci: "wide" }, "x")?.ci).toBeNull();
    expect(pair([1])).toBeNull();
  });
});

describe("calibration bins", () => {
  it("v1: lo and hi are bin edges, so the interval is a Wilson interval from the count", () => {
    const bins = readBins([{ p_mean: 0.65, freq: 0.55, n: 132, lo: 0.6, hi: 0.7 }], false);
    expect(bins[0].edge).toEqual([0.6, 0.7]);
    const w = wilson(0.55, 132) as [number, number];
    expect(bins[0].ci?.[0]).toBeCloseTo(w[0], 6);
    expect(bins[0].ci?.[1]).toBeCloseTo(w[1], 6);
  });
  it("mlv2: lo and hi are the report's own interval on the observed share", () => {
    const bins = readBins([{ p_mean: 0.3, freq: 0.31, n: 400, lo: 0.27, hi: 0.35 }], true);
    expect(bins[0].ci).toEqual([0.27, 0.35]);
    expect(bins[0].edge).toBeNull();
  });
  it("mlv2: an interval that does not hold the estimate is not trusted, a Wilson one replaces it", () => {
    const bins = readBins([{ p_mean: 0.3, freq: 0.31, n: 400, lo: 0.4, hi: 0.5 }], true);
    expect(bins[0].ci).toEqual(wilson(0.31, 400));
  });
  it("marks a bin thin below the threshold, drops empty bins and sorts by forecast", () => {
    const bins = readBins([
      { p_mean: 0.9, freq: 0.5, n: THIN_N - 1 },
      { p_mean: 0.1, freq: 0.1, n: THIN_N },
      { p_mean: 0.5, freq: 0.5, n: 0 },
      { p_mean: "x", freq: 0.5, n: 50 },
    ], false);
    expect(bins.map((b) => b.p)).toEqual([0.1, 0.9]);
    expect(bins.map((b) => b.thin)).toEqual([false, true]);
  });
  it("calls a gap close within the stated number of points, otherwise high or low", () => {
    expect(gapOf({ p: 0.5, freq: 0.5 + CLOSE_POINTS })).toBe("close");
    expect(gapOf({ p: 0.5, freq: 0.5 + CLOSE_POINTS + 0.01 })).toBe("runs_low");
    expect(gapOf({ p: 0.65, freq: 0.545 })).toBe("runs_high");
  });
  it("summarises: which bins are close, and where the forecast runs high", () => {
    const bins: Bin[] = readBins([
      { p_mean: 0.1, freq: 0.1, n: 500 }, { p_mean: 0.3, freq: 0.32, n: 400 }, { p_mean: 0.65, freq: 0.5, n: 100 }, { p_mean: 0.95, freq: 0.5, n: 4 },
    ], false);
    const s = summariseBins(bins);
    expect(s).toMatchObject({ total: 4, thin: 1, reliable: 3, close: 2, highFrom: 0.65, lowFrom: null });
    const line = reliabilityLine(s);
    expect(line).toContain("2 of 3 bands");
    expect(line).toContain("From about 65% up it runs high");
  });
  it("says so when no bin has enough cases or there are no bins", () => {
    expect(reliabilityLine(summariseBins([]))).toMatch(/no forecast bins/i);
    expect(reliabilityLine(summariseBins(readBins([{ p_mean: 0.4, freq: 0.4, n: 5 }], false)))).toMatch(/fewer than 30/);
  });
  it("reads one bin aloud with its interval and a thin warning", () => {
    const [b] = readBins([{ p_mean: 0.65, freq: 0.545, n: 20 }], false);
    const t = binReadout(b, 95);
    expect(t).toContain("Forecast about 65%");
    expect(t).toContain("55% of 20 cases");
    expect(t).toContain("95% interval");
    expect(t).toContain("runs high");
    expect(t).toContain("Only 20 cases");
  });
});

describe("budget verdict", () => {
  it("over or within by the point estimate, and whether the interval agrees", () => {
    expect(budgetVerdict({ value: 1.21, ci: [0.95, 1.48] }, 1)).toEqual({ verdict: "over", certain: false });
    expect(budgetVerdict({ value: 1.5, ci: [1.2, 1.8] }, 1)).toEqual({ verdict: "over", certain: true });
    expect(budgetVerdict({ value: 0.8, ci: [0.6, 0.95] }, 1)).toEqual({ verdict: "within", certain: true });
    expect(budgetVerdict({ value: 0.95, ci: [0.8, 1.12] }, 1)).toEqual({ verdict: "within", certain: false });
    expect(budgetVerdict({ value: 0.95, ci: null }, 1)).toEqual({ verdict: "within", certain: null });
    expect(budgetVerdict(null, 1).verdict).toBe("unknown");
    expect(budgetVerdict({ value: 1, ci: null }, null).verdict).toBe("unknown");
  });
  it("puts the words in plain terms", () => {
    const w = budgetWords({ rate: { value: 1.21, ci: [0.95, 1.48] }, budget: 1, verdict: "over", certain: false, detection: null });
    expect(w.title).toBe("Over budget");
    expect(w.detail).toMatch(/reaches the budget/);
    expect(budgetWords({ rate: null, budget: null, verdict: "unknown", certain: null, detection: null }).title).toMatch(/No budget/);
  });
});

describe("relate", () => {
  it("lower and clearly lower, from intervals; no claim without them", () => {
    expect(relate({ value: 0.43, ci: [0.42, 0.45] }, { value: 0.51, ci: [0.5, 0.52] })).toEqual({ lower: true, clear: true });
    expect(relate({ value: 0.43, ci: [0.42, 0.51] }, { value: 0.5, ci: [0.5, 0.52] })).toEqual({ lower: true, clear: false });
    expect(relate({ value: 0.43, ci: null }, { value: 0.5, ci: [0.5, 0.52] })).toEqual({ lower: true, clear: null });
    expect(relate(null, { value: 0.5, ci: null })).toEqual({ lower: null, clear: null });
  });
});

describe("reading the v1 hazard section", () => {
  const card = ready(readScorecard(report));
  it("uses the hazard section when there is no v2 scorecard", () => {
    expect(card.source).toBe("hazard");
    expect(card.version).toBe("v1");
    expect(card.accepted).toBeNull();
    expect(card.defaultNote).toBeNull();
    expect(card.meta.n).toBe(4);
    expect(card.meta.nUnit).toBe("people");
    expect(card.meta.origin).toBe("synthetic");
  });
  it("carries 10 calibration bins with Wilson intervals and flags the thin ones", () => {
    expect(card.bins).toHaveLength(10);
    expect(card.bins.every((b) => b.ci !== null)).toBe(true);
    expect(card.bins.filter((b) => b.thin).map((b) => b.n)).toEqual([12, 4]);
    expect(card.bins[0].edge).toEqual([0, 0.1]);
  });
  it("compares ours with both baselines on log loss and Brier, all with intervals from the report", () => {
    const ll = card.panels.find((p) => p.key === "log_loss");
    expect(ll?.rows.map((r) => r.id)).toEqual(["ours", "time_since_progress", "base_rate"]);
    expect(ll?.rows[0].est?.value).toBeCloseTo(0.4364, 3);
    expect(ll?.rows[0].est?.ci?.[0]).toBeCloseTo(0.4224, 3);
    expect(ll?.rows[2].est?.value).toBeCloseTo(0.5095, 3);
    expect(baselineLine(card.panels)).toContain("Ours is lower than both baselines");
    // the v1 report gives intervals for log loss in every row, but none for the Brier baselines
    expect(baselineLine(card.panels)).toContain("for log loss the intervals do not overlap");
    expect(baselineLine(card.panels)).toContain("for brier score the report gives no interval for a baseline");
    expect(card.panels.find((p) => p.key === "brier")?.rows.map((r) => r.est?.ci === null)).toEqual([false, true, true]);
  });
  it("derives the budget verdict itself: about 1.2 an hour against 1.0 is over, and the interval reaches the budget", () => {
    expect(card.alarms.budget).toBe(1);
    expect(card.alarms.rate?.value).toBeCloseTo(1.2116, 3);
    expect(card.alarms.verdict).toBe("over");
    expect(card.alarms.certain).toBe(false);
    expect(card.alarms.detection?.value).toBeCloseTo(0.3289, 3);
    expect(card.alarms.detection?.ci?.[0]).toBeCloseTo(0.275, 3);
  });
  it("has no time-to-progress head, says why Models v2 is missing, and lists the engine's caveats and hazard limits", () => {
    expect(card.tte).toBeNull();
    expect(card.candidate).toBeNull();
    expect(card.v2Status?.status).toBe("pending");
    expect(card.caveats.length).toBeGreaterThan(0);
    expect(card.limits.length).toBeGreaterThan(0);
    expect(card.limits.every((t) => typeof t === "string" && t.length > 0)).toBe(true);
  });
  it("lists the four personas (n = 4) without ranking them", () => {
    expect(card.perPerson.map((p) => p.label)).toEqual(["irregular", "nightowl", "ninetofive", "shiftwkr"].filter((l) => card.perPerson.some((p) => p.label === l)));
  });
});

describe("reading an mlv2 scorecard that is not accepted", () => {
  const card = ready(readScorecard(report, exampleV2));
  it("keeps v1 as the default and says so in plain words", () => {
    expect(card.version).toBe("v1");
    expect(card.accepted).toBe(false);
    expect(card.verdict).toBe("not_run");
    expect(card.defaultNote).toBe("The v1 forecast stays the default. The v2 candidate has not been tested on held-out data yet.");
    expect(card.label).toBe("Our forecast (v1)");
    expect(verdictWord(card.verdict)).toBe("not tested yet");
  });
  it("draws v1's own bins and numbers, not the candidate's, on the main charts", () => {
    expect(card.meta.n).toBe(4);
    expect(card.panels[0].rows.find((r) => r.ours)?.est?.value).toBeCloseTo(0.4364, 3);
    expect(card.bins).toHaveLength(10);
  });
  it("keeps the candidate on its own pool with v1 scored on that same pool", () => {
    expect(card.candidate?.meta.n).toBe(16);
    expect(card.candidate?.meta.pool).toMatch(/not held-out/);
    expect(card.candidate?.logLoss.candidate?.value).toBeCloseTo(0.4349, 3);
    expect(card.candidate?.logLoss.v1?.value).toBeCloseTo(0.4386, 3);
    expect(card.candidate?.falseAlarms.candidate?.ci?.[1]).toBeCloseTo(1.1906, 3);
  });
  it("shows the time-to-progress head as a candidate that runs high", () => {
    expect(card.tte?.candidate).toBe(true);
    expect(card.tte?.cIndex?.value).toBeCloseTo(0.6966, 3);
    expect(card.tte?.baselineC?.value).toBeCloseTo(0.5293, 3);
    expect(card.tte?.pairs).toHaveLength(5);
    expect(card.tte?.meanExpected).toBeCloseTo(0.933, 2);
    expect(card.tte?.kmMean).toBeCloseTo(0.658, 2);
    expect(card.tte?.runsHigh).toBe(true);
  });
  it("keeps the v2 pool apart from v1's, so the time-to-progress footer names the right people", () => {
    expect(card.v2Meta?.n).toBe(16);
    expect(card.v2Meta?.pool).toMatch(/dev pool/);
    expect(card.meta.n).toBe(4);
  });
  it("covers the other verdict words", () => {
    for (const [v, text] of [["null", "did not beat v1"], ["harmful", "did worse than v1"], ["no_primary", "no frozen candidate"]] as const) {
      const b = clone(exampleV2) as Record<string, unknown>;
      b.verdict = v;
      const c = ready(readScorecard(report, b));
      expect(c.defaultNote).toContain(text);
    }
  });
  it("treats accepted:true with a contradicting verdict as not accepted", () => {
    const b = clone(exampleV2) as Record<string, unknown>;
    b.accepted = true;
    b.verdict = "null";
    expect(ready(readScorecard(report, b)).version).toBe("v1");
  });
});

describe("reading an mlv2 scorecard that is accepted", () => {
  const accepted = () => {
    const b = clone(exampleV2) as Record<string, unknown>;
    b.accepted = true;
    b.verdict = "accepted";
    b.calibration = [{ p_mean: 0.2, freq: 0.22, n: 900, lo: 0.19, hi: 0.25 }, { p_mean: 0.7, freq: 0.66, n: 80, lo: 0.55, hi: 0.76 }];
    b.calibration_source = "held-out replicates (single frozen run)";
    return b;
  };
  it("shows v2 as our forecast, with v1 as a fourth row, and its own bins and pool", () => {
    const c = ready(readScorecard(report, accepted()));
    expect(c.version).toBe("v2");
    expect(c.defaultNote).toBeNull();
    expect(c.candidate).toBeNull();
    expect(c.label).toBe("gradient boosting + Platt + personal prior shift");
    expect(c.panels[0].rows.map((r) => r.id)).toEqual(["ours", "v1", "time_since_progress", "base_rate"]);
    expect(c.bins.map((b) => b.ci)).toEqual([[0.19, 0.25], [0.55, 0.76]]);
    expect(c.binsLabel).toBe("held-out replicates (single frozen run)");
    expect(c.meta.n).toBe(16);
    expect(c.tte?.candidate).toBe(false);
  });
  it("reads ML2's wording of an acceptance ('accepted_by_both_tests') as accepted", () => {
    const b = accepted();
    b.verdict = "accepted_by_both_tests";
    const c = ready(readScorecard(report, b));
    expect(c.version).toBe("v2");
    expect(c.accepted).toBe(true);
    expect(c.verdict).toBe("accepted");
  });
});

describe("nulls and missing sections", () => {
  it("a report with no hazard and no scorecard is unavailable, with the reason from the stub", () => {
    const r = readScorecard({ sections: { hazard: { status: "pending", reason: "hazard not landed" } } });
    expect(r).toMatchObject({ kind: "unavailable", status: "pending", what: "The stuck forecast", reason: "hazard not landed" });
  });
  it("a missing section says to run make eval", () => {
    const r = readScorecard({ sections: {} });
    expect(r).toMatchObject({ kind: "unavailable", status: "missing" });
    expect((r as { reason: string }).reason).toMatch(/make eval/);
    expect(readScorecard(null).kind).toBe("unavailable");
    expect(readScorecard("nonsense").kind).toBe("unavailable");
  });
  it("a scorecard with null everywhere does not throw and never invents numbers or intervals", () => {
    const empty = { meta: null, accepted: false, verdict: null, model: null, baselines: { v1: { log_loss: 0.44 } }, calibration: [], tte: null, caveats: null };
    const c = ready(readScorecard({ sections: { mlv2: { scorecard: empty } } }));
    expect(c.bins).toEqual([]);
    expect(c.tte).toBeNull();
    expect(c.alarms.verdict).toBe("unknown");
    const ours = c.panels[0]?.rows.find((r) => r.ours)?.est;
    expect(ours).toEqual({ value: 0.44, ci: null });
    expect(c.meta.n).toBeNull();
  });
  it("a hazard section without intervals keeps them null", () => {
    const h = { meta: { origin: "synthetic", n: 4, n_unit: "people", interval_level: 0.95 }, model: { log_loss: 0.4, brier: 0.14 }, baselines: { base_rate: { log_loss: 0.5 }, time_since_progress: { log_loss: 0.5 } }, calibration: [], false_alarms_per_hour: 1.2, budget_false_alarms_per_hour: 1 };
    const c = ready(readScorecard({ sections: { hazard: h } }));
    expect(c.panels[0].rows.every((r) => r.est?.ci === null)).toBe(true);
    expect(c.alarms.rate).toEqual({ value: 1.2, ci: null });
    expect(c.alarms.certain).toBeNull();
    expect(baselineLine(c.panels)).toMatch(/no interval for a baseline/);
  });
  it("origin is read from the report: real data is not relabelled synthetic", () => {
    const h = clone(report) as { sections: { hazard: { meta: { origin: string } } } };
    h.sections.hazard.meta.origin = "real";
    expect(ready(readScorecard(h)).meta.origin).toBe("real");
  });
});

import { baselineShort } from "./scorecard";
describe("baselineShort", () => {
  it("is one short line, with the interval detail kept for a hint", () => {
    const c = ready(readScorecard(report));
    const b = baselineShort(c.panels);
    expect(b.line).toBe("Lower is better. Ours is lower on every measure shown.");
    expect(b.detail).toMatch(/^About the intervals: for log loss the intervals do not overlap/);
    expect(b.line.length).toBeLessThan(90);
  });
});
