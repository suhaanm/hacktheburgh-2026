// One data file for the sidebar, the More sheet, the command palette, the tour and the Admin route gate. Pure, so it is tested.
// Knack has five worker destinations and three admin ones; everything else is under More (a sheet of at most ten rows) and the palette.
// To add a screen: its id in router.ts, one row here, one entry in screenRegistry.ts. Old ids live in routeRedirects.ts.
import { DEFAULT_SCREEN, type Screen } from "../../router";
import type { ViewRole } from "./viewAs";

export { DEFAULT_SCREEN };

/**
 * primary: the five worker destinations. admin: the three Admin destinations. understand, behind, reviewers: the groups of the More sheet.
 * hidden: reachable by address and by the flows that open them, never listed (first run, set up again).
 */
export type NavGroup = "primary" | "admin" | "understand" | "behind" | "reviewers" | "hidden";

/** The icon ids of the shell's inline set (16 px grid). */
export type NavIcon = "home" | "needs-you" | "routines" | "growth" | "your-data" | "firm" | "roles" | "onboarding" | "more" | "look";

export interface NavEntry {
  id: Screen;
  /** The one-line label in the sidebar, the More sheet and the palette. Sentence case, no hint beside it. */
  label: string;
  /** Shown in the command palette only (the sidebar carries no hints). */
  hint: string;
  group: NavGroup;
  /** Only in the Admin view. The Worker view cannot reach it (menu, palette, route). */
  admin?: boolean;
  /** Words the palette also matches. Includes the old names, so a habit still finds the screen. */
  also?: string;
  icon?: NavIcon;
}

export const NAV_ENTRIES: NavEntry[] = [
  // Worker: five
  { id: "home", label: "Home", hint: "What matters this week", group: "primary", icon: "home", also: "your week pointers monday note" },
  { id: "needs-you", label: "Needs you", hint: "Everything waiting for a decision", group: "primary", icon: "needs-you", also: "queue briefing approvals proposals morning inbox" },
  { id: "routines", label: "Routines", hint: "What runs for you, and what could", group: "primary", icon: "routines", also: "repeats hit list automations could automate" },
  { id: "growth", label: "Growth", hint: "Whether you need less help over time", group: "primary", icon: "growth", also: "independence curve help" },
  { id: "your-data", label: "Your data", hint: "What Knack remembers, measures and has sent", group: "primary", icon: "your-data", also: "memory privacy ledger delete forget egress capture" },
  // Admin: three
  { id: "firm", label: "Firm", hint: "Where the firm loses time", group: "admin", admin: true, icon: "firm", also: "admin overview insights" },
  { id: "roles", label: "Roles", hint: "Experts and juniors, side by side", group: "admin", admin: true, icon: "roles", also: "admin people compare" },
  { id: "onboarding", label: "Onboarding", hint: "How fast people reach independence", group: "admin", admin: true, icon: "onboarding", also: "admin new starters curve" },
  // More: understand your work
  { id: "genome", label: "Where time goes", hint: "Where time is lost against an expert", group: "understand", also: "genome work ribbon waterfall gap expert" },
  { id: "presence", label: "Your hours", hint: "Your working week", group: "understand", also: "presence heatmap idle" },
  { id: "graph", label: "How work connects", hint: "Your routines, skills and notes", group: "understand", also: "graph work graph nodes" },
  { id: "week", label: "Calendar", hint: "Your calendar, against an expert's", group: "understand", also: "week meetings focus" },
  { id: "git", label: "Git habits", hint: "How you commit, against experts", group: "understand", also: "commits programmer" },
  { id: "forecasts", label: "Forecasts", hint: "How well Knack forecasts stuck moments", group: "understand", also: "predictions stuck calibration scorecard" },
  // More: behind the scenes
  { id: "agents", label: "Background runs", hint: "Helpers that work while you do something else", group: "behind", also: "agents runs background" },
  { id: "models", label: "Models and cost", hint: "Which model, how fast, what it costs", group: "behind", also: "cost latency gemini" },
  { id: "today", label: "Live coach", hint: "The current task and the help level", group: "behind", also: "today coach task" },
  // More: reviewers
  { id: "evidence", label: "Evidence", hint: "For reviewers", group: "reviewers", also: "calibration limitations report eval" },
  // Not listed
  { id: "first-run", label: "Welcome", hint: "Set Knack up", group: "hidden", also: "first run welcome" },
  { id: "setup", label: "Set up again", hint: "Choose a role again", group: "hidden", also: "onboarding role set up" },
];

/** The three signature screens. Off by default; Settings, Views, "Pinned views" puts them in the sidebar under "Look closer". */
export const PINNED_VIEWS: Screen[] = ["genome", "graph", "presence"];

/** Screens in the Admin audience. Reaching one in the Worker view shows a calm "not in this view" state, not the data. */
export const ADMIN_ONLY: Screen[] = NAV_ENTRIES.filter((e) => e.admin).map((e) => e.id);
export const REVIEWER_SCREENS: Screen[] = NAV_ENTRIES.filter((e) => e.group === "reviewers").map((e) => e.id);
/** The screens of the detail groups under More. */
export const DETAIL_SCREENS: Screen[] = NAV_ENTRIES.filter((e) => e.group === "understand" || e.group === "behind").map((e) => e.id);
/** Screens without a sidebar: the first run, and the old set-up flow. */
export const BARE_SCREENS: Screen[] = ["first-run"];

export const canView = (id: Screen | "unknown", view: ViewRole): boolean => id === "unknown" || view === "admin" || !ADMIN_ONLY.includes(id);

export function entriesFor(view: ViewRole): NavEntry[] {
  return NAV_ENTRIES.filter((e) => e.group !== "hidden" && (!e.admin || view === "admin"));
}

export function groupOf(view: ViewRole, group: NavGroup): NavEntry[] {
  return NAV_ENTRIES.filter((e) => e.group === group && (!e.admin || view === "admin"));
}

export const labelOf = (id: Screen | "unknown"): string => NAV_ENTRIES.find((e) => e.id === id)?.label ?? "Knack";

/* -- The sidebar ---------------------------------------------------------------------------------------------------------------- */

export interface SidebarModel {
  /** The five worker destinations, always. */
  primary: NavEntry[];
  /** The three Admin destinations, in the Admin view only. */
  admin: NavEntry[];
  /** "Look closer": Genome, Graph and Presence, when Pinned views is on. */
  pinned: NavEntry[];
  /** Rows drawn: primary, admin, pinned, then More. */
  rows: number;
}

export function sidebarFor(view: ViewRole, pinnedOn = false): SidebarModel {
  const primary = groupOf(view, "primary");
  const admin = groupOf(view, "admin");
  const pinned = pinnedOn ? PINNED_VIEWS.map((id) => NAV_ENTRIES.find((e) => e.id === id)!).filter(Boolean) : [];
  return { primary, admin, pinned, rows: primary.length + admin.length + pinned.length + 1 };
}

/* -- The More sheet -------------------------------------------------------------------------------------------------------------- */

export interface MoreRow {
  /** A screen id, or "firm:people" for a Firm view. */
  id: string;
  label: string;
  path: string;
  /** The heading of its group in the sheet. */
  section: string;
}

export const MORE_MAX = 10;

export const SECTION: Record<NavGroup, string> = {
  primary: "Go to", admin: "Admin", understand: "Understand your work", behind: "Behind the scenes", reviewers: "For reviewers", hidden: "",
};
export const SECTION_FIRM = "Firm";

const row = (e: NavEntry): MoreRow => ({ id: e.id, label: e.label, path: `/${e.id}`, section: SECTION[e.group] });

/**
 * The rows of the More sheet, at most ten. The Worker view lists the ten screens that are not destinations (minus any that Pinned
 * views moved into the sidebar). The Admin view puts the five Firm views first and keeps the two signature screens, the two
 * behind-the-scenes screens and Evidence; the rest stay in the palette, which lists every screen.
 */
export function moreFor(view: ViewRole, pinnedOn = false): MoreRow[] {
  const pinned = new Set<Screen>(pinnedOn ? PINNED_VIEWS : []);
  const detail = (ids: Screen[]) => ids.filter((id) => !pinned.has(id)).map((id) => NAV_ENTRIES.find((e) => e.id === id)!).map(row);
  if (view === "admin") {
    const firm: MoreRow[] = FIRM_MORE.map((id) => {
      const t = FIRM_TABS.find((x) => x.id === id)!;
      return { id: `firm:${t.id}`, label: t.label, path: t.path, section: SECTION_FIRM };
    });
    return [...firm, ...detail(["genome", "graph", "agents", "models", "evidence"])].slice(0, MORE_MAX);
  }
  return [
    ...detail(["genome", "presence", "graph", "week", "git", "forecasts"]),
    ...detail(["agents", "models", "today"]),
    ...detail(["evidence"]),
  ].slice(0, MORE_MAX);
}

/* -- Clicks ---------------------------------------------------------------------------------------------------------------------- */

/** Clicks from Home to a screen over the nav graph: 0 for Home, 1 for a sidebar row, 2 through More. Used by jobs.test.ts. */
export function clicksFromHome(id: Screen, view: ViewRole, pinnedOn = false): number {
  if (id === DEFAULT_SCREEN) return 0;
  const s = sidebarFor(view, pinnedOn);
  if ([...s.primary, ...s.admin, ...s.pinned].some((e) => e.id === id)) return 1;
  if (moreFor(view, pinnedOn).some((r) => r.id === id)) return 2;
  return Infinity;
}

/* -- The Firm views: one idea each. The first three are sidebar destinations; the rest are rows in More and in the palette ------- */
export type FirmTab = "overview" | "roles" | "people" | "onboarding" | "automation" | "risk" | "forecasts" | "brief";
export interface FirmTabEntry { id: FirmTab; label: string; hint: string; path: string }
export const FIRM_TABS: FirmTabEntry[] = [
  { id: "overview", label: "Overview", hint: "The few things to know", path: "/firm" },
  { id: "roles", label: "Roles", hint: "Experts and juniors side by side", path: "/roles" },
  { id: "people", label: "People", hint: "Everyone, grouped by role", path: "/firm/people" },
  { id: "onboarding", label: "Onboarding", hint: "How fast people reach independence", path: "/onboarding" },
  { id: "automation", label: "Automation", hint: "Repeated work across the firm", path: "/firm/automation" },
  { id: "risk", label: "Risk and coverage", hint: "Approvals, pauses, data coverage", path: "/firm/risk" },
  { id: "forecasts", label: "Forecasts", hint: "How well the stuck forecasts hold up", path: "/firm/forecasts" },
  { id: "brief", label: "Firm brief", hint: "A one-page summary to print", path: "/firm/brief" },
];
/** The Firm views that are rows in the Admin More sheet (Roles and Onboarding are sidebar destinations). */
const FIRM_MORE: FirmTab[] = ["people", "automation", "risk", "forecasts", "brief"];

/** Which Firm view an address shows: `/roles` and `/onboarding` are their own destinations, `/firm/<view>` the rest. */
export function firmTabOf(path: string): FirmTab {
  const seg = path.split("/")[1] ?? "";
  if (seg === "roles") return "roles";
  if (seg === "onboarding") return "onboarding";
  const sub = path.split("/")[2] ?? "";
  return (FIRM_TABS.find((t) => t.id === sub)?.id ?? "overview") as FirmTab;
}
