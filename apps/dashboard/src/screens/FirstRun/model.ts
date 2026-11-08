// First run, pure (docs/KNACK_UX.md section 8, docs/knack-ux/07-first-run.md, docs/knack-ux/defaults.md). Three screens, every one with a Skip:
//   1. Role: "What work do you do?" a card per role and "Not sure yet", which picks nothing and can be changed later. A click advances.
//   2. What Knack may do: one card each for capture, screen glances and voice, every card with Yes, Not now and Never of equal weight, none pre-selected.
//      A card exists only where Knack can act on it (glances and voice are the desktop app's). Answering the last card advances.
//   3. Check it works: the macOS permissions as they are (never a wall: each says what will not work without it), Hey Knack's listening state, and "Show me",
//      which draws the annotation ring on a sample. Then "Show my week".
// The role pack's safe defaults are written to the memory file when the second screen is done. Nothing is ever consented to by this file: a consent is a real
// click on a card, recorded by the code that handles the click.
import { depthLabel } from "../../lib/profile";
import { daysText } from "../../lib/memoryPreview";
import { normDays } from "../../lib/days";
import type { OnboardingAnswers, OnboardingQuestions, Pack } from "../../types";

/** Remembered on this device once first run is finished or skipped (an internal identifier, so it keeps its old prefix). */
export const FIRST_RUN_KEY = "understudy-first-run-done";
/** What the worker said to the capture consent: "yes", "never", or "not-now:<ISO time>" (asked again after a week, once). Read by Your data. */
export const CAPTURE_CHOICE_KEY = "understudy-capture-choice";
/** The same for screen glances and for voice. Never is remembered so Knack does not ask again. */
export const GLANCE_CHOICE_KEY = "understudy-glance-choice";
export const VOICE_CHOICE_KEY = "understudy-voice-choice";
/** Where an unfinished first run is kept, so a closed window resumes where it stopped. Cleared when first run ends. */
export const PROGRESS_KEY = "understudy-first-run-progress";
/** Set for the rest of the session once first run has been shown, so Back never traps the worker in it. */
export const SEEN_KEY = "understudy-first-run-seen";
export const ASK_AGAIN_AFTER_DAYS = 7;

export type Step = "role" | "may" | "check";
export const STEPS: Step[] = ["role", "may", "check"];
export type Choice = "yes" | "not-now" | "never";
export type ConsentKind = "capture" | "glance" | "voice";
export const CHOICES: Choice[] = ["yes", "not-now", "never"];
/** The role a worker picks when they are not sure: nothing is written and nothing is chosen for them. */
export const NO_ROLE = "none";

/** Which consent cards exist on this machine: capture always; glances and voice only where the desktop app can act on them. */
export interface Caps { glance: boolean; voice: boolean }
export const kindsFor = (caps: Caps): ConsentKind[] => ["capture", ...(caps.glance ? (["glance"] as const) : []), ...(caps.voice ? (["voice"] as const) : [])];

export interface FirstRunState {
  step: Step;
  /** A pack id, NO_ROLE for "Not sure yet", or null before the choice. */
  role: string | null;
  answers: Partial<Record<ConsentKind, Choice>>;
  /** True while the memory file is being written (between screen 2 and screen 3). */
  writing: boolean;
  /** True once the memory file was written, so going back and forward does not write it twice. */
  written: boolean;
  error: string | null;
}
export const START: FirstRunState = { step: "role", role: null, answers: {}, writing: false, written: false, error: null };

export type FirstRunAction =
  | { type: "choose-role"; role: string }
  | { type: "answer"; kind: ConsentKind; choice: Choice }
  | { type: "advance" }
  | { type: "written" }
  | { type: "failed"; message: string }
  | { type: "back" }
  | { type: "skip" };

/** The first consent card with no answer, or null when every card has one. */
export const nextUnanswered = (s: Pick<FirstRunState, "answers">, caps: Caps): ConsentKind | null => kindsFor(caps).find((k) => !s.answers[k]) ?? null;

/**
 * Every transition. A click advances one screen; nothing needs typing; Back is the only way to go the other way (and not while the file is being
 * written). "advance" leaves the consent screen for the check screen, "skip" does what the Skip link does.
 */
export function reduce(s: FirstRunState, a: FirstRunAction): FirstRunState {
  switch (a.type) {
    case "choose-role":
      return s.step === "role" ? { ...s, step: "may", role: a.role, error: null } : s;
    case "answer":
      return s.step === "may" && !s.writing ? { ...s, answers: { ...s.answers, [a.kind]: a.choice }, error: null } : s;
    case "advance":
      return s.step === "may" && !s.writing ? { ...s, step: "check", writing: !s.written && !!s.role && s.role !== NO_ROLE, error: null } : s;
    case "written":
      return s.writing ? { ...s, writing: false, written: true } : s;
    case "failed":
      return s.writing ? { ...s, step: "may", writing: false, error: a.message } : s;
    case "back":
      if (s.writing) return s;
      return s.step === "check" ? { ...s, step: "may", error: null } : s.step === "may" ? { ...s, step: "role", error: null } : s;
    case "skip":
      if (s.writing) return s;
      return s.step === "role" ? { ...s, step: "may", role: s.role ?? NO_ROLE, error: null } : s.step === "may" ? reduce(s, { type: "advance" }) : s;
  }
}

/**
 * Clicks from the first screen to Home with nothing skipped: the role, one answer per consent card (the last answer advances), and "Show my week".
 * The connection chips, when present, add one (Continue).
 */
export const clicksToHome = (caps: Caps, chips = false): number => 1 + kindsFor(caps).length + 1 + (chips ? 1 : 0);

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

/** Four plain sentences about what was written (not Markdown, no file path, no revision number). Kept for Your data and tests; first run no longer prints it. */
export function readyLines(q: OnboardingQuestions, a: OnboardingAnswers): string[] {
  const tone = a.tone === "short" ? "Short summaries" : a.tone === "long" ? "Full summaries" : "Summaries as the role usually keeps them";
  const lines = [`${tone}, ${q.pack.tone_defaults.voice} voice`, `Usual hours ${a.hours.start} to ${a.hours.end}, ${daysText(a.hours.days)}`];
  if (a.risky.length) lines.push(`Never without asking: ${a.risky.map((r) => lower(label(q, "risky", r))).join(", ")}`);
  else lines.push("Never without asking: anything that cannot be undone");
  lines.push(a.tools.length ? `Tools: ${a.tools.map((t) => lower(label(q, "tools", t))).join(", ")}` : "Tools: none chosen yet");
  return lines;
}

/** The one line under a role's name: its summary cut at the first comma, " for ", " and ", " that " or " to ", at most four words ("Runs entitlement checks"). */
export function cardLine(summary: string): string {
  const first = (summary ?? "").split(/(?<=[.!?])\s/)[0].replace(/[.!?]$/, "");
  const cut = first.split(/,| (?:for|and|that|to) /)[0];
  return cut.split(/\s+/).filter(Boolean).slice(0, 4).join(" ");
}

export interface RoleCard { id: string; name: string; line: string; /** How far the pack is built (depthLabel); empty for Not sure yet. */ tag: string }
/** The role cards: at most four packs, then "Not sure yet" (which picks nothing). */
export function roleCards(packs: Pack[]): RoleCard[] {
  return [...packs.slice(0, 4).map((p) => ({ id: p.id, name: p.name, line: cardLine(p.summary), tag: depthLabel(p.depth) })), { id: NO_ROLE, name: "Not sure yet", line: "Choose later", tag: "" }];
}

/** What to remember about a consent, as one string for localStorage. */
export function captureRecord(choice: Choice, now = new Date()): string {
  return choice === "not-now" ? `not-now:${now.toISOString()}` : choice;
}

/** Whether a stored "Not now" is a week old, so Knack may ask once more. "Never" and "yes" never ask again. */
export function mayAskAgain(stored: string | null, now = new Date()): boolean {
  if (!stored?.startsWith("not-now:")) return false;
  const t = Date.parse(stored.slice("not-now:".length));
  return Number.isFinite(t) && now.getTime() - t >= ASK_AGAIN_AFTER_DAYS * 86_400_000;
}

/* -- The consent cards' words (fixed, printed whole beside the three choices) ------------------------------------------------------ */

export interface ConsentCard { kind: ConsentKind; title: string; text: string }
export const CAPTURE_CARD: ConsentCard = { kind: "capture", title: "Learn from my working times", text: "Records when each step starts and ends, never what you read. Stays on this laptop." };
export const VOICE_CARD: ConsentCard = { kind: "voice", title: "Listen for Hey Knack", text: "Listens on this Mac for those words only and keeps nothing. Talking sends your voice to a model." };
/** One plain sentence, the one that says what leaves the Mac. The desktop app's full consent text is printed under Your data, next to the switch it belongs to. */
export const GLANCE_CARD: ConsentCard = { kind: "glance", title: "Look at my screen when stuck", text: "Sends a small picture of your screen to a model, only then. Never saved." };

/* -- The check screen ---------------------------------------------------------------------------------------------------------------- */

export type PermName = "microphone" | "speech" | "screen";
/** What will not work without a permission, one plain sentence each. Printed beside the permission, never in a Hint. */
export const PERM_COPY: Record<PermName, { title: string; without: string }> = {
  microphone: { title: "Microphone", without: "Without it, Knack cannot hear you." },
  speech: { title: "Speech recognition", without: "Without it, Knack cannot hear Hey Knack." },
  screen: { title: "Screen recording", without: "Without it, Knack cannot look at your screen or point at it." },
};
/** The permission each consent needs: asking for it before the worker said yes would be a prompt out of nowhere. */
export const PERMS_FOR: Record<ConsentKind, PermName[]> = { capture: [], glance: ["screen"], voice: ["microphone", "speech"] };

/** The permissions worth showing: only those a consent the worker answered Yes to needs, plus screen recording when "Show me" can draw the ring. */
export function permsToShow(answers: Partial<Record<ConsentKind, Choice>>, caps: { ring: boolean }): PermName[] {
  const need = new Set<PermName>();
  for (const k of ["glance", "voice"] as const) if (answers[k] === "yes") PERMS_FOR[k].forEach((p) => need.add(p));
  if (caps.ring) need.add("screen");
  return (["microphone", "speech", "screen"] as const).filter((p) => need.has(p));
}

/** The Hey Knack line on the check screen: only in the desktop app (where the shell reports the listener's state), never in a browser tab. Words are fixed. */
export interface HeyKnackRow { title: string; line: string; on: boolean }
export function heyKnackRow(status: { switchOn: boolean; listening: boolean; line: string } | null): HeyKnackRow | null {
  if (!status) return null;
  const note = status.switchOn ? (status.listening ? "Listening. Say Hey Knack." : "On, but not listening yet.") : "Off. Turn it on in Settings.";
  return { title: "Hey Knack", line: status.switchOn && !status.listening && status.line ? `${note} ${status.line}` : note, on: status.switchOn };
}

/**
 * The worker went to System Settings to turn a refused permission on and came back: the listener stays blocked until it is armed again (it never retries a refusal by itself), so
 * the check screen arms it once on return and reads the state again a moment later. Only for the two permissions that System Settings can fix.
 */
export const shouldRearm = (wake: { fix?: string | null } | null): boolean => wake?.fix === "microphone" || wake?.fix === "speech";

/** In a browser tab there is no desktop app to ask macOS or to draw the ring: those rows say so, in these words, and have no button. */
export const NEEDS_APP = "Available in the Knack app.";
export const BROWSER_ROWS: { key: string; title: string }[] = [{ key: "permissions", title: "Permissions" }, { key: "tryit", title: "Show me where Knack points" }];

export const RING_SENTENCE = "Knack points; it never clicks unless you allow it.";

/* -- Progress that survives a closed window ------------------------------------------------------------------------------------------ */

/** What is kept of an unfinished first run: the screen, the role and the answers. Nothing else, and nothing that was not a click. */
export function progressRecord(s: FirstRunState): string {
  return JSON.stringify({ step: s.step, role: s.role, answers: s.answers, written: s.written });
}

/** Read it back, strictly: anything that is not exactly that shape starts first run again from the top. A saved "check" screen resumes at "may" (nothing is half-written). */
export function parseProgress(raw: string | null): FirstRunState | null {
  if (!raw) return null;
  try {
    const o = JSON.parse(raw) as { step?: unknown; role?: unknown; answers?: unknown; written?: unknown };
    if (o.step !== "role" && o.step !== "may" && o.step !== "check") return null;
    if (o.role !== null && typeof o.role !== "string") return null;
    const answers: FirstRunState["answers"] = {};
    for (const k of ["capture", "glance", "voice"] as const) {
      const v = (o.answers as Record<string, unknown> | null | undefined)?.[k];
      if (v === "yes" || v === "not-now" || v === "never") answers[k] = v;
      else if (v !== undefined) return null;
    }
    const step: Step = o.step === "check" ? "may" : o.step;
    if (step !== "role" && !o.role) return null;
    return { ...START, step, role: (o.role as string | null) ?? null, answers, written: o.written === true };
  } catch { return null; }
}

/* -- When first run opens ---------------------------------------------------------------------------------------------------------- */

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
  /** The page is the Knack app (html[data-knack-shell] is set), not a browser tab. */
  inApp?: boolean;
  /** First run was already shown in this session: Back must never trap the worker in it. */
  seen?: boolean;
}

/**
 * In the Knack app first run opens on the first launch on this Mac: whenever the per-device flag is absent, whatever the engine already knows about
 * the worker (a seeded example worker must not skip the role choice). It does not wait for the engine. A browser tab keeps the old rule: only when the
 * engine answered, does not know the worker and nothing was finished here. In both, a deep link is never hijacked and a session that has shown it once does not
 * show it again by itself.
 */
export function shouldStartFirstRun(g: FirstRunGate): boolean {
  if (g.done || g.seen) return false;
  if (g.query) return false;
  const named = g.hash.replace(/^#\/?/, "");
  const atHome = (named === "" || g.path === "/home") && g.path !== "/first-run" && g.path !== "/setup";
  if (!atHome) return false;
  if (g.inApp) return true;
  if (!g.extReady || g.engineUp !== true) return false;
  return !(g.role || g.person);
}
