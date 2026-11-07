import { describe, expect, it } from "vitest";
import weekFx from "../fixtures/calendar-week.json";
import agentsFx from "../fixtures/agents-runs.json";
import ledgerFx from "../fixtures/privacy-ledger.json";
import summaryFx from "../fixtures/privacy-summary.json";
import type { AgentRun, CalendarWeek, LedgerEntry, PrivacySummary } from "../types";
import { extensionsFrom, screenEnabled } from "./ext";
import { featureLabel, featureUnit, fmtFeature, gapClear, minutesByKind, spans, toMinutes, weekHeadline, weekWindow } from "./week";
import { budgetBars, countStates, fmtClock, isActive, leaseLeft, resultWithoutSteps, runActive, stateTone, stepsOf } from "./agents";
import { callsToday, canaryReading, exportLedger, fmtBytes, purposesSorted } from "./ledger";
import { cleanPrepared, expiresIn, firedText, preparedDirty } from "./briefing";

const week = (weekFx as unknown as { data: CalendarWeek }).data;
const runs = (agentsFx as unknown as { data: AgentRun[] }).data;
const ledger = (ledgerFx as unknown as { data: LedgerEntry[] }).data;
const summary = (summaryFx as unknown as { data: PrivacySummary }).data;

describe("extension gating", () => {
  it("shows every screen in demo-fixture mode", () => {
    const f = extensionsFrom(null, "demo");
    for (const s of ["week", "briefing", "agents", "privacy"] as const) expect(screenEnabled(s, f)).toBe(true);
  });
  it("live: shows a screen only when /health says its layer is true", () => {
    const f = extensionsFrom({ extensions: { calendar: true, privacy: false, proactive: true } }, "live");
    expect(screenEnabled("week", f)).toBe(true);
    expect(screenEnabled("briefing", f)).toBe(true);
    expect(screenEnabled("privacy", f)).toBe(false);
    expect(screenEnabled("agents", f)).toBe(false); // missing means off
  });
  it("live: a health answer with no extensions key turns everything off", () => {
    const f = extensionsFrom({}, "live");
    for (const s of ["week", "briefing", "agents", "privacy"] as const) expect(screenEnabled(s, f)).toBe(false);
  });
});

describe("week ribbon", () => {
  it("reads times as HH:MM, minutes or ISO", () => {
    expect(toMinutes("09:30")).toBe(570);
    expect(toMinutes(615)).toBe(615);
    expect(Number.isNaN(toMinutes("not a time"))).toBe(true);
    expect(toMinutes("2026-11-07T14:00:00")).toBe(14 * 60);
  });
  it("sorts spans and drops unreadable or empty ones", () => {
    const s = spans([{ start: "11:00", end: "12:00", kind: "focus" }, { start: "09:00", end: "09:00", kind: "meeting" }, { start: "x", end: "10:00", kind: "meeting" }, { start: "09:30", end: "10:00", kind: "meeting" }]);
    expect(s.map((x) => x.from)).toEqual([570, 660]);
  });
  it("windows to whole hours around the blocks, never narrower than 08:00 to 18:00", () => {
    const [lo, hi] = weekWindow(week.days, week.expert.days);
    expect(lo).toBeLessThanOrEqual(8 * 60);
    expect(hi).toBeGreaterThanOrEqual(18 * 60);
    expect(lo % 60).toBe(0);
    expect(weekWindow([{ dow: 0, blocks: [{ start: "06:10", end: "20:20", kind: "meeting" }] }])).toEqual([360, 1260]);
  });
  it("counts minutes by kind and the learner has more meeting time than the expert", () => {
    const l = minutesByKind(week.days), e = minutesByKind(week.expert.days ?? []);
    expect(l.meeting / 60).toBeCloseTo(week.features.meeting_h as number, 0);
    expect(l.meeting).toBeGreaterThan(e.meeting);
    expect(e.focus).toBeGreaterThan(l.focus);
  });
  it("labels features, picks units from the key and prints signed deltas with a real minus", () => {
    expect(featureLabel("meeting_h")).toMatch(/Meeting hours/);
    expect(featureUnit("longest_focus_min")).toBe("min");
    expect(featureUnit("fragmentation")).toBe("share");
    expect(fmtFeature("meeting_h", 3.5, true)).toBe("+3.5 h");
    expect(fmtFeature("focus_blocks_90", -3, true)).toBe("−3");
    expect(fmtFeature("fragmentation", 0.31)).toBe("0.31");
  });
  it("states the headline in words and flags which gaps exclude zero", () => {
    const r1 = (n: number) => Math.round(n * 10) / 10;
    expect(weekHeadline(week.features, week.expert)).toBe(`You spend ${r1(week.features.meeting_h as number)} hours a week in meetings, ${r1((week.features.meeting_h as number) - (week.expert.meeting_h as number))} more than the expert`);
    const clear = week.gap.rows.filter(gapClear).map((r) => r.feature);
    expect(clear).toContain("meeting_h");
    expect(clear).not.toContain("work_span_h");
  });
  it("carries no free text: only block kinds, times and attendee buckets", () => {
    const keys = new Set<string>();
    for (const d of week.days) for (const b of d.blocks) Object.keys(b).forEach((k) => keys.add(k));
    const allowed = new Set(["start", "end", "start_min", "end_min", "kind", "usable", "n_attendees_bucket"]);
    for (const k of keys) expect(allowed.has(k), `unexpected block field ${k}`).toBe(true);
    // Day fields are a date, a flag and the blocks: no title or name can be carried.
    for (const d of week.days) for (const k of Object.keys(d)) expect(["dow", "date", "working", "blocks"]).toContain(k);
  });
});

describe("agent runs", () => {
  it("draws budget bars as spent against allowed and flags a spent budget", () => {
    const failed = runs.find((r) => r.state === "failed")!;
    const bars = budgetBars(failed.children[0].budget, failed.children[0].spent);
    expect(bars.map((b) => b.key)).toEqual(["steps", "seconds", "tokens"]);
    expect(bars.every((b) => b.over && b.frac === 1)).toBe(true);
    const run = runs[0];
    const b2 = budgetBars(run.parent.budget, run.parent.spent);
    expect(b2[0].text).toBe("7 of 20 steps");
    expect(b2[1].text).toBe("96 of 300 s");
    expect(b2[0].over).toBe(false);
  });
  it("tells active runs from finished ones and counts them", () => {
    expect(isActive("running")).toBe(true);
    expect(isActive("done")).toBe(false);
    expect(runActive(runs[0])).toBe(true);
    expect(runActive(runs[1])).toBe(false);
    expect(countStates(runs)).toEqual({ active: 1, done: 1, failed: 1 });
    expect(stateTone("failed")).toBe("bad");
    expect(stateTone("stopped")).toBe("muted");
  });
});

describe("leases and step checks", () => {
  it("counts a lease down from when it was fetched and never below zero, and a revoked lease has none", () => {
    const l = { ttl_s: 120, remaining_s: 87, steps_left: 7, tools: ["git_log"], revoked: false };
    expect(leaseLeft(l, 0)).toBe(87);
    expect(leaseLeft(l, 30)).toBe(57);
    expect(leaseLeft(l, 500)).toBe(0);
    expect(leaseLeft({ ...l, revoked: true }, 0)).toBe(0);
    expect(fmtClock(87)).toBe("1:27");
    expect(fmtClock(5)).toBe("0:05");
  });
  it("carries a lease on every child in the fixture, scoped to tools only", () => {
    for (const r of runs) for (const c of r.children) {
      expect(c.lease).toBeTruthy();
      expect(c.lease!.tools.length).toBeGreaterThan(0);
      expect(Object.keys(c.lease!).sort()).toEqual(["remaining_s", "revoked", "steps_left", "tools", "ttl_s"]);
    }
  });
  it("reads steps and their checks, and tolerates a result with none", () => {
    const steps = stepsOf({ steps: [{ step: "Load", check: "verified" }, { name: "Plot", check: "uncertain" }, { label: "Write", check: "failed" }, { action: "x" }, "odd"] });
    expect(steps.map((s) => s.check)).toEqual(["verified", "uncertain", "failed", null, null]);
    expect(steps[0].label).toBe("Load");
    expect(steps[4].label).toBe("Step 5");
    expect(stepsOf(null)).toEqual([]);
    expect(stepsOf({ summary: 1 })).toEqual([]);
  });
  it("shows the rest of a result as facts, without the steps", () => {
    expect(resultWithoutSteps({ summary: { rows: 3 }, steps: [] })).toEqual({ rows: 3 });
    expect(resultWithoutSteps({ status: "x", steps: [] })).toEqual({ status: "x" });
  });
});

describe("privacy ledger", () => {
  it("sorts purposes by count and formats sizes", () => {
    expect(purposesSorted(summary.by_purpose)[0][1]).toBeGreaterThanOrEqual(2);
    expect(fmtBytes(212)).toBe("212 B");
    expect(fmtBytes(4683073984)).toBe("4.36 GB");
  });
  it("counts calls today from the ledger itself, so the summary and the list agree", () => {
    const now = new Date(ledger[0].t);
    const today = callsToday(ledger, now);
    expect(Object.values(today).reduce((a, b) => a + b, 0)).toBeGreaterThan(0);
    expect(Object.values(today).reduce((a, b) => a + b, 0)).toBeLessThanOrEqual(ledger.length);
  });
  it("exports exactly the entries listed, payloads as sent", () => {
    const out = JSON.parse(exportLedger(ledger));
    expect(out.entries).toEqual(ledger);
  });
  it("reads the canary in plain words and never overclaims", () => {
    expect(canaryReading(summary.canary).tone).toBe("clear");
    expect(canaryReading(summary.canary).text).toMatch(/evidence from a test, not a proof/);
    expect(canaryReading({ runs: 3, planted: 30, leaked: 2 }).tone).toBe("leak");
    expect(canaryReading(null).tone).toBe("none");
    expect(canaryReading({ runs: 0, planted: 0, leaked: 0 }).tone).toBe("none");
  });
  it("lists only enums, numbers and ids in the fixture payloads: no free text", () => {
    for (const e of ledger) for (const [k, v] of Object.entries(e.payload ?? {})) {
      expect(e.fields).toContain(k);
      const ok = typeof v === "number" || typeof v === "boolean" || (typeof v === "string" && /^[a-z0-9_]+$/.test(v)) || typeof v === "object";
      expect(ok).toBe(true);
    }
  });
});

describe("briefing helpers", () => {
  it("cleans prepared content and detects real edits only", () => {
    expect(cleanPrepared({ text: "  hi ", steps: [" a ", "", "  "] })).toEqual({ text: "hi", steps: ["a"] });
    expect(preparedDirty({ text: "a" }, { text: " a " })).toBe(false);
    expect(preparedDirty({ steps: ["a", "b"] }, { steps: ["a", "c"] })).toBe(true);
  });
  it("says when a card expires", () => {
    const now = Date.parse("2026-11-07T12:00:00Z");
    expect(expiresIn("2026-11-07T12:40:00Z", now)).toBe("in 40 min");
    expect(expiresIn("2026-11-07T17:00:00Z", now)).toBe("in 5 h");
    expect(expiresIn("2026-11-07T11:00:00Z", now)).toBe("expired");
  });
  it("says which thing firing created", () => {
    expect(firedText({ queue_id: "q_1" })).toMatch(/approval item q_1/);
    expect(firedText({ run_id: "r_1" })).toMatch(/background run r_1/);
    expect(firedText({})).toMatch(/did not say/);
  });
});
