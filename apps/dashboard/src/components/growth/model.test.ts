import { describe, expect, it } from "vitest";
import improves from "../../fixtures/growth.json";
import plateau from "../../fixtures/growth-plateau.json";
import sparse from "../../fixtures/growth-sparse.json";
import { emptyGrowth } from "../../fixtures/growth";
import {
  DIRECTION_WORD, buildView, cardsOf, change, claimOf, compositeOf, cueWeight, deleteCopy, deletedCount, directionOf, glyphOf, heroTitle, humanise,
  improvement, ledgerFields, marksOf, normalizeGrowth, offloadItems, originSentence, pct, pctBracket, pctRange, pickSamples, plural,
  recentSentence, remainingUntil, skillRows, statusOf, stillNeeded, timesWord, trendSentence, limitations,
} from "./model";
import type { LedgerRow, WireGrowth } from "./wire";

/** What the engine sends (the fixture files hold the raw answers). */
const wire = (x: unknown) => (x as { overall: { data: WireGrowth } }).overall.data;
/** What the screen works with: the same answers after normalisation (the composite under its internal name). */
const IMP = normalizeGrowth(wire(improves)), PLA = normalizeGrowth(wire(plateau)), SPA = normalizeGrowth(wire(sparse));
const wireOf = (x: unknown, skill: string) => normalizeGrowth((x as { skills: Record<string, { data: WireGrowth }> }).skills[skill].data);

describe("formatters", () => {
  it("uses a real minus sign and a plus for change", () => {
    expect(change(-3.14, 1)).toBe("−3.1");
    expect(change(4.4, 1)).toBe("+4.4");
    expect(change(0, 1)).toBe("0.0");
    expect(change(-0.01, 1)).toBe("0.0");
    expect(pct(0.847)).toBe("85%");
    expect(pctRange([0.436, 0.919])).toBe("44 to 92%");
    expect(pctBracket([0.04, 0.62])).toBe("[4, 62]%");
    expect(plural(1, "row")).toBe("1 row");
    expect(plural(3, "row")).toBe("3 rows");
    expect(timesWord(1)).toBe("1 time");
    expect(timesWord(7)).toBe("7 times");
  });
});

describe("status", () => {
  it("is empty with no occurrences, early below the engine's threshold, ready with a curve", () => {
    expect(statusOf(emptyGrowth("p", null, null).data)).toBe("empty");
    expect(statusOf(SPA)).toBe("early");
    expect(statusOf(IMP)).toBe("ready");
  });
  it("is early when ready is claimed but there is no curve to draw", () => {
    expect(statusOf({ ...IMP, curve: [] })).toBe("early");
  });
  it("falls back to a count threshold when readiness is missing", () => {
    const n = normalizeGrowth({ occurrences: { total: 4, unaided: 1, assisted: 3, errors: 0, abandoned: 0 } });
    expect(n.readiness).toEqual({ occurrences: 4, needed: 10, ready: false });
  });
  it("counts what is left until the curve starts", () => {
    expect(remainingUntil(6, 10)).toBe(4);
    expect(remainingUntil(12, 10)).toBe(0);
  });
});

describe("direction and trend", () => {
  it("flips the engine's assisted-share slope into improvement points per 10 occurrences", () => {
    const i = improvement({ slope_per_10: -0.05, ci: [-0.062, -0.029], direction: "less_help" });
    expect(i.per10).toBeCloseTo(5, 6);
    expect(i.ci![0]).toBeCloseTo(2.9, 6);
    expect(i.ci![1]).toBeCloseTo(6.2, 6);
    expect(improvement({ slope_per_10: null, ci: null, direction: "too_early" })).toEqual({ per10: null, ci: null });
  });
  it("words the trend from the interval, never claiming more than it shows", () => {
    expect(trendSentence({ slope_per_10: -0.05, ci: [-0.062, -0.029], direction: "less_help" })).toContain("5.0 points more");
    expect(trendSentence({ slope_per_10: -0.05, ci: [-0.062, -0.029], direction: "less_help" })).toContain("+2.9 to +6.2");
    expect(trendSentence({ slope_per_10: 0.04, ci: [0.01, 0.07], direction: "more_help" })).toContain("fewer");
    const steady = trendSentence({ slope_per_10: -0.017, ci: [-0.05, 0.011], direction: "steady" });
    expect(steady).toContain("Cannot tell yet");
    expect(steady).toContain("includes zero");
    expect(steady).toContain("not a finding that nothing is changing");
    expect(steady.toLowerCase()).not.toMatch(/no change|no clear change|levelled off|plateau/);
    expect(trendSentence({ slope_per_10: null, ci: null, direction: "too_early" })).toBe("Too early for a trend.");
  });
  it("maps the engine's first-draft words", () => {
    expect(directionOf("flat")).toBe("steady");
    expect(directionOf("unclear")).toBe("too_early");
    expect(directionOf(undefined)).toBe("too_early");
    expect(directionOf("less_help")).toBe("less_help");
  });
  it("titles the page without claiming expertise", () => {
    expect(heroTitle("ready", "less_help", null)).toBe("You need help less often than you did");
    expect(heroTitle("ready", "less_help", "the cliff check")).toBe("You need less help with the cliff check");
    expect(heroTitle("ready", "steady", null)).toBe("Cannot tell yet whether you need less help");
    expect(heroTitle("ready", "steady", "the cliff check")).toBe("Cannot tell yet whether you need less help with the cliff check");
    expect(heroTitle("ready", "more_help", null)).toContain("more help");
    expect(heroTitle("early", "less_help", null)).toContain("Too early");
    expect(heroTitle("empty", "too_early", null)).toBe("Not enough to show yet");
    for (const d of ["less_help", "steady", "more_help", "too_early"] as const) expect(heroTitle("ready", d, null).toLowerCase()).not.toMatch(/expert|master|proficient/);
  });
});

describe("copy from counts", () => {
  it("writes the first-10 versus last-10 sentence from the data", () => {
    expect(recentSentence("the cliff check", { n: 10, assisted: 7 }, { n: 10, assisted: 2 })).toBe("You needed help with the cliff check 7 times in your first 10 steps; in your last 10, 2.");
    expect(recentSentence(null, { n: 10, assisted: 1 }, { n: 10, assisted: 0 })).toBe("You needed help 1 time in your first 10 steps; in your last 10, 0.");
    expect(recentSentence("x", null, { n: 10, assisted: 0 })).toBeNull();
    expect(recentSentence("x", { n: 0, assisted: 0 }, { n: 10, assisted: 0 })).toBeNull();
  });
  it("builds every number in the lede from the response", () => {
    const v = buildView(IMP);
    expect(v.lede).toBe(`In your first ${IMP.baseline!.n} steps you finished ${IMP.baseline!.k} without a cue. In the latest ${IMP.components.independence!.n}, ${IMP.components.independence!.k}.`);
  });
});

describe("the fade", () => {
  it("summarises a window of tiers", () => {
    const w = cueWeight([10, 5, 3, 2, 0])!;
    expect(w.n).toBe(20);
    expect(w.cuedShare).toBeCloseTo(0.5, 6);
    expect(w.meanTier).toBeCloseTo(1.7, 6);
    expect(w.chipShare).toBeCloseTo(0.5, 6);
    expect(cueWeight([20, 0, 0, 0, 0])).toEqual({ n: 20, cuedShare: 0, meanTier: null, chipShare: null });
    expect(cueWeight(undefined)).toBeNull();
    expect(cueWeight([0, 0, 0, 0, 0])).toBeNull();
  });
  it("draws heavier cues thicker and rarer cues fainter, and no cue as a dot", () => {
    const heavy = glyphOf(cueWeight([0, 0, 0, 10, 10]))!;
    const light = glyphOf(cueWeight([0, 10, 0, 0, 0]))!;
    expect(heavy.stroke).toBeGreaterThan(light.stroke);
    const often = glyphOf(cueWeight([2, 18, 0, 0, 0]))!;
    const rare = glyphOf(cueWeight([18, 2, 0, 0, 0]))!;
    expect(often.opacity).toBeGreaterThan(rare.opacity);
    expect(glyphOf(cueWeight([20, 0, 0, 0, 0]))!.none).toBe(true);
    expect(glyphOf(cueWeight([0, 5, 5, 0, 0]))!.chip).toBe(true);
    expect(glyphOf(cueWeight([0, 9, 1, 0, 0]))!.chip).toBe(false);
    expect(glyphOf(null)).toBeNull();
  });
  it("gets lighter across the improving learner's curve (the point of the strip)", () => {
    const v = buildView(IMP);
    const first = glyphOf(v.curve[0].cue)!;
    const last = glyphOf(v.curve[v.curve.length - 1].cue)!;
    expect(last.opacity).toBeLessThan(first.opacity);
    expect(v.hasCueWeights).toBe(true);
  });
  it("picks sample points a minimum distance apart and always keeps the last", () => {
    const xs = Array.from({ length: 50 }, (_, i) => i * 4);
    const s = pickSamples(xs, 30);
    expect(s[s.length - 1]).toBe(49);
    for (let i = 1; i < s.length; i++) expect(xs[s[i]] - xs[s[i - 1]]).toBeGreaterThanOrEqual(30);
    expect(pickSamples([], 10)).toEqual([]);
    expect(pickSamples([5], 10)).toEqual([0]);
  });
});

describe("components in plain words", () => {
  it("returns the three cards with intervals", () => {
    const c = cardsOf(IMP);
    expect(c.map((x) => x.id)).toEqual(["help", "time", "keep"]);
    expect(c[0].title).toBe("Needs help less often");
    expect(c[1].title).toBe("Recovers faster");
    expect(c[2].title).toBe("Keeps it after a few days");
    for (const x of c) { expect(x.ci).not.toBeNull(); expect(x.value).not.toBeNull(); }
    expect(c[0].sentence).toContain(`${IMP.components.independence!.k} of ${IMP.components.independence!.n}`);
    expect(c[1].sentence).toContain(`${Math.round(IMP.components.gap_closure!.first5_lost_s!)} s`);
  });
  it("shows a missing retention as 'Not yet', never as zero", () => {
    const w = { ...IMP, components: { ...IMP.components, retention: { value: null, k: 0, n: 0, wilson: null } } };
    const keep = cardsOf(w)[2];
    expect(keep.display).toBe("Not yet");
    expect(keep.value).toBeNull();
    expect(keep.pending).toContain("3 or more days");
    expect(keep.display).not.toMatch(/0%/);
  });
  it("says so when more time is lost than at the start", () => {
    const w = { ...IMP, components: { ...IMP.components, gap_closure: { value: -0.2, first5_lost_s: 10, last5_lost_s: 12, ci: [-0.5, 0.1] as [number, number], n_first: 5, n_last: 5 } } };
    const t = cardsOf(w)[1];
    expect(t.sentence).toContain("more time lost than at the start");
    expect(t.scale[0]).toBeLessThan(0);
  });
});

describe("how many more occurrences", () => {
  it("uses the engine's own figure when it sends one", () => {
    expect(stillNeeded({ readiness: { occurrences: 60, needed: 10, ready: true }, trend: { ...IMP.trend, needed_more: 80 } })).toBe(80);
  });
  it("while a trend cannot be computed, counts what is left of trend_needed", () => {
    const early = { ...IMP.trend, direction: "too_early" as const, needed_more: null };
    expect(stillNeeded({ readiness: { occurrences: 14, needed: 10, ready: true, trend_needed: 30 }, trend: early })).toBe(16);
    expect(stillNeeded({ readiness: { occurrences: 150, needed: 10, ready: true, trend_needed: 30 }, trend: { ...IMP.trend, needed_more: null } })).toBe(0);
    expect(stillNeeded({ readiness: { occurrences: 6, needed: 10, ready: false }, trend: early })).toBe(0);
  });
  it("tells a worker with 10 to 29 occurrences what the trend needs", () => {
    const s = trendSentence({ slope_per_10: null, ci: null, direction: "too_early" }, 95, 16, 30, 14);
    expect(s).toBe("Too early for a trend. A trend needs 30 steps and you have 14.");
  });
  it("prints the engine's own sentence for a trend that cannot be computed yet, once", () => {
    const note = "A trend needs 30 occurrences (three blocks of 10); there are 14 so far.";
    const s = trendSentence({ slope_per_10: null, ci: null, direction: "too_early", power_note: note }, 95, 16, 30, 14);
    expect(s).toBe(`Too early for a trend. ${note}`);
  });
  it("puts the number, or the engine's own sentence, in the cannot-tell wording", () => {
    const steady = { slope_per_10: -0.017, ci: [-0.05, 0.011] as [number, number], direction: "steady" as const };
    expect(trendSentence(steady, 95, 30)).toContain("About 30 more steps would help.");
    expect(trendSentence(steady, 95, 0)).not.toContain("would help");
    const noted = trendSentence({ ...steady, power_note: "Plain engine note." }, 95, 30);
    expect(noted).toContain("Plain engine note.");
    expect(noted.startsWith("Cannot tell yet. ")).toBe(true);
    expect(noted).toContain("About 30 more steps would help.");
    // the engine's own sentence already says it, and already names the number: nothing is repeated
    const own = trendSentence({ ...steady, power_note: "Cannot tell yet: about 60 more occurrences would help." }, 95, 60);
    expect(own.match(/Cannot tell yet/g)).toHaveLength(1);
    expect(own.match(/60 more occurrences/g)).toHaveLength(1);
  });
  it("shows the steady skills as 'cannot tell yet' in the rows", () => {
    expect(DIRECTION_WORD.steady).toBe("cannot tell yet");
    expect(DIRECTION_WORD.less_help).toBe("needs less help");
  });
  it("says 'cannot tell yet' for the skills it cannot judge, and counts none as 'no change'", () => {
    const c = claimOf(skillRows(PLA.by_skill));
    expect(c).toContain("Needs less help on");
    expect(c).toContain("cannot tell yet");
    expect(c.toLowerCase()).not.toContain("no change");
  });
});

describe("the engine's claim", () => {
  it("is printed verbatim when the engine sends one, and derived from the rows otherwise", () => {
    const withClaim = buildView({ ...IMP, claim: "Engine claim text." });
    expect(withClaim.claim).toBe("Engine claim text.");
    expect(buildView({ ...IMP, claim: undefined }).claim).toMatch(/^Needs less help on/);
  });
});

describe("composite is experimental and never the headline", () => {
  it("carries the engine's caveat verbatim and is labelled experimental", () => {
    const w = { ...IMP, score: { ...IMP.score, composite_caveat: "Engine caveat text." } };
    const c = compositeOf(w)!;
    expect(c.experimental).toBe(true);
    expect(c.caveat).toBe("Engine caveat text.");
  });
  it("reads the composite under the engine's new names, or the earlier ones", () => {
    const base = { ...IMP.score, composite: null, composite_ci: null };
    const n = normalizeGrowth({ ...IMP, score: { ...base, composite_experimental: 61.5, composite_experimental_ci: [50, 70] } });
    expect(n.score.composite).toBe(61.5);
    expect(n.score.composite_ci).toEqual([50, 70]);
    const old = normalizeGrowth({ ...IMP, score: { ...IMP.score, composite: 58, composite_ci: [48, 66] } });
    expect(old.score.composite).toBe(58);
  });
  it("types no numbers of its own when the engine sends no caveat", () => {
    const c = compositeOf({ ...IMP, score: { ...IMP.score, composite_caveat: null } })!;
    expect(c.caveat).not.toMatch(/\d/);
    expect(c.caveat).toContain("Experimental");
  });
  it("puts independence now beside the trend as the headline pair", () => {
    const v = buildView(IMP);
    expect(v.independence).toEqual({ share: IMP.components.independence!.share, ci: IMP.components.independence!.wilson, k: IMP.components.independence!.k, n: IMP.components.independence!.n });
    expect(v.trend.per10).not.toBeNull();
  });
  it("prints the caveat among the limitations and says a zero-crossing interval is not evidence of no change", () => {
    const v = { ...buildView(IMP), caveat: "Engine caveat text." };
    const l = limitations(v, "synthetic").join(" ");
    expect(l).toContain("Engine caveat text.");
    expect(l).toContain("experimental");
    expect(l).toContain("not evidence of no change");
  });
});

describe("composite", () => {
  it("is withheld when the engine withholds it", () => {
    expect(compositeOf(SPA)).toBeNull();
    expect(buildView(SPA).composite).toBeNull();
  });
  it("carries its interval and all four parts", () => {
    const c = compositeOf(IMP)!;
    expect(c.value).toBe(wire(improves).score.composite_experimental);
    expect(c.ci).toEqual(wire(improves).score.composite_experimental_ci);
    expect(c.parts).toHaveLength(4);
    expect(c.parts.reduce((a, p) => a + p.weight, 0)).toBeCloseTo(1, 6);
  });
  it("re-weights and says so when a part does not exist yet", () => {
    const w: WireGrowth = { ...IMP, score: { ...IMP.score, composite_partial: true, available_weight: 0.9, used_weights: { independence_lb: 0.4 / 0.9, mastery: 0.3 / 0.9, gap_closure: 0.2 / 0.9, retention: 0 } }, components: { ...IMP.components, retention: { value: null, k: 0, n: 0, wilson: null } } };
    const c = compositeOf(w)!;
    expect(c.partial).toBe(true);
    expect(c.parts.find((p) => p.id === "ret")!.shown).toBe("not yet");
    expect(c.parts.reduce((a, p) => a + p.weight, 0)).toBeCloseTo(1, 6);
    expect(c.note).toContain("90%");
  });
});

describe("skill rows", () => {
  it("uses the pack's words and counts errors and stopped steps separately", () => {
    const rows = skillRows(IMP.by_skill);
    expect(rows).toHaveLength(IMP.by_skill.length);
    for (const r of rows) {
      expect(r.independent + r.assisted + r.other).toBe(r.n);
      expect(r.label.length).toBeGreaterThan(0);
    }
    expect(rows[0].label).toBe("Read the error message before retrying");
  });
  it("falls back to a readable name when the engine sends none", () => {
    expect(humanise("check-the-cliff")).toBe("Check the cliff");
    const r = skillRows([{ ...IMP.by_skill[0], label: "", name: "" }])[0];
    expect(r.label).toBe("Reads error first");
  });
  it("gives a time after a cue only when there are cues to time", () => {
    const rows = skillRows(SPA.by_skill);
    for (const r of rows) expect(r.ttp === null || r.ttp.n > 0).toBe(true);
    const none = skillRows([{ ...IMP.by_skill[0], time_to_progress: { after_cue: { median_s: null, ci: null, n: 0 }, no_cue: null } }])[0];
    expect(none.ttp).toBeNull();
  });
  it("counts the skills that need less help and never claims expertise", () => {
    const c = claimOf(skillRows(IMP.by_skill));
    expect(c).toMatch(/^Needs less help on \d of \d skills?/);
    expect(c).toContain("not a measure of expertise");
    expect(claimOf(skillRows(SPA.by_skill))).toBe("Too early to say for any skill.");
    expect(claimOf([])).toBe("");
  });
  it("writes each row's first-10 versus last-10 line from its own counts", () => {
    const row = skillRows(IMP.by_skill).find((r) => r.id === "check-the-cliff")!;
    const s = IMP.by_skill.find((x) => x.skill === "check-the-cliff")!;
    expect(row.recent).toContain(`${timesWord(s.first10!.assisted)} in your first 10`);
    expect(row.recent).toContain(`in your last 10, ${s.last10!.assisted}.`);
  });
});

describe("the three stories", () => {
  it("improves: ready, less help, composite with interval, fade lighter", () => {
    const v = buildView(IMP);
    expect(v.status).toBe("ready");
    expect(v.trend.direction).toBe("less_help");
    expect(v.title).toBe("You need help less often than you did");
    expect(v.composite!.ci).not.toBeNull();
    expect(v.cards).toHaveLength(3);
  });
  it("plateaus: ready, steady, and the page says it cannot tell yet and how many more would help, never 'no change'", () => {
    const v = buildView(PLA);
    expect(v.status).toBe("ready");
    expect(v.trend.direction).toBe("steady");
    expect(v.title).toBe("Cannot tell yet whether you need less help");
    expect(v.trend.sentence).toContain("includes zero");
    expect(v.trend.sentence).toContain("Cannot tell yet");
    expect(v.trend.stillNeeded).toBe(PLA.trend.needed_more);
    expect(v.trend.sentence).toContain(`${PLA.trend.needed_more} more occurrences`);
    expect(v.trend.sentence.toLowerCase()).not.toMatch(/no clear change|levelled off|has not changed|plateau/);
  });
  it("sparse: early, no curve, no composite, counts only", () => {
    const v = buildView(SPA);
    expect(v.status).toBe("early");
    expect(v.curve).toEqual([]);
    expect(v.composite).toBeNull();
    expect(v.trend.direction).toBe("too_early");
    expect(v.title).toContain("Too early");
    expect(v.total).toBe(6);
  });
  it("a focused skill speaks of that skill", () => {
    const w = wireOf(improves, "check-the-cliff");
    const v = buildView(w);
    expect(v.focusId).toBe("check-the-cliff");
    expect(v.focusName).toBe("the cliff check");
    expect(v.recentLine).toContain("the cliff check");
    expect(v.title).toContain("the cliff check");
  });
  it("empty: nothing to show", () => {
    const v = buildView(emptyGrowth("p", null, null).data);
    expect(v.status).toBe("empty");
    expect(v.title).toBe("Not enough to show yet");
    expect(v.skills).toEqual([]);
  });
});

describe("fixture invariants (the example data agrees with itself)", () => {
  for (const [name, fx] of [["improves", improves], ["plateau", plateau], ["sparse", sparse]] as const) {
    const all = [wire(fx), ...Object.values((fx as unknown as { skills: Record<string, { data: WireGrowth }> }).skills).map((s) => s.data)];
    it(`${name}: every curve point is a share inside its interval, with n and tiers that add up`, () => {
      for (const w of all) {
        for (const p of w.curve) {
          expect(p.lo).toBeLessThanOrEqual(p.independence + 1e-9);
          expect(p.hi).toBeGreaterThanOrEqual(p.independence - 1e-9);
          expect(p.n).toBeLessThanOrEqual(w.window);
          expect(p.tiers!.reduce((a, b) => a + b, 0)).toBe(p.n);
          expect(p.level == null || (p.level >= 1 && p.level <= 4)).toBe(true);
        }
        expect(w.occurrences.total).toBe(w.readiness.occurrences);
        expect(w.readiness.ready).toBe(w.readiness.occurrences >= w.readiness.needed);
        const comp = w.score.composite_experimental;
        if (comp != null) {
          expect(w.score.composite_experimental_ci![0]).toBeLessThanOrEqual(comp);
          expect(w.score.composite_experimental_ci![1]).toBeGreaterThanOrEqual(comp);
        }
        if (!w.readiness.ready) { expect(w.curve).toEqual([]); expect(comp ?? null).toBeNull(); expect(w.trend.direction).toBe("too_early"); }
        // a trend needs three blocks of 10, as the engine says
        if (w.readiness.occurrences < w.readiness.trend_needed!) expect(w.trend.direction).toBe("too_early");
      }
    });
    it(`${name}: ledger rows are enums and numbers only, with no free text`, () => {
      const rows = (fx as unknown as { ledger: { data: { rows: LedgerRow[] } } }).ledger.data.rows;
      expect(rows.length).toBeGreaterThan(0);
      for (const r of rows) for (const [k, v] of Object.entries(r)) if (typeof v === "string") expect(v, `${k}=${v}`).toMatch(/^[A-Za-z0-9_:\-]+$/);
      expect(new Set(rows.map((r) => r.stream)).has("assist")).toBe(true);
    });
  }
  it("improves: per-skill counts add up to the overall count", () => {
    expect(IMP.by_skill.reduce((a, s) => a + s.n, 0)).toBe(IMP.occurrences.total);
  });
});

describe("offloaded work", () => {
  const row = (o: Partial<LedgerRow>): LedgerRow => ({
    id: "x", person: "p", origin: "synthetic", t_hour: "2026-11-05T02", role: "r", skill: "s1", step: "st", stream: "automation", trigger: "none", stuck_bucket: null, tier: 0,
    options_shown: 0, answer_id: null, accepted: false, dismissed: false, seconds_to_progress: null, lost_s: null, outcome: "clean", level_before: null, level_after: null, taught: false, retrieval: false, ...o,
  });
  it("lists only delegated and automation rows, newest first, in plain words", () => {
    const items = offloadItems([row({ id: "a", stream: "assist" }), row({ id: "b", t_hour: "2026-11-04T02" }), row({ id: "c", stream: "delegated", t_hour: "2026-11-06T11", outcome: "error" })], (s) => `Skill ${s}`);
    expect(items.map((i) => i.id)).toEqual(["c", "b"]);
    expect(items[0]).toMatchObject({ streamWord: "You asked", outcome: "failed", what: "Skill s1", minutes: null });
    expect(items[1]).toMatchObject({ streamWord: "Overnight", outcome: "done" });
    expect(items[0].when).toBe("Fri 6 Nov, 11:00");
  });
  it("reads the engine's offload result, minutes and routine for runs done for the person", () => {
    const items = offloadItems([
      row({ id: "q", stream: "delegated", skill: null, routine: "calc-entry-3x", offload_outcome: "queued", minutes: 12.4, t_hour: "2026-11-06T11" }),
      row({ id: "y", stream: "automation", offload_outcome: "yielded", minutes: 0, t_hour: "2026-11-05T02" }),
    ], (s) => `Skill ${s}`);
    expect(items[0]).toMatchObject({ what: "Calc entry 3x", outcome: "waiting for your approval", minutes: 12.4 });
    expect(items[1]).toMatchObject({ what: "Skill s1", outcome: "paused for you", minutes: null });
  });
  it("respects the limit", () => {
    const rows = Array.from({ length: 12 }, (_, i) => row({ id: `r${i}`, t_hour: `2026-11-0${(i % 9) + 1}T02` }));
    expect(offloadItems(rows, (s) => s, 5)).toHaveLength(5);
  });
});

describe("ledger controls", () => {
  it("says exactly what delete removes, and what it leaves alone", () => {
    const c = deleteCopy({ assist: 150, delegated: 4, automation: 13 }, false);
    expect(c.button).toBe("Delete 167 rows");
    expect(c.what).toContain("150 assist, 4 delegated, 13 overnight");
    expect(c.what).toContain("answers you gave to Cue's questions");
    expect(c.what).toContain("Skill state");
    expect(c.what).toContain("one line to the audit log with counts only");
    expect(c.kept).toContain("Nothing else is touched");
    expect(deleteCopy({ assist: 1, delegated: 0, automation: 0 }, false).button).toBe("Delete 1 row");
  });
  it("says example data is only cleared on screen", () => {
    expect(deleteCopy({ assist: 6, delegated: 1, automation: 0 }, true).kept).toContain("example data");
  });
  it("reads the engine's deleted count either way", () => {
    expect(deletedCount({ deleted: 9 })).toBe(9);
    expect(deletedCount({ deleted: { assist: 5, delegated: 2, automation: 1 } })).toBe(8);
  });
  it("lists the field names across all rows, so the extra offload fields show too", () => {
    const f = ledgerFields([{ id: "a", stream: "assist" } as unknown as LedgerRow, { id: "b", stream: "delegated", minutes: 3, routine: "r", offload_outcome: "done" } as unknown as LedgerRow]);
    expect(f).toEqual(["id", "stream", "minutes", "routine", "offload_outcome"]);
  });
  it("lists a row's field names from the first row", () => {
    const rows = (improves as unknown as { ledger: { data: { rows: LedgerRow[] } } }).ledger.data.rows;
    const f = ledgerFields(rows);
    expect(f).toContain("skill");
    expect(f).toContain("tier");
    expect(f).not.toContain("text");
    expect(ledgerFields([])).toEqual([]);
  });
});

describe("early state marks", () => {
  it("lists the assist occurrences oldest first, optionally for one skill", () => {
    const rows = (sparse as unknown as { ledger: { data: { rows: LedgerRow[] } } }).ledger.data.rows;
    const all = marksOf(rows, null);
    expect(all).toHaveLength(6);
    expect(all.filter((m) => m.unaided)).toHaveLength(SPA.occurrences.unaided);
    expect(marksOf(rows, "reads-error-first")).toHaveLength(3);
  });
});

describe("origin and limits", () => {
  it("never calls simulated or synthetic data people", () => {
    expect(originSentence("simulated_participants", "synthetic")).toBe("Simulated participants (language model), not people.");
    expect(originSentence("synthetic_learner", "synthetic")).toContain("not people");
    expect(originSentence(undefined, "synthetic")).toContain("not people");
    expect(originSentence("live_worker", "real")).toContain("One person is not a study");
  });
  it("states the limits, including causation and the unrun live study", () => {
    const v = buildView(IMP);
    const l = limitations(v, "synthetic").join(" ");
    expect(l).toContain("does not show that the cues caused the change");
    expect(l).toContain("not the same as being expert");
    expect(l).toContain("never counted");
    expect(l).toContain("has not been run");
    expect(l).toContain("4 teammates");
    expect(limitations(v, "real").join(" ")).toContain("One person is not a study");
  });
});

describe("normalise", () => {
  it("fills what is missing without inventing numbers", () => {
    const n = normalizeGrowth({});
    expect(n.curve).toEqual([]);
    expect(n.baseline).toBeNull();
    expect(n.score.composite).toBeNull();
    expect(n.components.retention).toBeNull();
    expect(n.offloaded.delegated).toBe(0);
    expect(n.trend.direction).toBe("too_early");
    expect(statusOf(n)).toBe("empty");
  });
  it("leaves a complete answer unchanged where it matters", () => {
    const n = normalizeGrowth(IMP);
    expect(n.curve).toBe(IMP.curve);
    expect(n.score.composite).toBe(IMP.score.composite);
    expect(n.score.composite).toBe(wire(improves).score.composite_experimental);
    expect(n.by_skill).toHaveLength(IMP.by_skill.length);
  });
});
