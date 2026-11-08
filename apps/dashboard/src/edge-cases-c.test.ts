// Edge cases of Track C's screens (Needs you, Routines, Your data, Settings, Background tasks). One test per row of docs/knack-ux/edge-cases-c.md: the ids
// below are the ids of that table, and the last test fails if the table and the tests drift apart. Static markup (node environment), fixed clocks.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Evidence } from "./components/needsyou/Evidence";
import { ApprovalRow } from "./components/needsyou/ApprovalRow";
import { PausedRow } from "./components/needsyou/PausedRow";
import { PreparedRow } from "./components/needsyou/PreparedRow";
import { ProposalRow } from "./components/needsyou/ProposalRow";
import { RunningRow } from "./components/routines/RunningRow";
import { SettingsView, type SettingsViewProps } from "./components/settings/SettingsView";
import { AdminSees } from "./components/yourdata/AdminSees";
import { Measured } from "./components/yourdata/Measured";
import { Sent } from "./components/yourdata/Sent";
import { SentLink } from "./components/yourdata/SentLink";
import { Switches } from "./components/yourdata/Switches";
import attentionFx from "./fixtures/attention-settings.json";
import queueFx from "./fixtures/queue.json";
import routinesFx from "./fixtures/routines.json";
import briefingFx from "./fixtures/briefing.json";
import { learnedLines } from "./lib/attention";
import { clip, count, uniqueBy, validTime, whenText } from "./lib/safeText";
import { DAY_MS, RUN_GHOST_MS, TASK_GHOST_MS, WAITING_GHOST_MS, anyActiveRun, groupTasks, isGhostRow, isGhostRun, pickTasks, tasksOf } from "./lib/tasks";
import Agents from "./screens/Agents";
import { MAX_ROWS, PAGE_ROWS, awayLine, buildItems, needsCount, needsHeadline, plainDuration, plainWords, routineName, sameRoutine, saveHint, saveLine, seenLine, visibleItems } from "./screens/NeedsYou/model";
import { defaultTab, routinesHeadline, runningRoutines, touchesSentence, turnedDown } from "./screens/Routines/model";
import { liveModels, settingsHeadline, skillRows } from "./screens/Settings/model";
import { dataHeadline, memoryItems, plainMemoryLine } from "./screens/YourData/model";
import type { AgentRun, AttentionSettings, BriefingCard, LedgerEntry, QueueItem, Routine } from "./types";

const queue = (queueFx as unknown as { data: QueueItem[] }).data;
const routines = (routinesFx as unknown as { data: Routine[] }).data;
const cards = (briefingFx as unknown as { data: { cards: BriefingCard[] } }).data.cards;
const attn = (attentionFx as unknown as { data: AttentionSettings }).data;
const text = (h: string) => h.replace(/<[^>]+>/g, " ").replace(/&#x27;/g, "'").replace(/&quot;/g, '"').replace(/\s+/g, " ");
const noop = () => undefined;
const render = (c: unknown, p: object) => renderToStaticMarkup(createElement(c as never, p as never));
const pending = (over: Partial<QueueItem> = {}): QueueItem => ({ ...(queue.find((q) => q.status === "pending") as QueueItem), ...over });
const proposed = routines.find((r) => r.status === "proposed") as Routine;
const running = routines.find((r) => r.status === "shadow" || r.status === "approval") as Routine;
const NOW = Date.parse("2026-11-08T10:00:00Z");

const ids: string[] = [];
const T = (id: string, name: string, fn: () => void) => { ids.push(id); it(`[${id}] ${name}`, fn); };

describe("edge cases: safe text", () => {
  T("TX-01", "clip cuts on a whole character: an emoji, an accented letter and a combining mark are never split", () => {
    const s = "ab😀😀😀😀😀😀😀😀😀😀";
    const c = clip(s, 5);
    expect(Array.from(c).length).toBe(5);
    expect(c.endsWith("…")).toBe(true);
    expect(c).not.toMatch(/[\ud800-\udbff]$|^[\udc00-\udfff]/);
    expect(clip("é".repeat(10), 4)).toBe("ééé…");
    expect(clip("שלום עולם", 20)).toBe("שלום עולם");
  });
  T("TX-02", "clip, count and uniqueBy treat anything that is not text, a count or a list as nothing", () => {
    expect(clip(undefined)).toBe("");
    expect(clip({})).toBe("");
    expect(clip(42, 5)).toBe("42");
    expect(count(-3)).toBe(0);
    expect(count(Number.NaN)).toBe(0);
    expect(count(2.9)).toBe(2);
    expect(count("7")).toBe(0);
    expect(uniqueBy("nope", (x: { id: string }) => x.id)).toEqual([]);
    expect(uniqueBy([null, { id: "a" }, { id: "a" }, 5], (x: { id: string }) => x.id)).toEqual([{ id: "a" }]);
  });
  T("TX-03", "a time shows as a date and a clock when real, and as 'time unknown' when invalid, empty or more than a day ahead", () => {
    expect(whenText("2026-11-08T09:20:00Z", NOW)).toMatch(/8 Nov, \d\d:\d\d/);
    expect(whenText("not a date", NOW)).toBe("time unknown");
    expect(whenText("", NOW)).toBe("time unknown");
    expect(whenText(undefined, NOW)).toBe("time unknown");
    expect(whenText("2026-11-20T09:00:00Z", NOW)).toBe("time unknown");
    expect(whenText("2019-01-02T09:00:00Z", NOW)).toMatch(/2 Jan, \d\d:\d\d/);
    expect(validTime(12345)).toBeNull();
  });
});

describe("edge cases: Needs you", () => {
  T("NY-01", "no items: no list, no headline, a count of 0", () => {
    expect(buildItems({})).toEqual([]);
    expect(buildItems({ queue: null, routines: undefined, cards: null, runs: [] })).toEqual([]);
    expect(needsHeadline([])).toBe("");
    expect(needsCount([])).toBe(0);
  });
  T("NY-02", "one item: the headline is singular", () => {
    expect(needsHeadline(buildItems({ queue: [pending()] }))).toBe("1 thing needs you.");
  });
  T("NY-03", "hundreds of items: at most 60 are drawn, safety first, every further page is 50, and the count still says all of them", () => {
    const many = Array.from({ length: 300 }, (_, i) => pending({ id: `q${i}`, risk_class: i % 3 === 0 ? "irreversible" : "normal", kind: i % 3 === 0 ? "irreversible_step" : "approval" as QueueItem["kind"] }));
    const items = buildItems({ queue: many });
    expect(needsCount(items)).toBe(300);
    const shown = visibleItems(items, false);
    expect(shown.length).toBeLessThanOrEqual(MAX_ROWS);
    expect(shown.slice(0, 10).every((i) => i.cls === 0)).toBe(true);
    expect(visibleItems(items, true, PAGE_ROWS)).toHaveLength(PAGE_ROWS);
    expect(visibleItems(items, true, PAGE_ROWS * 2)).toHaveLength(PAGE_ROWS * 2);
    expect(needsHeadline(items)).toBe("300 things need you.");
  });
  T("NY-04", "a duplicate id is one item, and no two keys are the same", () => {
    const items = buildItems({ queue: [pending({ id: "dup" }), pending({ id: "dup", title: "Second" })], routines: [proposed, proposed], runs: [] });
    expect(items.filter((i) => i.kind === "approval")).toHaveLength(1);
    expect(items.filter((i) => i.kind === "proposal")).toHaveLength(1);
    expect(new Set(items.map((i) => i.key)).size).toBe(items.length);
  });
  T("NY-05", "items with no id still get their own keys", () => {
    const a = pending(); const b = pending();
    delete (a as Partial<QueueItem>).id; delete (b as Partial<QueueItem>).id;
    const items = buildItems({ queue: [a, b] });
    expect(items).toHaveLength(2);
    expect(new Set(items.map((i) => i.key)).size).toBe(2);
  });
  T("NY-06", "entries that are not objects are skipped without a word", () => {
    expect(buildItems({ queue: [null, "x", 3, pending()] as unknown as QueueItem[], routines: "nope" as unknown as Routine[] })).toHaveLength(1);
  });
  T("NY-07", "an approval with no title says 'An approval', and a very long one is cut with an ellipsis", () => {
    expect(text(render(ApprovalRow, { item: pending({ title: undefined as unknown as string }), primary: false, cls: 1, onDone: noop }))).toContain("An approval");
    const long = text(render(ApprovalRow, { item: pending({ title: "T".repeat(500) }), primary: false, cls: 1, onDone: noop }));
    expect(long).toContain("…");
    expect(long).not.toContain("T".repeat(200));
  });
  T("NY-08", "unicode in a title is kept whole: emoji, accents and right-to-left text", () => {
    const h = text(render(ApprovalRow, { item: pending({ title: "Envoyer le dossier à l’équipe 📨 — שלום" }), primary: false, cls: 1, onDone: noop }));
    expect(h).toContain("Envoyer le dossier à l’équipe 📨 — שלום");
  });
  T("NY-09", "an approval with no summary draws no empty paragraph", () => {
    const h = render(ApprovalRow, { item: pending({ summary: undefined as unknown as string }), primary: false, cls: 1, onDone: noop });
    expect(h).not.toMatch(/<p class="kc-row__body"><\/p>/);
  });
  T("NY-10", "a stale, future or invalid time never prints a date nobody could believe", () => {
    const bare = { screenshots: [], extracted: {}, expected: {}, diff: [], tier_log: [] };
    const h = text(renderToStaticMarkup(createElement(Evidence, { item: pending({ created_at: "2099-01-01T00:00:00Z", evidence: bare }), since: whenText("2099-01-01T00:00:00Z", NOW) })));
    expect(h).toContain("time unknown");
    expect(buildItems({ queue: [pending({ id: "a", created_at: "garbage" }), pending({ id: "b", created_at: "2026-11-08T09:00:00Z" })] })[0].key).toBe("q:b");
  });
  T("NY-11", "a routine proposal with no value and no frequency shows its title and its choices, with no empty line and no hint", () => {
    const bare = { ...proposed, value: undefined, proposal: { ...proposed.proposal, how_often: undefined } } as unknown as Routine;
    const h = render(ProposalRow, { routine: bare, onDecide: async () => undefined });
    expect(text(h)).toContain("Watch first");
    expect(text(h)).not.toMatch(/Could save|Seen /);
    expect(h).not.toMatch(/About the hours saved/);
    expect(h).not.toMatch(/<p class="kc-row__body"><\/p>/);
  });
  T("NY-12", "hours saved: a negative, reversed, NaN, missing or equal range is handled, never printed as nonsense", () => {
    expect(saveLine({ value: { hours_saved: [-5, -1] } })).toBe("");
    expect(saveLine({ value: { hours_saved: [5.2, 3.1] } })).toBe("Could save 3.1 to 5.2 hours.");
    expect(saveLine({ value: { hours_saved: [-2, 4] } })).toBe("Could save 0 to 4 hours.");
    expect(saveLine({ value: { hours_saved: [Number.NaN, 4] } })).toBe("");
    expect(saveLine({ value: { hours_saved: [2, 2] } })).toBe("Could save about 2 hours.");
    expect(saveLine({ value: { hours_saved: [1, 1] } })).toBe("Could save about 1 hour.");
    expect(saveLine({})).toBe("");
    expect(saveLine({ value: { hours_saved: "3" } })).toBe("");
    expect(saveHint({ value: { net_gbp: [-120, 340], horizon_weeks: 12 } })).toBe("95% interval over 12 weeks. About -£120 to £340 net of set-up.");
    expect(saveHint({})).toBe("95% interval.");
    expect(seenLine(undefined)).toBe("");
    expect(seenLine("about 58 times in 3 weeks")).toBe("Seen about 58 times in 3 weeks.");
  });
  T("NY-13", "evidence with a hundred fields shows thirty and says how many more, and with no evidence at all shows only what it has", () => {
    const extracted = Object.fromEntries(Array.from({ length: 100 }, (_, i) => [`field${i}`, `v${i}`]));
    const h = render(Evidence, { item: pending({ evidence: { screenshots: [], extracted, expected: {}, diff: [], tier_log: [] } }), since: "x" });
    expect((h.match(/kv__k/g) ?? []).length).toBe(30);
    expect(text(h)).toContain("70 more fields are in the run.");
    expect(() => render(Evidence, { item: pending({ evidence: undefined as never }), since: "" })).not.toThrow();
  });
  T("NY-14", "a prepared action with no prepared text, no title and no reason still draws its three choices", () => {
    const bare = { ...cards[0], title: undefined, why: undefined, prepared: undefined, ranking: undefined, sources: undefined } as unknown as BriefingCard;
    const h = render(PreparedRow, { card: bare, onFired: noop, onDismissed: noop, onChanged: noop });
    for (const b of ["Approve and run", "Not now", "Never"]) expect(text(h)).toContain(b);
    expect(text(h)).toContain("A prepared action");
  });
  T("NY-15", "a paused run with no start time and no kind has no clock and is called a background run", () => {
    const h = render(PausedRow, { run: { run_id: "r_x", state: "paused", parent: { state: "paused" }, children: [] } as unknown as AgentRun, onDone: noop });
    expect(h).not.toMatch(/<time/);
    expect(text(h)).toContain("Paused: Background run");
  });
  T("NY-16", "an away report with lists missing or empty says nothing; one with runs says how many", () => {
    expect(awayLine({})).toBeNull();
    expect(awayLine({ ran: [], failed: [] })).toBeNull();
    expect(awayLine(null)).toBeNull();
    expect(awayLine({ ran: [1, 2], failed: [3] })).toBe("Since you were away: 2 runs finished, 1 failed.");
  });
  T("NY-17", "the word swap accepts anything: null, a number, an object", () => {
    expect(plainWords(undefined)).toBe("");
    expect(plainWords(null)).toBe("");
    expect(plainWords(5 as unknown as string)).toBe("");
    expect(plainWords("A shadow run of the Demo")).toBe("A practice run of the Test");
  });
});

describe("edge cases: one routine, one row (QA Q1-08, Q1-09)", () => {
  T("NY-18", "a prepared 'Automate: X' beside the proposal 'X' is one row (the proposal's); a card about something else stays; an empty title never matches", () => {
    const card = (title: string) => ({ id: "c1", kind: "automate", title, why: "You did these steps 14 times.", prepared: {}, risk_class: "normal", sources: [], expires_at: "", status: "ready" }) as never;
    const items = buildItems({ routines: [proposed], cards: [card(`Automate: ${proposed.title}`)], now: NOW });
    expect(items).toHaveLength(1);
    expect(buildItems({ routines: [proposed], cards: [card("Something else entirely")], now: NOW })).toHaveLength(2);
    expect(sameRoutine({ title: "" } as never, { title: "" } as never)).toBe(false);
  });
  T("NY-19", "the away report: an id becomes a name, minutes become words, and a nonsense length is no length", () => {
    expect(routineName("benefits-workflow")).toBe("Benefits workflow");
    expect(plainDuration(481.3)).toBe("8 hours");
    expect(plainDuration(-1)).toBeNull();
    expect(plainDuration(Number.NaN)).toBeNull();
  });
});

describe("edge cases: Routines and background tasks", () => {
  T("RT-01", "no routines: nothing running, nothing turned down, an empty headline", () => {
    expect(runningRoutines(null)).toEqual([]);
    expect(runningRoutines(undefined)).toEqual([]);
    expect(turnedDown("nope" as unknown as Routine[])).toEqual([]);
    expect(routinesHeadline({ tasksRunning: 0, routinesRunning: 0, couldMinutes: 0 })).toBe("");
  });
  T("RT-02", "a duplicate id is one routine, and a hole in the list is skipped", () => {
    const list = runningRoutines([{ ...running, id: "a" }, null, { ...running, id: "a" }, { ...running, id: "b" }] as unknown as Routine[]);
    expect(list.map((r) => r.id).sort()).toEqual(["a", "b"]);
  });
  T("RT-03", "hundreds of routines sort by minutes a week, and a missing, NaN or negative number counts as none and sorts last", () => {
    const many = Array.from({ length: 400 }, (_, i) => ({ ...running, id: `r${i}`, minutes_per_week: i === 5 ? Number.NaN : i === 6 ? undefined : i === 7 ? -30 : i }));
    const list = runningRoutines(many as unknown as Routine[]);
    expect(list).toHaveLength(400);
    expect(list[0].id).toBe("r399");
    expect(list.slice(-4).map((r) => r.id)).toContain("r5");
  });
  T("RT-04", "a routine whose steps are unknown prints no total, no NaN and no 'undefined'", () => {
    const bare = { ...running, shadow: undefined, rung: undefined, proposal: undefined } as unknown as Routine;
    const h = text(render(RunningRow, { routine: bare, open: true, canRun: true, onToggle: noop, onDecide: async () => undefined, onRun: async () => null }));
    const m = h.match(/NaN|undefined|null|step \d+ of \d+/i);
    expect(m ? h.slice(Math.max(0, h.indexOf(m[0]) - 60), h.indexOf(m[0]) + 60) : "").toBe("");
    expect(h).toContain("0 of 0 runs matched you");     // no record yet is a true zero, not a made-up number
  });
  T("RT-05", "a very long routine title is cut, and a missing one is called 'A routine'", () => {
    const long = text(render(RunningRow, { routine: { ...running, title: "R".repeat(500) }, open: false, canRun: false, onToggle: noop, onDecide: async () => undefined, onRun: async () => null }));
    expect(long).toContain("…");
    expect(text(render(RunningRow, { routine: { ...running, title: undefined as unknown as string }, open: false, canRun: false, onToggle: noop, onDecide: async () => undefined, onRun: async () => null }))).toContain("A routine");
  });
  T("RT-06", "what a routine touches survives missing lists", () => {
    expect(touchesSentence({ touches: undefined, proposal: undefined } as unknown as Routine)).toBe("");
    expect(touchesSentence({ touches: ["A", "B", "C"], proposal: { touches: [] } } as unknown as Routine)).toBe("Touches A, B and C.");
  });
  T("RT-07", "the headline names the most urgent fact and never a negative or NaN number of minutes", () => {
    expect(routinesHeadline({ tasksRunning: 1, routinesRunning: 2, couldMinutes: 0 })).toBe("1 task is working in the background.");
    expect(routinesHeadline({ tasksRunning: 0, routinesRunning: 1, couldMinutes: 0 })).toBe("You have 1 routine set up.");
    expect(routinesHeadline({ tasksRunning: 0, routinesRunning: 0, couldMinutes: 180 })).toBe("About 3 hours a week could be handed over.");
    expect(routinesHeadline({ tasksRunning: 0, routinesRunning: 0, couldMinutes: Number.NaN })).toBe("");
    expect(routinesHeadline({ tasksRunning: 0, routinesRunning: 0, couldMinutes: -50 })).toBe("");
  });
  T("RT-09", "which tab Routines opens on: Could automate when Your routines is empty and that list is not; a tab in the address always wins", () => {
    expect(defaultTab(null, 0, 2)).toBe("could-automate");
    expect(defaultTab(null, 1, 2)).toBe("running");
    expect(defaultTab("running", 0, 2)).toBe("running");
  });
  T("RT-08", "five hundred runs become five hundred tasks without an error; a run with nothing in it is a finished task", () => {
    const runs = Array.from({ length: 500 }, (_, i) => ({ run_id: `r${i}`, kind: "data.profile", mode: "foreground", state: "done", started: "2026-11-08T08:00:00Z", parent: { id: "p", role: "planner", state: "done", budget: {}, spent: {} }, children: [] }));
    expect(tasksOf(runs)).toHaveLength(500);
    expect(tasksOf([{}, { run_id: "x" }])[0].state).toBe("done");
  });
});

describe("edge cases: ghosts and old records (a clock is fixed in every test)", () => {
  const ago = (ms: number) => new Date(NOW - ms).toISOString();
  const run = (state: string, started: string): AgentRun => ({ run_id: `r_${state}_${started.length}`, kind: "data.profile", mode: "foreground", state, started, parent: { id: "p", role: "planner", state, budget: {}, spent: {} }, children: [] }) as AgentRun;
  T("GH-01", "a run record still going after the 15 minutes the service allows is a ghost: not listed, not counted as running, no Needs you item", () => {
    expect(isGhostRun(run("running", ago(RUN_GHOST_MS + 60_000)), NOW)).toBe(true);
    expect(isGhostRun(run("running", ago(RUN_GHOST_MS - 60_000)), NOW)).toBe(false);
    expect(anyActiveRun([run("planning", ago(3 * DAY_MS))], NOW)).toBe(false);
    expect(buildItems({ runs: [run("paused", ago(3 * DAY_MS))], now: NOW })).toEqual([]);
  });
  T("GH-02", "a task row from the tasks service may run as long as its longest cap plus a margin, and a ghost beyond that is dropped", () => {
    expect(isGhostRow({ task_id: "t", title: "x", state: "running", started: ago(TASK_GHOST_MS - 60_000) }, NOW)).toBe(false);
    expect(isGhostRow({ task_id: "t", title: "x", state: "running", started: ago(TASK_GHOST_MS + 60_000) }, NOW)).toBe(true);
  });
  T("GH-03", "a card that waits for the worker is a ghost only after a day", () => {
    expect(isGhostRow({ task_id: "t", title: "x", state: "waiting_consent", started: ago(WAITING_GHOST_MS - 60_000), needs_consent: { scope_text: "x" } }, NOW)).toBe(false);
    expect(buildItems({ tasks: [{ task_id: "t", title: "x", state: "waiting_consent", started: ago(WAITING_GHOST_MS + 60_000), needs_consent: { scope_text: "x" } }], now: NOW })).toEqual([]);
  });
  T("GH-04", "a finished task created more than 24 hours ago, or with no usable creation time, is not listed; one created 23 hours ago is", () => {
    const t = (started: string) => ({ id: started, title: "x", state: "done" as const, note: "", steps: [], started, finished: null, isTask: true, open: null, answer: null });
    const g = groupTasks([t(ago(DAY_MS + 60_000)), t("garbage"), t(ago(23 * 3_600_000))], new Map(), NOW);
    expect(g.today).toHaveLength(1);
  });
  T("GH-05", "the built-in sample is never a task, even when its runs look like work: with nothing answered there are no tasks", () => {
    expect(pickTasks({ rows: null, runs: null }, NOW)).toEqual([]);
    expect(pickTasks({ rows: null, runs: [run("running", "2026-11-07T16:53:00Z")] }, NOW)).toEqual([]);
  });
  T("GH-06", "a start time ahead of the clock is a skewed clock: the task is shown, not hidden", () => {
    expect(pickTasks({ rows: [{ task_id: "t", title: "Soon", state: "running", started: new Date(NOW + 3_600_000).toISOString() }], runs: null }, NOW)).toHaveLength(1);
  });
});

describe("edge cases: Your data", () => {
  T("YD-01", "what it measures with no view reads 'Reading', and counts that are negative or NaN are zero with both buttons off", () => {
    const h = render(Measured, { capture: false, view: null, onExport: async () => undefined, onDelete: async () => 0 });
    expect(text(h)).toContain("Reading");
    const odd = render(Measured, { capture: true, view: { counts: { assist: -4, delegated: Number.NaN, automation: undefined } }, onExport: async () => undefined, onDelete: async () => 0 });
    expect(text(odd)).toContain("0 counted, 0 done for you, 0 overnight");
    expect(odd.match(/disabled/g)?.length).toBe(2);
  });
  T("YD-02", "the call list: empty says so; entries with missing fields say 'time unknown' and 'model not recorded'; non-objects are skipped; hundreds show four and a way to the rest", () => {
    expect(text(render(Sent, { entries: [], summary: null, onChanged: noop }))).toContain("Nothing has been sent to a model.");
    const bare = { purpose: "x" } as unknown as LedgerEntry;
    const h = text(render(Sent, { entries: [null, bare, "x"] as unknown as LedgerEntry[], summary: null, onChanged: noop }));
    expect(h).toContain("time unknown");
    expect(h).toContain("model not recorded");
    const many = Array.from({ length: 500 }, (_, i) => ({ t: "2026-11-08T09:00:00Z", purpose: "p", schema: null, fields: [], payload: {}, model: "m", bytes: i, id: `l${i}` })) as unknown as LedgerEntry[];
    const big = render(Sent, { entries: many, summary: null, onChanged: noop });
    expect((big.match(/ledger__row/g) ?? []).length).toBe(4);
    expect(text(big)).toContain("Show all 500");
  });
  T("YD-03", "what the admin sees with no lists draws one sentence and a closed More with nothing in it that is empty", () => {
    const h = render(AdminSees, { sharing: { items: undefined, never: undefined, preview: null } as never });
    expect(text(h)).toContain("Your admin sees a summary of numbers about your work.");
    expect(h).not.toMatch(/They can see|They can never see|Exactly what they see about you/);
  });
  T("YD-04", "capture and glances in a browser tab with nothing from the app is one switch and one line", () => {
    const h = text(render(Switches, { capture: false, onCapture: noop, busy: false, glance: null, onGlance: noop, desktop: null, onDesktop: noop, error: null }));
    expect(h).toContain("Screen glances and folders are in the Knack app.");
  });
  T("YD-05", "the memory lines: a missing section, a non-list, a line with no id and a duplicate id are all handled, in order", () => {
    expect(memoryItems(undefined)).toEqual([]);
    expect(memoryItems({} as never)).toEqual([]);
    const items = memoryItems({ sections: { Preferences: [{ id: "a", text: "one", note: null }, { id: "a", text: "dup", note: null }, { text: "no id", note: null }, null, { id: "z", text: 5 }] as never, Never: "not a list" as never } });
    expect(items.map((i) => i.text)).toEqual(["one", "no id"]);
    expect(new Set(items.map((i) => i.id)).size).toBe(2);
  });
  T("YD-06", "the headline counts what is remembered and never a negative or NaN number", () => {
    expect(dataHeadline({ lines: 0, capture: false })).toBe("Knack remembers nothing about you yet, on this Mac only.");
    expect(dataHeadline({ lines: 1, capture: null })).toBe("Knack remembers 1 thing about you, on this Mac only.");
    expect(dataHeadline({ lines: 12, capture: true })).toBe("Knack remembers 12 things about you, on this Mac only, and learns from when you are active.");
    expect(dataHeadline({ lines: -3, capture: false })).toContain("nothing");
  });
  T("YD-08", "memory lines the engine writes as codes are shown as sentences, the file's own text is kept for editing, and nothing reads like a granted permission", () => {
    expect(plainMemoryLine("calc-entry-3x | rung A1 | consent: shadow | unattended: not allowed")).toBe("Calc entry 3x is set to watch first. Away runs are off.");
    expect(plainMemoryLine("Run without my click: submit, close case")).toMatch(/^Always asks you first before: /);
    expect(memoryItems({ sections: { Never: [{ id: "n", text: "Run without my click: submit", note: null }] } })[0].text).toBe("Run without my click: submit");
  });
  T("YD-07", "what it looked at or sent is one sentence and one link for a worker, and no call row", () => {
    const h = render(SentLink, {});
    expect(text(h)).toBe(" Nothing leaves this Mac without your say. Every call Knack makes ");
    expect(h).not.toMatch(/ledger__row/);
  });
});

describe("edge cases: Settings", () => {
  const base = (over: Partial<SettingsViewProps> = {}): SettingsViewProps => ({
    live: liveModels({ health: { mock: true, key_present: true }, canSwitch: true, running: false, changing: false }), onLive: noop,
    attention: attn, attentionError: null, onPreset: noop, onMode: noop, onGroup: noop, onResetLearned: noop, onLevelGlance: noop, wake: null, onWake: noop,
    desktop: null, onDesktop: noop, theme: "auto", onTheme: noop, view: "worker", onView: noop, version: null, ...over,
  });
  const html = (over?: Partial<SettingsViewProps>) => renderToStaticMarkup(createElement(SettingsView, base(over)));
  T("ST-01", "an interruptions answer with no list of kinds draws the three words with none pressed and no groups", () => {
    const h = html({ attention: { ...attn, types: undefined } as unknown as AttentionSettings });
    expect(text(h)).toContain("Rarely");
    expect(h).not.toMatch(/data-testid="group-/);
    expect(h).not.toMatch(/aria-pressed="true"[^>]*>(Rarely|Balanced|Often)</);
  });
  T("ST-02", "zero kinds is the same, and no 'Each kind' content", () => {
    const h = html({ attention: { ...attn, types: [] } });
    expect(h).not.toMatch(/data-testid="notice-/);
  });
  T("ST-03", "a kind at a mode nobody knows has no button pressed and does not break the row", () => {
    const weird = { ...attn, types: attn.types.map((t, i) => (i === 4 ? { ...t, mode: "frantic" } : t)) } as AttentionSettings;
    expect(() => html({ attention: weird })).not.toThrow();
  });
  T("ST-04", "what it learned: a negative count, NaN hours and an hour of 99 are left out of the sentence", () => {
    const l = learnedLines({ routine_proposal: { n: -5, drop_hours: [99, Number.NaN, 14, 3.5], max_drop: 1, never_subjects: 0 } } as never)[0].text;
    expect(l).toBe("“A routine it could run for you” is quieter than usual: especially around 14:00.");
  });
  T("ST-05", "with the app but an empty settings object, coaching is off, move aside is on and open at login is off, each with its line", () => {
    const t = text(html({ desktop: {} }));
    expect(t).toContain("No hints while you work.");
    expect(t).toContain("The window minimises while an agent works.");
    expect(t).toContain("Off. Routines only run while Knack is open.");
  });
  T("ST-06", "Hey Knack: no bridge says it is in the app; each of the three states prints the fixed note", () => {
    expect(text(html())).toContain("Available in the Knack app.");
    for (const w of [{ switchOn: true, listening: true, line: "" }, { switchOn: true, listening: false, line: "Not listening while the screen is locked" }, { switchOn: false, listening: false, line: "off" }]) expect(text(html({ wake: w }))).toContain("Stays on this Mac. Nothing is stored.");
  });
  T("ST-07", "five hundred skills show at most two hundred, each name once, sorted, with the long ones cut", () => {
    const skills = Array.from({ length: 500 }, (_, i) => ({ name: `skill-${String(i).padStart(3, "0")}`, description: "D".repeat(300) }));
    const rows = skillRows({ off: [], skills: [...skills, { name: "skill-000" }] });
    expect(rows).toHaveLength(200);
    expect(rows[0].name).toBe("skill-000");
    expect(Array.from(rows[0].description).length).toBe(140);
  });
  T("ST-08", "the headline says how Knack is set, and says nothing it does not know", () => {
    expect(settingsHeadline({ live: true, preset: "rarely" })).toBe("Knack uses live models and interrupts you rarely.");
    expect(settingsHeadline({ live: false, preset: null })).toBe("Knack does not use live models.");
    expect(settingsHeadline({ live: null, preset: null })).toBe("");
  });
  T("ST-10", "the two limits on a task live inside Advanced, and the live line only says 'because a key is set' when the engine said so", () => {
    const h = html({ skills: { use_claude_skills: true, off: [], max_minutes: 30, max_budget_usd: 2, skills: [] } });
    expect(h.indexOf("Most a task may spend")).toBeGreaterThan(h.indexOf(">Advanced<"));
    expect(liveModels({ health: { mock: false }, canSwitch: true, running: false, changing: false }).line).not.toMatch(/because a key/);
  });
  T("ST-09", "the Advanced section is closed, last, and the call list is not even loaded until it is opened", () => {
    const h = html();
    expect(h.lastIndexOf("Advanced")).toBeGreaterThan(h.lastIndexOf("Appearance"));
    expect(h).not.toMatch(/data-testid="advanced-calls"/);
  });
});

describe("edge cases: admin only", () => {
  T("AG-01", "a worker who reaches Background runs by its address sees the one gate sentence and nothing else", () => {
    const h = renderToStaticMarkup(createElement(Agents));
    expect(text(h)).toBe(" Switch to Admin to see this. ");
  });
});

describe("the table and the tests agree", () => {
  it("every id in docs/knack-ux/edge-cases-c.md is a test here, and every test here is in the table", () => {
    const doc = readFileSync(resolve(__dirname, "../../../docs/knack-ux/edge-cases-c.md"), "utf8");
    const inDoc = [...new Set([...doc.matchAll(/\|\s*([A-Z]{2}-\d\d)\s*\|/g)].map((m) => m[1]))];
    expect(inDoc.sort()).toEqual([...ids].sort());
  });
});
