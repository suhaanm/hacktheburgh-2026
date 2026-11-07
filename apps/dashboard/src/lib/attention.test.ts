import { describe, expect, it } from "vitest";
import settingsFx from "../fixtures/attention-settings.json";
import digestFx from "../fixtures/attention-digest.json";
import type { AttentionDigest, AttentionSettings } from "../types";
import { BUDGET_FLOOR, MODES, bannerReading, budgetWords, clampBudget, groupTypes, learnedLines, modeLine, reasonText, todayHeadline, todaySummary, typeLabel, withMode } from "./attention";

const settings = (settingsFx as unknown as { data: AttentionSettings }).data;
const digest = (digestFx as unknown as { data: AttentionDigest }).data;

describe("notice settings", () => {
  it("groups the engine's five classes into four plain groups, in the engine's order, with safety inside 'Needs you'", () => {
    const g = groupTypes(settings.types);
    expect(g.map((x) => x.title)).toEqual(["Needs you", "Helps in the moment", "Can wait", "Information"]);
    const needs = g[0].rows;
    expect(needs.filter((r) => r.fixed).map((r) => r.type)).toEqual(["kill_engaged", "injection_pause", "irreversible_decision"]);
    expect(needs.some((r) => r.cls === "time" && !r.fixed)).toBe(true);
    expect(g.flatMap((x) => x.rows)).toHaveLength(settings.types.length);
  });
  it("offers the four modes, loudest first", () => {
    expect(MODES).toEqual(["loud", "normal", "quiet", "digest"]);
  });
  it("says in one plain line what a mode does for a kind, and that safety ignores every mode", () => {
    expect(modeLine("time", "loud")).toMatch(/10 minutes/);
    expect(modeLine("time", "normal")).toMatch(/20 minutes/);
    expect(modeLine("now", "quiet")).toMatch(/No offers/);
    expect(modeLine("wait", "digest")).toBe("A summary only.");
    expect(modeLine("safety", "loud")).toMatch(/Always shown once/);
    expect(modeLine("safety", "quiet")).toBe(modeLine("safety", "digest"));
  });
  it("labels every kind the engine lists in words, with no raw identifier left", () => {
    for (const t of settings.types) { const l = typeLabel(t.type); expect(l).not.toMatch(/_/); expect(l.length).toBeGreaterThan(8); }
    expect(typeLabel("some_new_kind")).toBe("Some new kind");
  });
  it("changes one mode at a time, keeps only non-default entries, and never changes a safety row", () => {
    const quiet = withMode(settings, "routine_proposal", "quiet");
    expect(quiet.modes).toEqual({ routine_proposal: "quiet" });
    expect(quiet.types.find((t) => t.type === "routine_proposal")?.mode).toBe("quiet");
    expect(withMode(quiet, "routine_proposal", "normal").modes).toEqual({});
    const refused = withMode(settings, "kill_engaged", "quiet");
    expect(refused).toBe(settings);
    expect(withMode(settings, "no_such_kind", "quiet")).toBe(settings);
  });
  it("keeps the budget between 0 and 40 and says what it means", () => {
    expect(clampBudget(-3)).toBe(0);
    expect(clampBudget(99)).toBe(40);
    expect(clampBudget(12.6)).toBe(13);
    expect(clampBudget(Number.NaN)).toBe(10);
    expect(budgetWords(0)).toMatch(/everything that can wait goes into the summary/);
    expect(budgetWords(1)).toMatch(/Up to 1 notice a day/);
    expect(budgetWords(10)).toMatch(/Up to 10 notices a day/);
    expect(BUDGET_FLOOR).toMatch(/Safety stops and approvals that block a job always stay visible/);
  });
});

describe("today strip", () => {
  it("counts shown, held and dropped from the engine's keys and says why in the engine's words", () => {
    const t = todaySummary(digest.today);
    expect(t).toMatchObject({ shown: 2, held: 2, dropped: 4 });
    const typing = t.lines.find((l) => l.code === "held_typing")!;
    expect(typing.text).toBe("Held because you were typing. Shown at your next pause.");
    expect(t.lines[0].state).toBe("shown");
    expect(t.lines.map((l) => l.state)).toEqual(["shown", "held", "dropped", "dropped"]);
    expect(todayHeadline(t, { used: 2, per_day: 10 })).toBe("Today: 2 shown, 2 held, 4 dropped. 2 of 10 interrupting notices used.");
  });
  it("is empty and calm when nothing happened, and ignores junk", () => {
    expect(todaySummary({})).toEqual({ shown: 0, held: 0, dropped: 0, lines: [] });
    expect(todaySummary(undefined).lines).toEqual([]);
    expect(todaySummary({ "dropped:dropped_flow": 0, "held:held_dnd": Number.NaN }).lines).toEqual([]);
  });
  it("gives an unknown reason a plain fallback instead of a code", () => {
    expect(reasonText("dropped_something_new")).toBe("No reason was recorded.");
    expect(todaySummary({ "held:held_something_new": 1 }).lines[0].text).toBe("No reason was recorded.");
  });
});

describe("what was learned and the banner", () => {
  it("writes learned quieting in one sentence and says it only ever makes a kind quieter", () => {
    const l = learnedLines(settings.learned);
    expect(l).toHaveLength(1);
    expect(l[0].text).toMatch(/“A routine it could run for you” is quieter than usual: from 9 reactions; especially around 14:00, 15:00; 1 thing you chose never for\./);
    expect(learnedLines({})).toEqual([]);
    expect(learnedLines(undefined)).toEqual([]);
  });
  it("shows the banner only when something is waiting or a summary is ready, and never for the stopped state", () => {
    expect(bannerReading({ needs_you: 0, waiting: 0, marker: "none", stopped: false }, false).show).toBe(false);
    expect(bannerReading(null, false).show).toBe(false);
    const w = bannerReading({ needs_you: 1, waiting: 4, marker: "needs_you", stopped: false }, false);
    expect(w).toEqual({ show: true, text: "1 needs you, 3 are waiting", summary: false });
    expect(bannerReading({ needs_you: 0, waiting: 1, marker: "none", stopped: false }, false).text).toBe("1 is waiting");
    expect(bannerReading({ needs_you: 0, waiting: 0, marker: "stopped", stopped: true }, false).show).toBe(false);
    const s = bannerReading({ needs_you: 0, waiting: 0, marker: "none", stopped: false }, true);
    expect(s).toEqual({ show: true, text: "", summary: true });
  });
});
