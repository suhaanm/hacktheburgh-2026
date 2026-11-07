import type { ExtensionName, Health } from "../types";

/** Each REQ-2 screen is shown only when the layer behind it is switched on, or in demo-fixture mode. */
export const EXT_SCREENS = { week: "calendar", briefing: "proactive", agents: "agents", privacy: "privacy" } as const;
export type ExtScreen = keyof typeof EXT_SCREENS;
export type ExtFlags = Partial<Record<ExtensionName, boolean>>;

const ALL: ExtensionName[] = ["privacy", "localmodel", "calendar", "git", "proactive", "agents"];

/** Demo fixtures: every layer is on. Live: exactly what the engine says; a missing `extensions` key means none. */
export function extensionsFrom(health: Pick<Health, "extensions"> | null | undefined, source: "live" | "demo"): ExtFlags {
  if (source === "demo") return Object.fromEntries(ALL.map((k) => [k, true])) as ExtFlags;
  const out: ExtFlags = {};
  for (const k of ALL) out[k] = health?.extensions?.[k] === true;
  return out;
}

export const screenEnabled = (screen: ExtScreen, flags: ExtFlags): boolean => flags[EXT_SCREENS[screen]] === true;

/** The environment variable that switches a layer on, for the "not switched on" state. */
export const FLAG_FOR: Record<ExtensionName, string> = {
  privacy: "UNDERSTUDY_X_PRIVACY", localmodel: "UNDERSTUDY_X_LOCALMODEL", calendar: "UNDERSTUDY_X_CALENDAR",
  git: "UNDERSTUDY_X_GIT", proactive: "UNDERSTUDY_X_PROACTIVE", agents: "UNDERSTUDY_X_AGENTS",
};
