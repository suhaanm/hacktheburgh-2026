// First run, pure (docs/KNACK_UX.md section 8, docs/knack-ux/07-first-run.md): three screens, one click each, no text field.
//   1. "What work do you do?"  a role card (a pack is a card). Choosing one advances.
//   2. "Let Knack learn from your work?"  Yes, learn my times / Not now / Never, with equal weight. The answer writes the memory file with the
//      role pack's safe defaults.
//   3. "Here is what Knack will remember."  four plain lines from what was just written, then "Show my week".
// The questions the old set-up asked (tools, risky actions, tone, pace, hours) take the pack's defaults and stay editable in Your data.
import { daysText } from "../../lib/memoryPreview";
import { normDays } from "../../lib/days";
import type { OnboardingAnswers, OnboardingQuestions, Pack } from "../../types";

/** Remembered on this device once the three screens are done (an internal identifier, so it keeps its old prefix). */
export const FIRST_RUN_KEY = "understudy-first-run-done";
/** What the worker said to the one consent: "yes", "never", or "not-now:<ISO time>" (asked again after a week, once). Read by Your data. */
export const CAPTURE_CHOICE_KEY = "understudy-capture-choice";
export const ASK_AGAIN_AFTER_DAYS = 7;

export type Step = "role" | "capture" | "ready";
export type CaptureChoice = "yes" | "not-now" | "never";
export const STEPS: Step[] = ["role", "capture", "ready"];

export interface FirstRunState {
  step: Step;
  role: string | null;
  capture: CaptureChoice | null;
  /** True while the memory file is being written (between click 2 and screen 3). */
  writing: boolean;
  error: string | null;
}
export const START: FirstRunState = { step: "role", role: null, capture: null, writing: false, error: null };

export type FirstRunAction =
  | { type: "choose-role"; role: string }
  | { type: "choose-capture"; choice: CaptureChoice }
  | { type: "written" }
  | { type: "failed"; message: string }
  | { type: "back" };

/** Every transition. A click advances one screen; nothing needs typing; Back is the only way to go the other way. */
export function reduce(s: FirstRunState, a: FirstRunAction): FirstRunState {
  switch (a.type) {
    case "choose-role":
      return s.step === "role" ? { ...s, step: "capture", role: a.role, error: null } : s;
    case "choose-capture":
      return s.step === "capture" && !s.writing ? { ...s, capture: a.choice, writing: true, error: null } : s;
    case "written":
      return s.step === "capture" && s.writing ? { ...s, step: "ready", writing: false } : s;
    case "failed":
      return s.step === "capture" ? { ...s, writing: false, capture: null, error: a.message } : s;
    case "back":
      return s.step === "capture" && !s.writing ? { ...START } : s;
  }
}

/** Clicks from the first screen to Home: the role, the one consent, "Show my week". */
export const CLICKS_TO_HOME = 3;
/** With the connections slot filled, choosing a role opens its chips and needs one more click (Continue). */
export const CLICKS_WITH_CONNECTIONS = CLICKS_TO_HOME + 1;

/** The pack's safe defaults: its pre-selected tools, risky actions set to "never without me", the pack's tone, a gradual pace, the pack's hours. Capture only when the worker said yes. */
export function defaultAnswers(data: OnboardingQuestions, capture: boolean): OnboardingAnswers {
  const opts = (id: string) => data.questions.find((x) => x.id === id)?.options ?? [];
  const flagged = (id: string) => opts(id).filter((o) => o.default).map((o) => o.value);
  const risky = flagged("risky").length ? flagged("risky") : opts("risky").map((o) => o.value);
  const dh = data.questions.find((x) => x.id === "hours")?.default_hours;
  const hours = dh ? { start: dh.start, end: dh.end, days: normDays(dh.days) } : { start: "09:00", end: "17:30", days: [0, 1, 2, 3, 4] };
  const pace = opts("pace").find((o) => o.default)?.value ?? (opts("pace").some((o) => o.value === "gradual") ? "gradual" : opts("pace")[Math.floor(opts("pace").length / 2)]?.value ?? "gradual");
  const tools = flagged("tools").length ? flagged("tools") : opts("tools").map((o) => o.value);
  return { tools, risky, tone: data.pack.tone_defaults.length, pace, hours, capture };
}

const label = (q: OnboardingQuestions, id: string, v: string) => q.questions.find((x) => x.id === id)?.options.find((o) => o.value === v)?.label ?? v;
const lower = (s: string) => s.charAt(0).toLowerCase() + s.slice(1);

/** Four plain sentences about what was written (not Markdown, no file path, no revision number). */
export function readyLines(q: OnboardingQuestions, a: OnboardingAnswers): string[] {
  const tone = a.tone === "short" ? "Short summaries" : a.tone === "long" ? "Full summaries" : "Summaries as the role usually keeps them";
  const lines = [`${tone}, ${q.pack.tone_defaults.voice} voice`, `Usual hours ${a.hours.start} to ${a.hours.end}, ${daysText(a.hours.days)}`];
  if (a.risky.length) lines.push(`Never without asking: ${a.risky.map((r) => lower(label(q, "risky", r))).join(", ")}`);
  else lines.push("Never without asking: anything that cannot be undone");
  lines.push(a.tools.length ? `Tools: ${a.tools.map((t) => lower(label(q, "tools", t))).join(", ")}` : "Tools: none chosen yet");
  return lines;
}

/** The one line under a role's name: its summary cut at the first " for ", " and ", " that " or " to ", at most four words ("Runs entitlement checks"). */
export function cardLine(summary: string): string {
  const first = summary.split(/(?<=[.!?])\s/)[0].replace(/[.!?]$/, "");
  const cut = first.split(/,| (?:for|and|that|to) /)[0];
  return cut.split(/\s+/).filter(Boolean).slice(0, 4).join(" ");
}

/** The role cards: at most five, a pack each. */
export function roleCards(packs: Pack[]): { id: string; name: string; line: string }[] {
  return packs.slice(0, 5).map((p) => ({ id: p.id, name: p.name, line: cardLine(p.summary) }));
}

/** What to remember about the consent, as one string for localStorage. */
export function captureRecord(choice: CaptureChoice, now = new Date()): string {
  return choice === "not-now" ? `not-now:${now.toISOString()}` : choice;
}

/** Whether a stored "Not now" is a week old, so Knack may ask once more. "Never" and "yes" never ask again. */
export function mayAskAgain(stored: string | null, now = new Date()): boolean {
  if (!stored?.startsWith("not-now:")) return false;
  const t = Date.parse(stored.slice("not-now:".length));
  return Number.isFinite(t) && now.getTime() - t >= ASK_AGAIN_AFTER_DAYS * 86_400_000;
}

export interface FirstRunGate {
  engineUp: boolean | null;
  extReady: boolean;
  role: string | null;
  person: string | null;
  done: boolean;
  path: string;
  /** The raw hash, to tell "nothing named" from an explicit /home. */
  hash: string;
  /** The route's query string. Anything in it (a settings deep link, a story) is a deep link and is never hijacked. */
  query?: string;
}

/**
 * Open first run by itself only when everything says it is the first time: the engine answered, it does not know this worker, set-up was never
 * finished here, and the address names Home or nothing (a deep link is never hijacked). Never when the engine cannot be reached.
 */
export function shouldStartFirstRun(g: FirstRunGate): boolean {
  if (!g.extReady || g.engineUp !== true) return false;
  if (g.done || g.role || g.person) return false;
  if (g.query) return false;
  const named = g.hash.replace(/^#\/?/, "");
  return (named === "" || g.path === "/home") && g.path !== "/first-run" && g.path !== "/setup";
}
