// Settings: what each row says and when a control is allowed. Pure: no network, no React. Code decides, never a model.
import type { AttentionSettings } from "../../types";
import { clampBudget } from "../../lib/attention";
import { plainWords } from "../NeedsYou/model";

/** The section ids: the contract with the shell (docs/KNACK_UX.md section 3, in this order). */
export const SECTIONS = ["live-models", "interruptions", "coaching", "move-aside", "open-at-login", "appearance", "models", "views", "about"] as const;
export type SectionId = (typeof SECTIONS)[number] | "connections" | "hey-knack" | "advanced";
/** Sections other tracks add: Connections (plugins and MCP apps, behind a lazy slot) and Hey Knack (the voice switch). Accepted as an address even when the slot is empty. */
export const SLOT_SECTIONS = ["connections", "hey-knack", "advanced"] as const;
export const sectionOf = (s: string | null | undefined): SectionId | null => ((SECTIONS as readonly string[]).includes(s ?? "") || (SLOT_SECTIONS as readonly string[]).includes(s ?? "") ? (s as SectionId) : null);

/** Hey Knack's row: the fixed note always, and the shell's own line only when the switch is on but it is not listening (why it is quiet). */
export const WAKE_NOTE = "Stays on this Mac. Nothing is stored.";
export function wakeLine(w: { switchOn: boolean; listening: boolean; line: string } | null): string | null {
  if (!w) return null;
  return w.switchOn && !w.listening && w.line ? `${WAKE_NOTE} ${plainWords(w.line)}` : WAKE_NOTE;
}

/* -- Use live models ------------------------------------------------------------------------------------------------------------------- */
export interface LiveInput {
  /** What GET /health said, or null when the engine did not answer. `mock` false is live. `key_present` is additive: absent means the engine did not say. */
  health: { mock?: boolean; key_present?: boolean } | null;
  /** The desktop app can restart the stack; a browser tab cannot. */
  canSwitch: boolean;
  /** A background run is working. */
  running: boolean;
  /** The switch was just pressed and the restart is under way. */
  changing: boolean;
  /** The switch is on, a key is set, and the app could not reach the model service at start: it keeps trying and switches on by itself. */
  retrying?: boolean;
}
export interface LiveView { checked: boolean; disabled: boolean; line: string }

export const LIVE_LINES = {
  on: "On, because a key is set. Every call is listed under Advanced.",
  onPlain: "On. Every call is listed under Advanced.",
  off: "Off. Knack does not call a live model.",
  noKey: "No key found. Add it to .env and reopen Knack.",
  restart: "Switching restarts the engine. About 20 seconds.",
  running: "A job is running. Stop it first.",
  app: "Switch this in the Knack app.",
  down: "Knack cannot reach its engine. Nothing was changed.",
  /** The switch is on; only the service could not be reached. Never says to turn the switch on. */
  retrying: "On. Knack could not reach the model service. It keeps trying and will switch on by itself.",
} as const;

/** The first row of Settings. Disabled, with its reason printed, when there is no key, a job is running, or this is not the app. */
export function liveModels(i: LiveInput): LiveView {
  if (!i.health) return { checked: false, disabled: true, line: LIVE_LINES.down };
  const live = i.health.mock === false;
  // The worker's switch is on and a key is set, but the service could not be reached at start: the row shows the switch as it is (on) and says what Knack is doing about it.
  const retrying = i.retrying === true && !live && i.health.key_present !== false;
  const checked = live || retrying;
  // 'Because a key is set' is only said when the engine says a key is set: it never claims a key it was not told about.
  const base = retrying ? LIVE_LINES.retrying : checked ? (i.health.key_present === true ? LIVE_LINES.on : LIVE_LINES.onPlain) : LIVE_LINES.off;
  if (i.changing) return { checked, disabled: true, line: LIVE_LINES.restart };
  if (i.health.key_present === false && !checked) return { checked, disabled: true, line: LIVE_LINES.noKey };
  if (i.running) return { checked, disabled: true, line: `${base} ${LIVE_LINES.running}` };
  if (!i.canSwitch) return { checked, disabled: true, line: `${base} ${LIVE_LINES.app}` };
  return { checked, disabled: false, line: `${base}` };
}

/**
 * What each setting starts as (owner request REQ-9, 8 Nov 2026: every default as automated as the safety layers allow). The values apply; no row prints them
 * (owner, 8 Nov 2026: no "Default: X" text on any setting). The reasons and the safety note for each are in docs/knack-ux/defaults.md, and a test keeps the two in step.
 * Never a default here: auto-granting a consent card, auto-approving, unattended runs, irreversible actions. Those stay off until the worker says otherwise.
 */
export const DEFAULTS = {
  "live-models": { value: "on" },     // on when a key is set
  interruptions: { value: "balanced" },
  coaching: { value: "on" },
  "help-level": { value: "auto" },
  "hey-knack": { value: "on" },
  "move-aside": { value: "on" },
  "open-at-login": { value: "on" },
  skills: { value: "on" },
  "max-minutes": { value: 30 },
  "max-budget": { value: 2 },
} as const;
export type DefaultId = keyof typeof DEFAULTS;

/* -- Interruptions: three words over the eighteen kinds -------------------------------------------------------------------------------- */
export type Preset = "rarely" | "balanced" | "often";
export const PRESETS: { id: Preset; label: string; mode: "quiet" | "normal" | "loud"; budget: number }[] = [
  { id: "rarely", label: "Rarely", mode: "quiet", budget: 4 },
  { id: "balanced", label: "Balanced", mode: "normal", budget: 10 },
  { id: "often", label: "Often", mode: "loud", budget: 20 },
];
export const STOPS_LINE = "Stops and blocking approvals always show.";

const free = (s: Pick<AttentionSettings, "types">) => s.types.filter((t) => !t.fixed);

/** The mode one group of kinds is at when every kind that can change is at the same one; otherwise null (they differ, so no button is pressed). */
export function groupModeOf(rows: { mode: string; fixed?: boolean }[]): "loud" | "normal" | "quiet" | "digest" | null {
  const free = rows.filter((r) => !r.fixed);
  if (free.length === 0) return null;
  const m = free[0].mode;
  return free.every((r) => r.mode === m) && (m === "loud" || m === "normal" || m === "quiet" || m === "digest") ? m : null;
}

/** Which word fits: when every kind that can change is at the same mode, the word for it; otherwise none (the kinds differ). */
export function presetOf(s: Pick<AttentionSettings, "types">): Preset | null {
  const rows = free(s);
  if (rows.length === 0) return null;
  const first = rows[0].mode;
  if (!rows.every((r) => r.mode === first)) return null;
  return PRESETS.find((p) => p.mode === first)?.id ?? null;
}

/** The change that sets every kind that can change to the word's mode, and the day's budget to its number. Safety kinds are never in it. */
export function presetPatch(p: Preset, s: Pick<AttentionSettings, "types">): { modes: Record<string, string>; budget_per_day: number } {
  const def = PRESETS.find((x) => x.id === p)!;
  return { modes: Object.fromEntries(free(s).map((t) => [t.type, def.mode])), budget_per_day: clampBudget(def.budget) };
}

/* -- Appearance ------------------------------------------------------------------------------------------------------------------------ */
export type Theme = "auto" | "light" | "dark";
export const THEME_KEY = "understudy-theme";
export const THEMES: { id: Theme; label: string }[] = [{ id: "auto", label: "Auto" }, { id: "light", label: "Light" }, { id: "dark", label: "Dark" }];
export const themeOf = (v: string | null | undefined): Theme => (v === "light" || v === "dark" ? v : "auto");

/* -- Coaching -------------------------------------------------------------------------------------------------------------------------- */
export type HelpLock = "auto" | 1 | 2 | 3 | 4;
export const HELP_LOCKS: { id: HelpLock; label: string }[] = [{ id: "auto", label: "Automatic" }, { id: 1, label: "Level 1" }, { id: 2, label: "Level 2" }, { id: 3, label: "Level 3" }, { id: 4, label: "Level 4" }];
/** The desktop settings behind the lock: `helpLevelMode` and `lockedLevel`. */
export const lockOf = (s: { helpLevelMode?: string; lockedLevel?: number } | null | undefined): HelpLock => (s?.helpLevelMode === "locked" && [1, 2, 3, 4].includes(s.lockedLevel ?? 0) ? (s.lockedLevel as HelpLock) : "auto");
export const lockPatch = (l: HelpLock): { helpLevelMode: "auto" | "locked"; lockedLevel?: number } => (l === "auto" ? { helpLevelMode: "auto" } : { helpLevelMode: "locked", lockedLevel: l });

/** What a role pack's depth means to the worker (the same words as Track B's profile helper): a standard pack is not a starter. */
export const depthWords = (depth: string | null | undefined): string => (depth === "deep" ? "Fully built and validated" : depth === "standard" ? "Full pack" : "Starter");

/** A desktop-only row in a browser tab: printed, not hidden. */
export const APP_ONLY = "Available in the Knack app.";

/** The headline of Settings: how Knack is set right now, in one sentence. */
export function settingsHeadline(i: { live: boolean | null; preset: Preset | null }): string {
  const live = i.live === null ? "" : i.live ? "Knack uses live models" : "Knack does not use live models";
  const how = i.preset === "rarely" ? "interrupts you rarely" : i.preset === "often" ? "interrupts you often" : i.preset === "balanced" ? "interrupts you at a balanced pace" : "";
  if (live && how) return `${live} and ${how}.`;
  if (live) return `${live}.`;
  return how ? `Knack ${how}.` : "";
}

/* -- Skills: the skill files already on this Mac (the tasks service's list), names and descriptions only ------------------------------------------ */
export interface SkillRow { name: string; description: string; on: boolean }
/** The skills as listed: a real name only, each name once, sorted by name, at most 200; `off` names are turned off whatever the row says. */
export function skillRows(a: { off?: unknown; skills?: unknown } | null | undefined): SkillRow[] {
  const off = new Set(Array.isArray(a?.off) ? (a!.off as unknown[]).filter((x): x is string => typeof x === "string") : []);
  const seen = new Set<string>();
  const rows: SkillRow[] = [];
  for (const k of Array.isArray(a?.skills) ? (a!.skills as unknown[]) : []) {
    const o = (k && typeof k === "object" ? k : {}) as { name?: unknown; description?: unknown };
    const name = typeof o.name === "string" ? o.name.trim().slice(0, 80) : "";
    if (!name || seen.has(name)) continue;
    seen.add(name);
    rows.push({ name, description: typeof o.description === "string" ? Array.from(o.description.replace(/\s+/g, " ").trim()).slice(0, 140).join("") : "", on: !off.has(name) });
  }
  return rows.sort((x, y) => x.name.localeCompare(y.name)).slice(0, 200);
}
/** The new off list after one skill is switched: every other name stays as it was, and a name is never listed twice. */
export function withSkill(off: string[] | undefined, name: string, on: boolean): string[] {
  const rest = (Array.isArray(off) ? off : []).filter((x) => typeof x === "string" && x !== name);
  return on ? rest : [...rest, name];
}

/** The longest a background task may run, in the choices the row offers (the service accepts 1 to 120). The current value is always one of them. */
export const MAX_MINUTES_CHOICES = [5, 10, 15, 30, 60, 90, 120] as const;
export function maxMinutesChoices(current: unknown): number[] {
  const n = typeof current === "number" && Number.isInteger(current) && current >= 1 && current <= 120 ? current : null;
  return n === null || (MAX_MINUTES_CHOICES as readonly number[]).includes(n) ? [...MAX_MINUTES_CHOICES] : [...MAX_MINUTES_CHOICES, n].sort((x, y) => x - y);
}

/** The most a task may spend, in US dollars: the choices the row offers (the service accepts 0.5 to 20). The current value is always one of them. */
export const MAX_BUDGET_CHOICES = [0.5, 1, 2, 5, 10, 20] as const;
export function maxBudgetChoices(current: unknown): number[] {
  const n = typeof current === "number" && Number.isFinite(current) && current >= 0.5 && current <= 20 ? current : null;
  return n === null || (MAX_BUDGET_CHOICES as readonly number[]).includes(n) ? [...MAX_BUDGET_CHOICES] : [...MAX_BUDGET_CHOICES, n].sort((x, y) => x - y);
}
/** "US$0.50", "US$2": whole dollars without cents, anything else with two decimals. */
export const usd = (n: number): string => `US$${Number.isInteger(n) ? n : n.toFixed(2)}`;
