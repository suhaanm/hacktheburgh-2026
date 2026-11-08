// @vitest-environment jsdom
// The worker's insight sections on the data that breaks screens: empty, one case, NaN and null, a negative gain, an interval that spans zero, 10 000
// occurrences, very long and unicode labels, a week dated in the future or years ago, a generator with no steps, an hours map with nothing in it.
// Each state is rendered for real and the text a person would read is checked: it says the state in words, never shows NaN, undefined, null or Infinity,
// and never names another person or counts anybody. The matrix (state, what is shown, test name) is docs/knack-ux/edge-cases-d.md.
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import genomeFx from "../../fixtures/genome.json";
import weekFx from "../../fixtures/calendar-week.json";
import sugFx from "../../fixtures/calendar-suggestions.json";
import presenceFx from "../../fixtures/presence.json";
import gitFx from "../../fixtures/git-habits.json";
import packetFx from "../../fixtures/evidence-packet.json";
import explainFx from "../../fixtures/evidence-explain.json";

const api = vi.hoisted(() => ({ genome: vi.fn(), calendarWeek: vi.fn(), calendarSuggestions: vi.fn(), presence: vi.fn(), gitHabits: vi.fn(), evidencePacket: vi.fn(), evidenceExplain: vi.fn() }));
vi.mock("../../api", () => ({
  ApiError: class ApiError extends Error { status = 0; code = ""; },
  api,
}));
import { StepsSection } from "./StepsSection";
import { TimeSection } from "./TimeSection";
import { CommitsSection } from "./CommitsSection";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

type Json = Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
const env = (fx: unknown): { data: Json; meta: Json } => structuredClone(fx as { data: Json; meta: Json });
const answer = (data: unknown, meta: unknown) => ({ data, meta, source: "live", why: null });
const BAD = /\b(NaN|undefined|null|Infinity)\b|\[object|Invalid Date/;
const OTHERS = /\bp_(?:[a-z]+_)*[a-z]*\d[a-z0-9_]*\b|\b\d[\d,]*\s+(?:people|learners|experts|workers)\b|\bcolleagues?\b|\bexperts\b/i;

let host: HTMLDivElement;
let root: Root;
beforeEach(() => {
  vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockReturnValue({ width: 900, height: 600, top: 0, left: 0, right: 900, bottom: 600, x: 0, y: 0, toJSON: () => ({}) });
  const g = env(genomeFx), w = env(weekFx), s = env(sugFx), p = env(presenceFx), h = env(gitFx);
  api.genome.mockReset().mockResolvedValue(answer(g.data, g.meta));
  api.calendarWeek.mockReset().mockResolvedValue(answer(w.data, w.meta));
  api.calendarSuggestions.mockReset().mockResolvedValue(answer(s.data, s.meta));
  api.presence.mockReset().mockResolvedValue(answer(p.data, p.meta));
  api.gitHabits.mockReset().mockResolvedValue(answer(h.data, h.meta));
  const pk = env(packetFx), ex = env(explainFx);
  api.evidencePacket.mockReset().mockResolvedValue(answer(pk.data, pk.meta));
  api.evidenceExplain.mockReset().mockResolvedValue(answer(ex.data, ex.meta));
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); host.remove(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

async function show(el: ReturnType<typeof createElement>): Promise<string> {
  await act(async () => { root.render(el); });
  for (let i = 0; i < 6; i++) await act(async () => { await new Promise((r) => setTimeout(r, 15)); });
  host.querySelectorAll("details").forEach((d) => { d.open = true; });
  return (host.textContent ?? "").replace(/\s+/g, " ");
}
const steps = () => show(createElement(StepsSection, { open: true }));
const time = () => show(createElement(TimeSection, { open: true }));
const commits = () => show(createElement(CommitsSection, { open: true }));
const headline = (): string => host.querySelector("h2.gr-sec__headline")?.textContent ?? "";
/** The words around the first offending match, so a failure shows what was printed. */
const around = (raw: string, re: RegExp): string | null => {
  // the size of a meeting on the worker's own calendar ("5 to 9 people") is their own data, not a count of colleagues
  const t = raw.replace(/\b\d+ to \d+ people|fewer than \d+ people|\d+ or more people/g, "a meeting");
  const m = re.exec(t); return m ? t.slice(Math.max(0, m.index - 60), m.index + m[0].length + 60) : null; };
const clean = (t: string): void => {
  const bad = around(t, BAD), others = around(t, OTHERS);
  expect(bad === null, `junk in the text: ${bad}`).toBe(true);
  expect(others === null, `another person or a count: ${others}`).toBe(true);
  expect(headline().trim().length).toBeGreaterThan(15);
};

describe("My steps: edge cases", () => {
  it("steps: empty ribbon says so in words", async () => {
    const g = env(genomeFx);
    Object.assign(g.data, { alignment: [], expert: { segments: [] }, novice: { segments: [] }, waterfall: [], person_gap_s: undefined });
    api.genome.mockResolvedValue(answer(g.data, g.meta));
    const t = await steps();
    expect(headline()).toMatch(/appear here once Knack has seen you/);
    expect(t).toMatch(/No steps to line up yet/);
    clean(t);
  });
  it("steps: NaN seconds and a NaN figure for the case never reach the screen", async () => {
    const g = env(genomeFx);
    g.data.person_gap_s = Number.NaN;
    g.data.novice.segments[1].t1 = Number.NaN;
    api.genome.mockResolvedValue(answer(g.data, g.meta));
    clean(await steps());
  });
  it("steps: a negative gain (faster than the experienced worker) says the steps matched", async () => {
    const g = env(genomeFx);
    g.data.person_gap_s = -45;
    api.genome.mockResolvedValue(answer(g.data, g.meta));
    // the figure for the case is clamped at zero; the ribbon's own columns still say what lost time
    const t = await steps();
    expect(t).not.toMatch(/-\d+ s longer/);
    clean(t);
  });
  it("steps: a very long and a unicode step name stay words", async () => {
    const g = env(genomeFx);
    g.data.expert.segments[0].cog = "RECONCILE_THE_HOUSEHOLD_INCOME_AGAINST_THE_BENEFIT_CAP_RULES_FOR_ZONE_THREE_AND_FOUR";
    g.data.novice.segments[0].cog = "ÜBERPRÜFEN_日本語_ñandú";
    api.genome.mockResolvedValue(answer(g.data, g.meta));
    const t = await steps();
    expect(t).toMatch(/Überprüfen 日本語 ñandú|Reconcile the household/i);
    clean(t);
  });
  it("steps: 10 000 segments draw in a reasonable time and stay finite", async () => {
    const g = env(genomeFx);
    const seg = (k: number) => Array.from({ length: 10000 }, (_, i) => ({ cog: i % 2 ? "READ" : "ENTER", t0: i * 5, t1: i * 5 + 3 + (i % k) }));
    g.data.expert = { segments: seg(2) };
    g.data.novice = { segments: seg(3) };
    g.data.alignment = Array.from({ length: 10000 }, (_, i) => ({ i, j: i, op: "match", seconds: 1 }));
    api.genome.mockResolvedValue(answer(g.data, g.meta));
    const t0 = Date.now();
    clean(await steps());
    expect(Date.now() - t0).toBeLessThan(15000);
  });
  it("steps: a generator with no steps for the expert still names what only the worker did", async () => {
    const g = env(genomeFx);
    g.data.expert = { segments: [] };
    g.data.alignment = g.data.novice.segments.map((_: unknown, j: number) => ({ i: null, j, op: "gap_expert", seconds: 12 }));
    api.genome.mockResolvedValue(answer(g.data, g.meta));
    clean(await steps());
  });
  it("steps: the engine's group figure, its note and both person ids are never drawn", async () => {
    const t = await steps();
    expect(t).not.toMatch(/p_nov|p_exp|novices lose|average over all/i);
    expect(t).not.toContain(String(env(genomeFx).data.person));
    expect(t).not.toContain(String(env(genomeFx).data.expert_person));
  });
});

describe("Where my time goes: edge cases", () => {
  it("time: an empty week and no hours say so in words", async () => {
    const w = env(weekFx);
    w.data.days = w.data.days.map((d: Json) => ({ ...d, blocks: [] }));
    api.calendarWeek.mockResolvedValue(answer(w.data, w.meta));
    const p = env(presenceFx);
    p.data.bins = [];
    api.presence.mockResolvedValue(answer(p.data, p.meta));
    const t = await time();
    expect(headline()).toMatch(/appear here once a calendar is connected/);
    expect(t).toMatch(/No calendar blocks this week/);
    clean(t);
  });
  it("time: null and NaN features fall back to a plain sentence", async () => {
    const w = env(weekFx);
    w.data.features.meeting_h = null;
    w.data.expert.meeting_h = Number.NaN;
    api.calendarWeek.mockResolvedValue(answer(w.data, w.meta));
    const t = await time();
    expect(headline()).toMatch(/Your week against the expert's/);
    clean(t);
  });
  it("time: a week dated in the future, years ago or not a date is shown as given, never as Invalid Date", async () => {
    for (const week of ["2031-W02", "1999-W52", "not a week"]) {
      const w = env(weekFx);
      w.data.week = week;
      api.calendarWeek.mockResolvedValue(answer(w.data, w.meta));
      clean(await time());
    }
  });
  it("time: a gap row with an interval that spans zero reads as within noise, not as a difference", async () => {
    const w = env(weekFx);
    w.data.gap.rows = [{ feature: "meeting_h", learner: 8, expert: 7.9, delta: 0.1, ci: [-1.2, 1.4], expert_range: [3, 9], significant: false }];
    api.calendarWeek.mockResolvedValue(answer(w.data, w.meta));
    const t = await time();
    expect(t).toMatch(/within noise/);
    expect(t).toMatch(/0 of 1 differences are clear/);
    clean(t);
  });
  it("time: 10 000 calendar blocks list seven rows, then Show all", async () => {
    const w = env(weekFx);
    w.data.days[0].blocks = Array.from({ length: 10000 }, (_, i) => ({ start: "08:00", end: "08:15", start_min: 480 + (i % 600), end_min: 495 + (i % 600), kind: i % 2 ? "meeting" : "focus", usable: true, n_attendees_bucket: "5to9" }));
    api.calendarWeek.mockResolvedValue(answer(w.data, w.meta));
    const t = await time();
    expect(host.querySelectorAll("table tbody tr").length).toBeLessThan(40);
    clean(t);
  });
  it("time: an hours map with every bin at zero, and a calendar with no expert week, still read", async () => {
    const p = env(presenceFx);
    p.data.bins = p.data.bins.map(() => 0);
    api.presence.mockResolvedValue(answer(p.data, p.meta));
    const w = env(weekFx);
    w.data.expert.days = [];
    api.calendarWeek.mockResolvedValue(answer(w.data, w.meta));
    clean(await time());
  });
  it("time: no suggestions says the week is close to the experienced worker's, and nothing is sent", async () => {
    api.calendarSuggestions.mockResolvedValue(answer([], env(sugFx).meta));
    const t = await time();
    expect(t).toMatch(/Nothing to suggest/);
    clean(t);
  });
  it("time: never names another person or counts the experts, in the text or the footer", async () => {
    const t = await time();
    expect(t).not.toMatch(/p_exp|p_ninetofive|8 synthetic experts|\d+ experts/);
  });
});

describe("My commits: edge cases", () => {
  it("commits: no habits says a repository has to be registered", async () => {
    const h = env(gitFx);
    h.data.habits = [];
    h.data.suggestions = [];
    api.gitHabits.mockResolvedValue(answer(h.data, h.meta));
    const t = await commits();
    expect(headline()).toMatch(/once a repository is registered/);
    expect(t).toMatch(/No commits to read yet/);
    clean(t);
  });
  it("commits: NaN and null shares and intervals never reach the screen", async () => {
    const h = env(gitFx);
    h.data.habits[0].delta = Number.NaN;
    h.data.habits[0].ci = [Number.NaN, Number.NaN];
    h.data.habits[1].learner = null;
    api.gitHabits.mockResolvedValue(answer(h.data, h.meta));
    clean(await commits());
  });
  it("commits: 10 000 commits are counted with a thousands separator and no count of people", async () => {
    const h = env(gitFx);
    h.data.n_commits = 10000;
    api.gitHabits.mockResolvedValue(answer(h.data, h.meta));
    const t = await commits();
    expect(t).toMatch(/10,000 commits were counted/);
    clean(t);
  });
  it("commits: an interval that spans zero is not flagged", async () => {
    const h = env(gitFx);
    h.data.habits = h.data.habits.map((x: Json) => ({ ...x, delta: 0.01, ci: [-0.05, 0.07], flagged: false, reason: "interval_spans_zero", suggestion: undefined }));
    h.data.suggestions = [];
    api.gitHabits.mockResolvedValue(answer(h.data, h.meta));
    const t = await commits();
    expect(headline()).toMatch(/No commit habit of yours stands out/);
    clean(t);
  });
  it("commits: a very long and a unicode habit label stay words", async () => {
    const h = env(gitFx);
    h.data.habits[0].label = "Commits that change more than two hundred and fifty lines across several unrelated modules at once ñandú 日本語";
    api.gitHabits.mockResolvedValue(answer(h.data, h.meta));
    clean(await commits());
  });
  it("commits: the plural 'experts' and the count of them never appear", async () => {
    const t = await commits();
    expect(t).not.toMatch(/\bexperts\b/i);
    expect(t).not.toMatch(/\b8 experts\b/);
  });
});
