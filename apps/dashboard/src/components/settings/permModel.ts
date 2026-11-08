// The four macOS permissions Knack can use, as Settings and the first run show them: each On or Off with ONE button. Pure: the page reads `state()` (read only: it never makes macOS ask),
// and a button is the worker's own click. Knack can ask macOS and open the right System Settings pane; it can never grant anything itself.

export type Perm = "microphone" | "speech" | "accessibility" | "screen";
export const PERM_ORDER: Perm[] = ["microphone", "speech", "accessibility", "screen"];
export type PermClosed = "granted" | "not_asked" | "denied" | "restricted";

export const PERM_TITLE: Record<Perm, string> = { microphone: "Microphone", speech: "Speech recognition", accessibility: "Accessibility", screen: "Screen recording" };
/** What each one is for, one plain line, printed beside it. */
export const PERM_FOR: Record<Perm, string> = {
  microphone: "Lets Knack hear you.",
  speech: "Lets Knack hear the words Hey Knack.",
  accessibility: "Lets Knack click for you, when you allow it.",
  screen: "Lets Knack look at your screen and point at things anywhere on it.",
};

export interface PermRow {
  kind: Perm;
  title: string;
  line: string;
  on: boolean;
  /** "On" or "Off", the only two words a row prints for its state. */
  word: "On" | "Off";
  /** The one button: Allow (macOS has not been asked, so its own question appears), Open System Settings (it was said no, only the worker can change it there), or none. */
  button: "Allow" | "Open System Settings" | null;
}

/** A closed state from whatever the shell answered; anything unknown is "not asked", never "On". */
export function closedState(raw: unknown): PermClosed {
  const v = typeof raw === "string" ? raw.toLowerCase().replace(/[\s-]/g, "_") : raw === true ? "granted" : "";
  return v === "granted" || v === "denied" || v === "restricted" ? v : "not_asked";
}

export function permRow(kind: Perm, raw: unknown): PermRow {
  const st = closedState(raw);
  const on = st === "granted";
  return {
    kind,
    title: PERM_TITLE[kind],
    line: st === "restricted" ? "This Mac does not let Knack use it." : PERM_FOR[kind],
    on,
    word: on ? "On" : "Off",
    button: on || st === "restricted" ? null : st === "denied" ? "Open System Settings" : "Allow",
  };
}

/** The four rows, in order, from the shell's permissions answer (or all Off when it did not answer). */
export function permRows(state: Record<string, unknown> | null | undefined): PermRow[] {
  return PERM_ORDER.map((k) => permRow(k, state?.[k]));
}

/** The first run asks in two steps, each on the worker's click: voice (microphone, then speech recognition) and clicking and screen help (accessibility, then screen recording). */
export interface PermGroup { id: "voice" | "screen_help"; title: string; button: string; kinds: Perm[] }
export const PERM_GROUPS: PermGroup[] = [
  { id: "voice", title: "Voice", button: "Allow voice", kinds: ["microphone", "speech"] },
  { id: "screen_help", title: "Clicking and screen help", button: "Allow clicking and screen help", kinds: ["accessibility", "screen"] },
];

/** What a group's one button does now: the kinds to ask macOS for, in order (those never asked), and the kinds only System Settings can turn on (those said no). */
export function groupPlan(g: PermGroup, rows: PermRow[]): { ask: Perm[]; open: Perm[]; done: boolean } {
  const by = new Map(rows.map((r) => [r.kind, r]));
  const ask = g.kinds.filter((k) => by.get(k)?.button === "Allow");
  const open = g.kinds.filter((k) => by.get(k)?.button === "Open System Settings");
  return { ask, open, done: ask.length === 0 && open.length === 0 && g.kinds.every((k) => by.get(k)?.on || !by.get(k)?.button) };
}
