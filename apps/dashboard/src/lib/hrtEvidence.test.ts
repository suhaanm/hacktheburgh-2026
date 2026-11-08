import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import reportFx from "../fixtures/eval-report.json";
import { ANCHORS, mapRows, otherSections, sectionTitle } from "./evidence";

/**
 * The two HRT blocks of the Evidence page (components/HrtEvidence.tsx): they are anchored so the evidence map points at them and "Other sections" does not list
 * them twice; their source says what the app may say (owner decision D57: no 'synthetic', no 'simulated'); and, once the report carries the sections, the
 * shapes the component reads are there.
 */
const src = readFileSync(fileURLToPath(new URL("../components/HrtEvidence.tsx", import.meta.url)), "utf8");
const secs = (reportFx as unknown as { sections: Record<string, Record<string, unknown>> }).sections;

describe("HRT evidence blocks", () => {
  it("are anchored, titled and not repeated under other sections", () => {
    expect(ANCHORS.hrt_ledger).toBe("hrt-ledger");
    expect(ANCHORS.hrt_decisions).toBe("hrt-decisions");
    expect(sectionTitle("hrt_ledger")).not.toMatch(/synthetic|simulated/i);
    const rows = mapRows(reportFx as never);
    expect(otherSections(rows).map((r) => r.section)).not.toContain("hrt_ledger");
    expect(otherSections(rows).map((r) => r.section)).not.toContain("hrt_decisions");
  });

  it("use the app's words: generated worlds, generators we wrote", () => {
    expect(src).not.toMatch(/synthetic|simulat/i);
    expect(src).not.toMatch(/\bdemo\b/i);
    expect(src).toMatch(/generated worlds/);
  });

  it("read the shapes the engine writes, when the report has the sections", () => {
    const l = secs.hrt_ledger, d = secs.hrt_decisions;
    if (!l || l.status) return;             // the report on disk has not had the sections merged yet: nothing to check
    expect(Array.isArray(l.rows) && Array.isArray(l.worlds) && Array.isArray(l.guard) && Array.isArray(l.reliability_v1)).toBe(true);
    const w = (l.worlds as Record<string, unknown>[])[0];
    for (const k of ["world", "predictions", "model_log_loss", "best_naive", "model_minus_best_naive", "model_minus_best_naive_ci", "verdict", "calibration_slope", "calibration_slope_ci", "calibration_intercept", "guard_flags"]) expect(w).toHaveProperty(k);
    expect(d && !d.status).toBeTruthy();
    const r = (d.rows as Record<string, unknown>[])[0];
    for (const k of ["id", "decision", "shipped_rule", "naive_policy", "naive_value", "oracle_value", "primary_contrast", "ci95", "ci_adjusted_98_75", "verdict"]) expect(r).toHaveProperty(k);
    expect(Array.isArray(d.scoreboard)).toBe(true);
  });

  it("read the conformal and decision-value blocks, with width beside coverage, when the report has them", () => {
    const l = secs.hrt_ledger, d = secs.hrt_decisions;
    if (!l || l.status || !l.conformal) return;
    const c = l.conformal as Record<string, unknown>;
    for (const k of ["claims", "standard", "recalibrated", "guard_link", "statement"]) expect(c).toHaveProperty(k);
    const row = (c.standard as Record<string, Record<string, unknown>>[])[0];
    for (const k of ["world", "people", "stuck_set", "finish"]) expect(row).toHaveProperty(k);
    for (const k of ["coverage", "ci", "status", "single_label_share", "both_label_share"]) expect(row.stuck_set).toHaveProperty(k);
    for (const k of ["coverage", "ci", "status", "factor", "recentred_coverage", "recentred_factor"]) expect(row.finish).toHaveProperty(k);
    expect(row.next_progress).toHaveProperty("mean_length_steps");
    if (!d || d.status || !d.value_vs_accuracy) return;
    const v = d.value_vs_accuracy as Record<string, unknown>;
    for (const k of ["claims", "worlds", "statement", "design"]) expect(v).toHaveProperty(k);
    const w = (v.worlds as Record<string, unknown>[])[0];
    for (const k of ["world", "best_naive", "forecasts", "model_minus_best_naive", "model_minus_best_naive_ci", "verdict", "log_loss_model_minus_best_naive", "guard"]) expect(w).toHaveProperty(k);
    expect((w.forecasts as Record<string, unknown>[])[0]).toHaveProperty("net_minutes_per_hour");
  });
});
