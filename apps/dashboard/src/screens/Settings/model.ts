// Settings: what each row says and when a control is allowed. Pure: no network, no React. Code decides, never a model.
import type { AttentionSettings } from "../../types";
import { clampBudget } from "../../lib/attention";

/** The section ids: the contract with the shell (docs/KNACK_UX.md section 3, in this order). */
export const SECTIONS = ["live-models", "interruptions", "coaching", "move-aside", "open-at-login", "appearance", "models", "views", "about"] as const;
export type SectionId = (typeof SECTIONS)[number] | "connections" | "hey-knack";
/** Sections other tracks add: Connections (plugins and MCP apps, behind a lazy slot) and Hey Knack (the voice switch). Accepted as an address even when the slot is empty. */
export const SLOT_SECTIONS = ["connections", "hey-knack"] as const;
export const sectionOf = (s: string | null | undefined): SectionId | null => ((SECTIONS as readonly string[]).includes(s ?? "") || (SLOT_SECTIONS as readonly string[]).includes(s ?? "") ? (s as SectionId) : null);

/** Hey Knack's row: the fixed note always, and the shell's own line only when the switch is on but it is not listening (why it is quiet). */
export const WAKE_NOTE = "Stays on this Mac. Nothing is stored.";
export function wakeLine(w: { switchOn: boolean; listening: boolean; line: string } | null): string | null {
  if (!w) return null;
  return w.switchOn && !w.listening && w.line ? `${WAKE_NOTE} ${w.line}` : WAKE_NOTE;
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
}
export interface LiveView { checked: boolean; disabled: boolean; line: string }

export const LIVE_LINES = {
  on: "Knack can call Gemini for steps you allow. Each call is listed in Your data.",
  off: "Everything runs on example data.",
  noKey: "No Gemini key found. Add it to .env and reopen Knack.",
  restart: "Switching restarts the engine. About 20 seconds.",
  running: "A job is running. Stop it first.",
  app: "Switch this in the Knack app.",
  down: "Knack cannot reach its engine. Nothing was changed.",
} as const;

/** The first row of Settings. Disabled, with its reason printed, when there is no key, a job is running, or this is not the app. */
export function liveModels(i: LiveInput): LiveView {
  if (!i.health) return { checked: false, disabled: true, line: LIVE_LINES.down };
  const checked = i.health.mock === false;
  const base = checked ? LIVE_LINES.on : LIVE_LINES.off;
  if (i.changing) return { checked, disabled: true, line: LIVE_LINES.restart };
  if (i.health.key_present === false && !checked) return { checked, disabled: true, line: LIVE_LINES.noKey };
  if (i.running) return { checked, disabled: true, line: `${base} ${LIVE_LINES.running}` };
  if (!i.canSwitch) return { checked, disabled: true, line: `${base} ${LIVE_LINES.app}` };
  return { checked, disabled: false, line: `${base}` };
}

/* -- Interruptions: three words over the eighteen kinds -------------------------------------------------------------------------------- */
export type Preset = "rarely" | "balanced" | "often";
export const PRESETS: { id: Preset; label: string; mode: "quiet" | "normal" | "loud"; budget: number }[] = [
  { id: "rarely", label: "Rarely", mode: "quiet", budget: 4 },
  { id: "balanced", label: "Balanced", mode: "normal", budget: 10 },
  { id: "often", label: "Often", mode: "loud", budget: 20 },
];
export const STOPS_LINE = "Stops and blocking approvals always show.";

const free = (s: Pick<AttentionSettings, "types">) => s.types.filter((t) => !t.fixed);

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

/** A desktop-only row in a browser tab: printed, not hidden. */
export const APP_ONLY = "Available in the Knack app.";
