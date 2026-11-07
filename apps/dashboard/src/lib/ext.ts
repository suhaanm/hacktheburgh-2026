import type { AgentHealth, ExtensionName, Health } from "../types";

/** Each optional screen belongs to one layer. A screen is always reachable: with its layer off it shows example data and says so. */
export const EXT_SCREENS = { week: "calendar", briefing: "proactive", agents: "agents", privacy: "privacy", git: "git" } as const;
export type ExtScreen = keyof typeof EXT_SCREENS;
export type ExtFlags = Partial<Record<ExtensionName, boolean>>;

const ALL: ExtensionName[] = ["privacy", "localmodel", "calendar", "git", "proactive", "agents"];

/**
 * Demo fixtures (the engine cannot be reached): every layer reads as on, so the screens show their example data.
 * Live: exactly what the engine says; a missing `extensions` key means none. The `agents` flag lives on the agent service
 * (port 7710), so its health answer is merged in: either service saying true makes it true.
 */
export function extensionsFrom(health: Pick<Health, "extensions"> | null | undefined, source: "live" | "demo", agent?: Pick<AgentHealth, "extensions"> | null): ExtFlags {
  if (source === "demo") return Object.fromEntries(ALL.map((k) => [k, true])) as ExtFlags;
  const out: ExtFlags = {};
  for (const k of ALL) out[k] = health?.extensions?.[k] === true || agent?.extensions?.[k] === true;
  return out;
}

export const screenEnabled = (screen: ExtScreen, flags: ExtFlags): boolean => flags[EXT_SCREENS[screen]] === true;

/** The environment variable that switches a layer on, for the "not switched on" state. */
export const FLAG_FOR: Record<ExtensionName, string> = {
  privacy: "UNDERSTUDY_X_PRIVACY", localmodel: "UNDERSTUDY_X_LOCALMODEL", calendar: "UNDERSTUDY_X_CALENDAR",
  git: "UNDERSTUDY_X_GIT", proactive: "UNDERSTUDY_X_PROACTIVE", agents: "UNDERSTUDY_X_AGENTS",
};
