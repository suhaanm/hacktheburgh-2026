import { describe, expect, it } from "vitest";
import reportFx from "../fixtures/eval-report.json";
import type { EvalReport } from "../types";
import { ANCHORS, ORIGIN_LABEL, describeSection, hasInterval, mapCounts, mapRows, nText, originKind, originWords, otherSections, sectionTitle } from "./evidence";

const rep = reportFx as unknown as EvalReport & { evidence_map: unknown[] };

describe("evidence map", () => {
  const rows = mapRows(rep);
  it("has one row per section in the report, from the eval track's own map", () => {
    expect(rows.length).toBe(Array.isArray(rep.evidence_map) ? rep.evidence_map.length : Object.keys(rep.sections).length - 1);
    expect(new Set(rows.map((r) => r.section)).size).toBe(rows.length);
    expect(rows.every((r) => r.title.length > 0)).toBe(true);
  });
  // A small report of the tests' own, so the pending and no-results cases do not depend on which sections the eval harness has landed.
  const m = (origin = "synthetic") => ({ origin, n: 4, n_unit: "people", split: null, interval_level: 0.95, note: null, generated_at: "" });
  const small = {
    sections: {
      hazard: { meta: m(), model: { log_loss: 0.4 } },
      runtime: { status: "pending", reason: "runtime not landed (module absent)", meta: m() },
      study: { status: "not_run", reason: "the live study has not been run: no data", meta: m("real") },
      deficit_recovery: { meta: m(), rows: [{ deficit: "a", ci: [0.2, 0.9] }] },
      plain: { meta: m(), value: 3, rows: [{ name: "x", value: 1 }] },
    },
  } as unknown as EvalReport;
  const smallRows = mapRows(small);
  it("carries status and a reason for what has not run", () => {
    const runtime = smallRows.find((r) => r.section === "runtime");
    expect(runtime?.status).toBe("pending");
    expect(runtime?.reason).toMatch(/not landed|absent/);
    const study = smallRows.find((r) => r.section === "study")!;
    expect(study.status).toBe("not_run");
    expect(study.kind).toBe("not_run");
    expect(study.n).toBe(4);
    expect(smallRows.find((r) => r.section === "hazard")?.reason).toBeNull();
  });
  it("carries the same for what the real report has not run: the live study, and the role studies", () => {
    const study = rows.find((r) => r.section === "study")!;
    expect(study.status).toBe("not_run");
    expect(study.n).toBe(4);
    expect(study.reason).toMatch(/not been run|no data/);
    // The harness writes origin "unknown" for a study that has not run. Nothing was measured, so the row says "not run": never "synthetic", never "live".
    expect(study.kind).toBe("not_run");
    expect(study.originLabel).toBe("not run");
    const roles = rows.find((r) => r.section === "study_roles")!;
    expect(roles.status).toBe("not_run");
    expect(roles.reason).toMatch(/not people/);
    expect(rows.find((r) => r.section === "agentic")?.status).toBe("ok");
    expect(rows.find((r) => r.section === "hazard")?.reason).toBeNull();
  });
  it("counts statuses", () => {
    const c = mapCounts(rows);
    expect(c.total).toBe(rows.length);
    expect(c.ok + c.not_run + c.pending + c.failed).toBe(c.total);
    expect(c.ok).toBeGreaterThan(10);
  });
  it("labels simulated participants as such, and a real model on scripted cases stays synthetic", () => {
    const sim = rows.find((r) => r.section === "study_sim")!;
    expect(sim.kind).toBe("simulated");
    expect(sim.originLabel).toBe("language-model participants");
    const live = rows.find((r) => r.section === "redteam_live")!;
    expect(live.kind).toBe("synthetic");
    expect(live.label).toMatch(/real model/);
    expect(originKind("real", "people", null, "Live study")).toBe("live");
    expect(originKind("synthetic", "silicon participants", null, "x")).toBe("simulated");
    expect(originKind("mixed", "runs", null, "x")).toBe("mixed");
  });
  it("says whether a section reports intervals: yes, no, and none for a section with no results", () => {
    expect(smallRows.find((r) => r.section === "deficit_recovery")?.intervals).toBe("yes");
    expect(smallRows.find((r) => r.section === "plain")?.intervals).toBe("no");
    expect(smallRows.find((r) => r.section === "runtime")?.intervals).toBe("none");
    expect(rows.find((r) => r.section === "deficit_recovery")?.intervals).toBe("yes");
    expect(rows.find((r) => r.section === "study")?.intervals).toBe("none");
    expect(hasInterval({ rows: [{ gap: 1, ci: [0.2, 0.9] }] })).toBe(true);
    expect(hasInterval({ meta: { interval_level: 0.95 }, value: 3 })).toBe(false);
    expect(hasInterval({ held_out_ci: [0.01, 0.04] })).toBe(true);
  });
  it("points at a section's own block when it has one", () => {
    expect(rows.find((r) => r.section === "hazard")?.anchor).toBe(ANCHORS.hazard);
    expect(rows.find((r) => r.section === "pooling")?.anchor).toBe("deficits");
    expect(rows.find((r) => r.section === "privacy")?.anchor).toBe("privacy");
  });
  it("shows a section it has never heard of, with no code change", () => {
    const withNew = { ...rep, sections: { ...rep.sections, brand_new: { meta: { origin: "synthetic", n: 9, n_unit: "widgets", interval_level: 0.95, split: null, note: null, generated_at: "" }, headline: { widgets_ok: 9, share: 0.5, ci: [0.4, 0.6] }, rows: [{ name: "a", value: 1.5, extra: { nested: 1 } }], caveats: ["Only a test."] } } } as unknown as EvalReport;
    const r = mapRows(withNew).find((x) => x.section === "brand_new")!;
    expect(r.title).toBe("Brand new");
    expect(r.status).toBe("ok");
    expect(r.n).toBe(9);
    expect(r.intervals).toBe("yes");
    expect(r.anchor).toBeNull();
    expect(otherSections(mapRows(withNew)).map((x) => x.section)).toContain("brand_new");
    const v = describeSection((withNew.sections as Record<string, unknown>).brand_new);
    expect(v.facts).toContainEqual(["Widgets ok", "9"]);
    expect(v.facts).toContainEqual(["Ci", "[0.4, 0.6]"]);
    expect(v.tables[0].cols).toEqual(["name", "value"]);
    expect(v.caveats).toEqual(["Only a test."]);
  });
  it("lists only sections with no block of their own under 'other'", () => {
    const other = otherSections(rows).map((r) => r.section);
    expect(other).toContain("git");
    expect(other).toContain("modelbench");
    expect(other).not.toContain("hazard");
    expect(other).not.toContain("pooling");
  });
  it("writes n with its unit", () => {
    expect(nText({ n: 11336, nUnit: "tokens" })).toBe("11,336 tokens");
    expect(nText({ n: 4, nUnit: "people" })).toBe("4 people");
    expect(nText({ n: 1, nUnit: "" })).toBe("1 person");
    expect(nText({ n: null, nUnit: "runs" })).toBe("none yet");
    expect(sectionTitle("something_new")).toBe("Something new");
  });
  it("describes every real section without throwing, and never prints an object as text", () => {
    for (const [k, v] of Object.entries(rep.sections)) {
      if (k === "limitations") continue;
      const d = describeSection(v);
      for (const [, val] of d.facts) expect(val).not.toMatch(/\[object Object\]/);
      for (const t of d.tables) for (const row of t.rows) for (const c of Object.values(row)) expect(c).not.toMatch(/\[object Object\]/);
    }
  });
});

import { liveFixSentence, liveRuns, liveSentence } from "./evidence";

describe("real model block: every number carries its condition", () => {
  const live = (reportFx as unknown as { sections: { agent_runs: { live: unknown } } }).sections.agent_runs.live;
  const v = liveRuns(live)!;
  it("lists the conditions in a fixed order with their own counts", () => {
    expect(v.rows.map((r) => r.key)).toEqual(["clean", "layout_v2", "glitch", "injected"]);
    const by = Object.fromEntries(v.rows.map((r) => [r.key, r]));
    expect([by.clean.pass, by.clean.n, by.clean.falseClaims]).toEqual([18, 20, 0]);
    expect([by.glitch.pass, by.glitch.n, by.glitch.falseClaims]).toEqual([0, 20, 20]);
    expect([by.layout_v2.pass, by.layout_v2.n]).toEqual([20, 20]);
    expect([by.injected.paused, by.injected.n, by.injected.mustPause]).toEqual([20, 20, true]);
  });
  it("writes each condition as a sentence with the condition, the count and the false claims together", () => {
    const s = v.rows.map(liveSentence);
    expect(s[0]).toBe("Clean pages: 18 of 20 passed, and no false claims.");
    expect(s[2]).toMatch(/^A 503 error mid-run: 0 of 20 passed, and 20 false claims/);
    expect(s[3]).toMatch(/^Injected instruction: paused on 20 of 20 runs.*Pausing is the right outcome here, not a pass\.$/);
    for (const x of s) expect(x).toMatch(/of \d+/);
  });
  it("reads pass_by_condition as {pass, n, wilson} objects too, and never uses a named all-conditions total", () => {
    const shaped = {
      ...(live as object), condition: "clean", false_claims_all_conditions: 20,
      pass_by_condition: { clean: { pass: 18, n: 20, wilson: [0.699, 0.972] }, layout_v2: { pass: 20, n: 20, wilson: [0.839, 1] }, glitch: { pass: 0, n: 20, wilson: [0, 0.161] }, injected: { pass: 0, n: 20, wilson: [0, 0.161] } },
      false_claims_by_condition: { clean: 0, layout_v2: 0, glitch: 20, injected: 0 },
    };
    const w = liveRuns(shaped)!;
    expect(w.rows.map((r) => [r.key, r.pass, r.n, r.falseClaims])).toEqual([["clean", 18, 20, 0], ["layout_v2", 20, 20, 0], ["glitch", 0, 20, 20], ["injected", 0, 20, 0]]);
    expect(w.rows[0].wilson).toEqual([0.699, 0.972]);
    expect(JSON.stringify(w)).not.toContain("false_claims_all_conditions");
    // The conditions block can even be absent: the per-condition maps alone are enough.
    const bare = liveRuns({ label: "real model", pass_by_condition: shaped.pass_by_condition, false_claims_by_condition: shaped.false_claims_by_condition })!;
    expect(bare.rows.map(liveSentence)[2]).toMatch(/^A 503 error mid-run: 0 of 20 passed, and 20 false claims/);
  });
  it("labels the fix as in-sample, with the result it replaces", () => {
    expect(v.fix?.inSample).toBe(true);
    const t = liveFixSentence(v.fix!);
    expect(t).toMatch(/After the fix, with the 503 error: 10 of 10 passed/);
    expect(t).toMatch(/Before the fix, the same condition: 0 of 20 passed, 20 false claims/);
    expect(v.fix?.droppedNote).toMatch(/excluded from every number/);
  });
  it("uses pass_by_condition and false_claims_by_condition when the report has them", () => {
    const withMaps = { ...(live as object), pass_by_condition: { clean: 17, glitch: 1 }, false_claims_by_condition: { glitch: 19 } };
    const w = liveRuns(withMaps)!;
    expect(w.rows.find((r) => r.key === "clean")?.pass).toBe(17);
    expect(w.rows.find((r) => r.key === "glitch")?.pass).toBe(1);
    expect(w.rows.find((r) => r.key === "glitch")?.falseClaims).toBe(19);
    expect(w.rows.find((r) => r.key === "layout_v2")?.pass).toBe(20); // falls back to the condition's own count
  });
  it("never exposes the bare totals, and says the computer-use run was a stand-in actuator", () => {
    const text = JSON.stringify(v);
    expect(text).not.toMatch(/"false_claims":20,"cost/); // the top-level total is not carried through
    expect(v.tier3).toMatch(/stand-in actuator|nothing is clicked/i);
    expect(liveRuns(null)).toBeNull();
    expect(liveRuns({ label: "x" })?.rows).toEqual([]);
  });
});

describe("the origin badge for something that has not run", () => {
  const m = (origin: string) => ({ origin, n: 4, n_unit: "people", split: null, interval_level: 0.95, note: null, generated_at: "" });
  it("is 'not run' for a not_run section, whatever origin it carries", () => {
    for (const origin of ["real", "synthetic", "mixed", "unknown"]) expect(originKind(origin, "people", null, "x", "not_run")).toBe("not_run");
    expect(ORIGIN_LABEL.not_run).toBe("not run");
  });
  it("is 'not run' for an unknown origin even when the status says ok, and never 'synthetic' or 'live'", () => {
    expect(originKind("unknown", "people", null, "x", "ok")).toBe("not_run");
    expect(originKind("unknown", "people", null, "x")).toBe("not_run");
    expect(originKind("unknown", "people", null, "x")).not.toBe("synthetic");
    expect(originKind("unknown", "people", null, "x")).not.toBe("live");
  });
  it("leaves every section that has run exactly as it was", () => {
    expect(originKind("real", "people", null, "Live study", "ok")).toBe("live");
    expect(originKind("synthetic", "people", null, "x", "ok")).toBe("synthetic");
    expect(originKind("mixed", "runs", null, "x", "ok")).toBe("mixed");
    expect(originKind("synthetic", "silicon participants", null, "x", "ok")).toBe("simulated");
    expect(originKind("synthetic", "people", null, "x", "pending")).toBe("synthetic");
  });
  it("shows 'not run' on the map row, both for status and for origin", () => {
    const rep = { sections: {
      live_study: { status: "not_run", reason: "no data", meta: m("real") },
      role_studies: { status: "not_run", reason: "Language-model participants, not people.", meta: m("synthetic"), label: "language-model participants, not people" },
      held: { meta: m("unknown"), rows: [{ a: 1 }] },
      ran: { meta: m("synthetic"), rows: [{ a: 1, ci: [0, 2] }] },
    } } as unknown as EvalReport;
    const rows = mapRows(rep);
    const label = (s: string) => rows.find((r) => r.section === s)?.originLabel;
    expect(label("live_study")).toBe("not run");
    expect(label("role_studies")).toBe("not run");
    expect(label("held")).toBe("not run");
    expect(label("ran")).toBe("generators we wrote");
  });
  it("shows 'not run' on every not_run or unknown-origin row of the real report, and 'synthetic' or 'live' on none of them", () => {
    const realRows = mapRows(rep);
    for (const r of realRows.filter((x) => x.status === "not_run" || x.origin === "unknown")) {
      expect(r.kind).toBe("not_run");
      expect(r.originLabel).toBe("not run");
    }
    expect(realRows.some((r) => r.status === "not_run")).toBe(true);
  });
  it("words a single analytic's badge the same way", () => {
    expect(originWords("real")).toEqual({ text: "real", data: "real", sr: ", measured from real people" });
    expect(originWords("synthetic").text).toBe("");
    expect(originWords("mixed").text).toBe("");
    expect(originWords("unknown")).toEqual({ text: "not run", data: "not_run", sr: ", nothing was measured yet" });
    expect(originWords("").text).toBe("not run");
  });
});
