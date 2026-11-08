// The budgets check-copy.mjs enforces (qa/knack/budgets.json) may be tighter than the spec's (docs/knack-ux/budgets.json, KNACK_UX section 5), never looser.
// "A change that raises a number is a decision for the lead": this is what makes loosening a number a visible, failing change instead of a quiet edit.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const dashboard = join(here, "..");
const read = (p: string) => JSON.parse(readFileSync(p, "utf8"));
const spec = read(join(dashboard, "..", "..", "docs", "knack-ux", "budgets.json"));
const mine = read(join(dashboard, "qa", "knack", "budgets.json"));

type Row = Record<string, number | string | boolean | undefined>;
const METRICS = ["wordsAbove", "wordsTotal", "longParas", "pills", "controls"] as const;

/** A route's budget for a metric: its own number, else its audience's default. */
const budget = (cfg: { defaults: Record<string, Row>; routes: Record<string, Row> }, id: string, metric: string): number | undefined => {
  const r = cfg.routes[id] ?? {};
  const v = r[metric] ?? cfg.defaults[String(r.audience)]?.[metric];
  return typeof v === "number" ? v : undefined;
};

describe("check-copy budgets against the spec", () => {
  it("keeps the audience defaults of the spec", () => {
    expect(mine.defaults).toEqual(spec.defaults);
  });

  it("keeps the element budgets of the spec (title, hero, lede, row, button)", () => {
    // The script enforces the element budgets it can read from a rendered page; each of those is the spec's number or tighter.
    for (const k of ["screenTitleWords", "heroWords", "ledeWords", "rowTitleWords", "buttonWords", "heroActionWords"]) expect(mine.elements[k], k).toBeLessThanOrEqual(spec.elements[k]);
    for (const k of Object.keys(mine.elements)) expect(spec.elements[k], k).toBeDefined();
  });

  it("keeps the sidebar budget of the spec: six rows, nine for an admin, no hint words", () => {
    expect(mine.sidebar.workerRows).toBeLessThanOrEqual(spec.sidebar.workerRows);
    expect(mine.sidebar.adminRows).toBeLessThanOrEqual(spec.sidebar.adminRows);
    expect(mine.sidebar.hintWords).toBeLessThanOrEqual(spec.sidebar.hintWords);
    expect(mine.sidebar.words.worker).toBeLessThanOrEqual(spec.sidebar.words.worker);
    expect(mine.sidebar.words.admin).toBeLessThanOrEqual(spec.sidebar.words.admin);
  });

  it("is never looser than the spec on a screen the spec budgets", () => {
    const loose: string[] = [];
    for (const id of Object.keys(spec.routes)) {
      if (!(id in mine.routes)) continue;
      for (const m of METRICS) {
        const s = budget(spec, id, m);
        const b = budget(mine, id, m);
        if (s !== undefined && b !== undefined && b > s) loose.push(`${id} ${m}: ${b} > ${s}`);
      }
      const e = (spec.routes[id] as Row).wordsAboveEmpty;
      const f = (mine.routes[id] as Row).wordsAboveEmpty;
      if (typeof e === "number" && typeof f === "number" && f > e) loose.push(`${id} wordsAboveEmpty: ${f} > ${e}`);
    }
    expect(loose).toEqual([]);
  });

  it("budgets every screen of the Track D list, with a path", () => {
    for (const id of ["growth", "firm", "roles", "onboarding", "genome", "presence", "graph", "week", "git", "forecasts", "agents", "models", "today"]) {
      expect(mine.routes[id], id).toBeTruthy();
      expect(String(mine.routes[id].path), id).toMatch(/^\//);
    }
  });

  it("keeps Evidence exempt from the word budget only, not from the header and sidebar rules", () => {
    expect(mine.exempt.evidence).toBeTruthy();
    expect(Object.keys(mine.routes)).not.toContain("evidence");
  });
});
