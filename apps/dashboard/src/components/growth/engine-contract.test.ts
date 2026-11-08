// Contract test: the screen's adapters against what the engine's own score.growth() produced on its own simulated learners
// (a snapshot, regenerated when the engine's shape changes: fixtures/growth-engine-snapshot.json). Simulated, not people.
// If CUE-ENGINE renames or drops a key the screen reads, one of these fails before the screen shows a blank.
import { workerText } from "../../lib/voice";
import { describe, expect, it } from "vitest";
import snap from "../../fixtures/growth-engine-snapshot.json";
// The engine's own generated examples (packages/schema/examples, made by `python -m understudy_engine.cue.make_examples`). Read, never edited.
import exGrowth from "../../../../../packages/schema/examples/cue.growth.example.json";
import exSkill from "../../../../../packages/schema/examples/cue.growth_skill.example.json";
import exLedger from "../../../../../packages/schema/examples/cue.ledger.example.json";
import { buildView, cardsOf, ledgerFields, normalizeGrowth, offloadItems, skillRows } from "./model";
import type { Envelope, LedgerRow, WireGrowth } from "./wire";

const S = snap as unknown as Record<string, Envelope<WireGrowth>> & { ledger_sample: LedgerRow[] };
const READY = ["improving:overall", "improving:check-the-cliff", "flat:overall", "flat:check-the-cliff"] as const;

describe("engine contract: growth responses", () => {
  for (const k of READY) {
    it(`${k}: builds a complete view with finite numbers`, () => {
      const env = S[k];
      expect(env.meta!.n_unit).toBe("occurrences");
      expect(env.meta!.interval_level).toBe(0.95);
      const w = normalizeGrowth(env.data);
      const v = buildView(w, 95);
      expect(v.status).toBe("ready");
      expect(v.curve.length).toBeGreaterThan(0);
      for (const p of v.curve) {
        for (const x of [p.i, p.p, p.lo, p.hi, p.n]) expect(Number.isFinite(x)).toBe(true);
        expect(p.lo).toBeLessThanOrEqual(p.p + 1e-9);
        expect(p.hi).toBeGreaterThanOrEqual(p.p - 1e-9);
        expect(p.lv == null || (p.lv >= 1 && p.lv <= 4)).toBe(true);
        expect(p.cue).not.toBeNull();
      }
      expect(v.baseline).not.toBeNull();
      expect(v.independence).not.toBeNull();
      expect(v.composite).not.toBeNull();
      expect(v.composite!.caveat.length).toBeGreaterThan(0);
      expect(v.cards).toHaveLength(3);
      for (const c of cardsOf(w)) expect(c.display).not.toMatch(/NaN|undefined|null/);
      expect(v.skills.length).toBeGreaterThan(0);
      for (const s of skillRows(w.by_skill)) {
        expect(s.label.length).toBeGreaterThan(0);
        expect(s.name.length).toBeGreaterThan(0);
        expect(s.independent + s.assisted + s.other).toBe(s.n);
      }
      expect(v.title.length).toBeGreaterThan(0);
      expect(v.trend.sentence).not.toMatch(/NaN|undefined|null/);
    });
  }
  it("prints the engine's composite caveat verbatim and labels the composite experimental", () => {
    const raw = S["improving:overall"].data;
    const v = buildView(normalizeGrowth(raw));
    expect(v.composite!.experimental).toBe(true);
    expect(v.composite!.caveat).toBe(raw.score.composite_caveat);
    expect(v.composite!.caveat).toMatch(/^Experimental/);
    expect(v.composite!.value).toBe(raw.score.composite_experimental);
    expect(v.composite!.ci).toEqual(raw.score.composite_experimental_ci);
  });
  it("a steady trend reads as 'cannot tell yet' with the engine's sentence once, never 'no change'", () => {
    const raw = S["flat:overall"].data;
    expect(raw.trend.direction).toBe("steady");
    const v = buildView(normalizeGrowth(raw));
    expect(v.title).toBe("Cannot tell yet whether you need less help");
    expect(v.trend.sentence).toContain(workerText(raw.trend.power_note!)); // printed as sent, with a group of learners written as cases (views.md)
    expect(v.trend.sentence.match(/Cannot tell yet/g)).toHaveLength(1);
    expect(v.trend.sentence).toContain("includes zero");
    expect(v.trend.sentence.toLowerCase()).not.toMatch(/no clear change|has not changed/);
  });
  it("too few occurrences for a trend: the engine's own count, and how many more", () => {
    const raw = S["new:overall"].data;
    const v = buildView(normalizeGrowth(raw));
    expect(v.trend.sentence).toBe(`Too early for a trend. ${workerText(raw.trend.power_note!)}`);
    expect(v.trend.stillNeeded).toBe(raw.trend.needed_more);
    expect(raw.readiness.trend_needed).toBe(30);
  });
  it("a focused skill's view speaks of that skill with the engine's own name", () => {
    const v = buildView(normalizeGrowth(S["improving:check-the-cliff"].data));
    expect(v.focusId).toBe("check-the-cliff");
    expect(v.focusName).toBe("the cliff check");
    expect(v.smoothLevel).toBe(false);
  });
  it("everything smooths the level (skills differ), one skill does not", () => {
    expect(buildView(normalizeGrowth(S["improving:overall"].data)).smoothLevel).toBe(true);
  });
  it("a learner with 6 occurrences is early: no curve, no composite, counts only", () => {
    const v = buildView(normalizeGrowth(S["new:overall"].data));
    expect(v.status).toBe("early");
    expect(v.curve).toEqual([]);
    expect(v.composite).toBeNull();
    expect(v.trend.direction).toBe("too_early");
    expect(v.total).toBe(6);
  });
  it("nobody yet is empty, and the nulls the engine sends for n = 0 never become 0%", () => {
    const w = normalizeGrowth(S["none:overall"].data);
    const v = buildView(w);
    expect(v.status).toBe("empty");
    expect(w.components.independence).toBeNull();
    expect(cardsOf(w)[0].display).toBe("Not yet");
    expect(v.skills).toEqual([]);
  });
  it("the engine's partial counts and offloaded block read as zeros, not as missing", () => {
    const w = normalizeGrowth(S["improving:overall"].data);
    expect(w.offloaded.delegated).toBe(0);
    expect(w.counts?.assist).toBe(w.occurrences.total);
  });
});

describe("engine contract: ledger rows", () => {
  const rows = S.ledger_sample;
  it("carries every field the screen's row type names", () => {
    const f = ledgerFields(rows);
    for (const k of ["id", "person", "origin", "t_hour", "role", "skill", "step", "stream", "trigger", "tier", "accepted", "dismissed", "seconds_to_progress", "lost_s", "outcome", "level_before", "level_after", "taught", "retrieval"]) {
      expect(f, k).toContain(k);
    }
  });
  it("holds enums and numbers only: no free text", () => {
    for (const r of rows) for (const [k, v] of Object.entries(r)) if (typeof v === "string") expect(v, `${k}=${v}`).toMatch(/^[A-Za-z0-9_:\-.]+$/);
  });
  it("lists no assist row as work done for the person", () => {
    expect(offloadItems(rows, (s) => s)).toEqual([]);
  });
});

describe("engine contract: the engine's own example payloads", () => {
  const G = exGrowth as unknown as Envelope<WireGrowth>;
  const K = exSkill as unknown as Envelope<WireGrowth>;
  const L = exLedger as unknown as Envelope<{ rows: LedgerRow[]; counts: { assist: number; delegated: number; automation: number } }>;

  it("the overall example builds a ready view, with the engine's claim, caveat and power note printed as sent", () => {
    const v = buildView(normalizeGrowth(G.data), Math.round(G.meta!.interval_level * 100));
    expect(v.status).toBe("ready");
    expect(v.curve.length).toBeGreaterThan(0);
    expect(v.claim).toBe(G.data.claim);
    expect(v.composite!.caveat).toBe(G.data.score.composite_caveat);
    expect(v.composite!.value).toBe(G.data.score.composite_experimental);
    expect(v.independence).toEqual({ share: G.data.components.independence!.share, ci: G.data.components.independence!.wilson, k: G.data.components.independence!.k, n: G.data.components.independence!.n });
    expect(v.trend.direction).toBe(G.data.trend.direction);
    if (G.data.trend.direction === "steady") {
      expect(v.title).toBe("Cannot tell yet whether you need less help");
      expect(v.trend.sentence).toContain(workerText(G.data.trend.power_note!));
    }
    expect(v.lede).toBe(`In your first ${G.data.baseline!.n} steps you finished ${G.data.baseline!.k} without a cue. In the latest ${G.data.components.independence!.n}, ${G.data.components.independence!.k}.`);
  });
  it("the counts in the lede match the engine's own counts: show the counts, not a verdict", () => {
    expect(G.data.claim).toContain(`Unaided on ${G.data.components.independence!.k} of the last ${G.data.components.independence!.n}`);
  });
  it("the skill example focuses that skill under the engine's name", () => {
    const v = buildView(normalizeGrowth(K.data));
    expect(v.focusId).toBe(K.data.skill);
    expect(v.focusName).toBe("the cliff check");
    expect(v.smoothLevel).toBe(false);
  });
  it("the ledger example: counts by stream, offload rows with routine, minutes and a result", () => {
    expect(L.data.counts.assist).toBeGreaterThan(0);
    const off = L.data.rows.filter((r) => r.stream !== "assist");
    expect(off.length).toBe(L.data.counts.delegated + L.data.counts.automation);
    const items = offloadItems(L.data.rows, (s) => s);
    expect(items.length).toBe(off.length);
    for (const i of items) {
      expect(["done", "waiting for your approval", "failed", "paused for you"]).toContain(i.outcome);
      expect(i.what.length).toBeGreaterThan(0);
    }
    expect(ledgerFields(L.data.rows)).toEqual(expect.arrayContaining(["routine", "minutes", "offload_outcome", "stream", "skill"]));
  });
  it("the ledger example holds enums and numbers only (no free text)", () => {
    for (const r of L.data.rows) for (const [k, v] of Object.entries(r)) if (typeof v === "string") expect(v, `${k}=${v}`).toMatch(/^[A-Za-z0-9_:\-.]+$/);
  });
});
