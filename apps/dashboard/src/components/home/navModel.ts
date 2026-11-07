// One data file for the menu, the command palette, the tour and the admin route gate. Pure, so it is tested.
// To add a screen to the app: add its id to router.ts, a lazy() entry in App.tsx, and one row here.
import { DEFAULT_SCREEN, type Screen } from "../../router";
import type { ViewRole } from "./viewAs";
import { APP_NAME } from "../../brand";

export { DEFAULT_SCREEN };

export type NavGroup = "main" | "details" | "more" | "reviewers";

export interface NavEntry {
  id: Screen;
  label: string;
  hint: string;
  group: NavGroup;
  /** Only in the Admin view. The Worker view cannot reach it (menu, palette, route). */
  admin?: boolean;
  /** Words the palette also matches. */
  also?: string;
}

export const NAV_ENTRIES: NavEntry[] = [
  { id: "home", label: "Your week", hint: "A few pointers for you", group: "main", also: "home pointers monday note" },
  { id: "firm", label: "Firm", hint: "Your firm, by role", group: "main", admin: true, also: "admin roles people onboarding brief" },
  { id: "repeats", label: "Repeats", hint: "What you do again and again", group: "main", also: "hit list repeated actions automate" },
  { id: "growth", label: "Growth", hint: "How much less help you need", group: "main", also: "independence curve help" },
  { id: "routines", label: "Routines", hint: "What could run for you", group: "main", also: "automations proposals" },
  { id: "queue", label: "Queue", hint: "Waiting for approval", group: "main", also: "approvals morning" },
  { id: "privacy", label: "Privacy", hint: "What was sent to a model", group: "main", also: "ledger egress data" },

  { id: "genome", label: "Genome", hint: "Where time is lost", group: "details", also: "work ribbon waterfall gap expert" },
  { id: "presence", label: "Presence", hint: "Your working week", group: "details", also: "heatmap hours idle" },
  { id: "graph", label: "Graph", hint: "How your work connects", group: "details", also: "work graph nodes" },
  { id: "week", label: "Week", hint: "Your calendar, against an expert's", group: "details", also: "calendar meetings focus" },
  { id: "git", label: "Git habits", hint: "How you commit, against experts", group: "details", also: "commits programmer" },
  { id: "predictions", label: "Predictions", hint: "How well we forecast stuck moments", group: "details", also: "stuck forecast calibration scorecard" },

  { id: "today", label: "Today", hint: "The current task", group: "more", also: "coach task" },
  { id: "memory", label: "Memory", hint: "What it knows about you", group: "more", also: "file notes rules" },
  { id: "notices", label: "Notices", hint: "How loudly it speaks", group: "more", also: "notifications attention" },
  { id: "onboarding", label: "Set up", hint: "Choose a role", group: "more", also: "onboarding role" },
  { id: "briefing", label: "Briefing", hint: "Up to three things for today", group: "more", also: "cards proactive" },
  { id: "agents", label: "Agents", hint: "Background helpers", group: "more", also: "runs background" },
  { id: "models", label: "Models", hint: "Which model, how fast, what it costs", group: "more", also: "cost latency" },

  { id: "evidence", label: "Evidence", hint: "For reviewers", group: "reviewers", also: "calibration limitations report eval" },
];

/** Screens in the Admin audience. Reaching one in the Worker view shows a calm "not in this view" state, not the data. */
export const ADMIN_ONLY: Screen[] = NAV_ENTRIES.filter((e) => e.admin).map((e) => e.id);
/** Screens that are detailed statistics. They get a one-line note that these are the detailed numbers. */
export const DETAIL_SCREENS: Screen[] = NAV_ENTRIES.filter((e) => e.group === "details").map((e) => e.id);
export const REVIEWER_SCREENS: Screen[] = NAV_ENTRIES.filter((e) => e.group === "reviewers").map((e) => e.id);

export const canView = (id: Screen | "unknown", view: ViewRole): boolean => id === "unknown" || view === "admin" || !ADMIN_ONLY.includes(id);

export function entriesFor(view: ViewRole): NavEntry[] {
  return NAV_ENTRIES.filter((e) => !e.admin || view === "admin");
}

export function groupOf(view: ViewRole, group: NavGroup): NavEntry[] {
  return entriesFor(view).filter((e) => e.group === group);
}

export const labelOf = (id: Screen | "unknown"): string => NAV_ENTRIES.find((e) => e.id === id)?.label ?? APP_NAME;

/** The Details group opens by itself when you are on one of its screens. */
export const inGroup = (id: Screen | "unknown", group: NavGroup): boolean => NAV_ENTRIES.some((e) => e.id === id && e.group === group);

/* -- The Firm screen's own views: one idea each, reached by a tab strip and by the palette ------------------------------------ */
export type FirmTab = "overview" | "roles" | "people" | "onboarding" | "automation" | "risk" | "forecasts" | "brief";
export interface FirmTabEntry { id: FirmTab; label: string; hint: string; path: string }
export const FIRM_TABS: FirmTabEntry[] = [
  { id: "overview", label: "Overview", hint: "The seven things to know", path: "/firm" },
  { id: "roles", label: "Roles", hint: "Experts and juniors side by side", path: "/firm/roles" },
  { id: "people", label: "People", hint: "Everyone, grouped by role", path: "/firm/people" },
  { id: "onboarding", label: "Onboarding", hint: "How fast people reach independence", path: "/firm/onboarding" },
  { id: "automation", label: "Automation", hint: "Repeated work across the firm", path: "/firm/automation" },
  { id: "risk", label: "Risk and coverage", hint: "Approvals, pauses, data coverage", path: "/firm/risk" },
  { id: "forecasts", label: "Forecasts", hint: "How well the stuck forecasts hold up", path: "/firm/forecasts" },
  { id: "brief", label: "Firm brief", hint: "A one-page summary to print", path: "/firm/brief" },
];

export function firmTabOf(path: string): FirmTab {
  const seg = path.split("/")[2] ?? "";
  return (FIRM_TABS.find((t) => t.id === seg)?.id ?? "overview") as FirmTab;
}
