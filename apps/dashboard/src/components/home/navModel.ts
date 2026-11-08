// One data file for the sidebar, the More sheet, the command palette, the tour and the Admin route gate. Pure, so it is tested.
// Rule (docs/knack-ux/views.md): a worker sees five destinations and nothing else; an admin sees the firm in eight, with three more under More.
// Everything the old app had as a screen is either a section of Growth, a Firm view, or a row under the Admin More. Old ids live in routeRedirects.ts.
// To add a screen: its id in router.ts, one row here, one entry in screenRegistry.ts.
import { DEFAULT_SCREEN, type Screen } from "../../router";
import type { ViewRole } from "./viewAs";

export { DEFAULT_SCREEN };

/**
 * primary: the five worker destinations. admin: the eight Admin destinations. more: the three rows behind the Admin More.
 * hidden: reachable by address and by the flows that open them, never listed (first run, set up again).
 */
export type NavGroup = "primary" | "admin" | "more" | "hidden";

/** The icon ids of the shell's inline set (16 px grid). */
export type NavIcon =
  | "home" | "needs-you" | "routines" | "growth" | "your-data"
  | "firm" | "brief" | "forecasts" | "roles" | "people" | "onboarding" | "automation" | "risk"
  | "more" | "look";

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
  { id: "home", label: "Home", hint: "What matters this week", group: "primary", icon: "home", also: "your week pointers monday note today task" },
  { id: "needs-you", label: "Needs you", hint: "Everything waiting for a decision", group: "primary", icon: "needs-you", also: "queue briefing approvals proposals morning inbox" },
  { id: "routines", label: "Routines", hint: "What runs for you, and what could", group: "primary", icon: "routines", also: "repeats hit list automations could automate background tasks agents" },
  { id: "growth", label: "Growth", hint: "Whether you need less help over time", group: "primary", icon: "growth", also: "progress independence curve help" },
  { id: "your-data", label: "Your data", hint: "What Knack remembers, measures and has sent", group: "primary", icon: "your-data", also: "memory privacy ledger delete forget egress capture" },
  // Admin: eight (the owner's order: Firm, Brief, Forecasts, Roles, People, Onboarding, Automation, Risk)
  { id: "firm", label: "Firm", hint: "Where the firm loses time", group: "admin", admin: true, icon: "firm", also: "admin overview insights" },
  { id: "brief", label: "Brief", hint: "A one-page summary of the firm to print", group: "admin", admin: true, icon: "brief", also: "firm brief export pdf one-pager print" },
  { id: "forecasts", label: "Forecasts", hint: "What to expect, and what to do about it", group: "admin", admin: true, icon: "forecasts", also: "predictions stuck calibration scorecard" },
  { id: "roles", label: "Roles", hint: "Experts and juniors, side by side", group: "admin", admin: true, icon: "roles", also: "admin compare" },
  { id: "people", label: "People", hint: "Everyone, grouped by role", group: "admin", admin: true, icon: "people", also: "admin team staff" },
  { id: "onboarding", label: "Onboarding", hint: "How fast people reach independence", group: "admin", admin: true, icon: "onboarding", also: "admin new starters curve" },
  { id: "automation", label: "Automation", hint: "Repeated work across the firm", group: "admin", admin: true, icon: "automation", also: "admin repeats hit list" },
  { id: "risk", label: "Risk", hint: "Approvals, pauses and data coverage", group: "admin", admin: true, icon: "risk", also: "admin coverage risk and coverage" },
  // Admin More: three
  { id: "models", label: "Models and cost", hint: "Which model, how fast, what it costs", group: "more", admin: true, also: "cost latency gemini" },
  { id: "evidence", label: "Evidence", hint: "For reviewers", group: "more", admin: true, also: "calibration limitations report eval" },
  { id: "agents", label: "Background runs", hint: "Helpers that work while someone does something else", group: "more", admin: true, also: "agents runs background" },
  // Not listed
  { id: "first-run", label: "Welcome", hint: "Set Knack up", group: "hidden", also: "first run welcome" },
  { id: "setup", label: "Set up again", hint: "Choose a role again", group: "hidden", also: "onboarding role set up" },
];

/** Screens in the Admin audience. Reaching one in the Worker view shows the Admin gate sentence, not the data, and makes no request. */
export const ADMIN_ONLY: Screen[] = NAV_ENTRIES.filter((e) => e.admin).map((e) => e.id);
/** The three rows behind the Admin More. They carry a one-line way back. */
export const MORE_SCREENS: Screen[] = NAV_ENTRIES.filter((e) => e.group === "more").map((e) => e.id);
/** Screens without a sidebar: the first run, and the set-up flow. */
export const BARE_SCREENS: Screen[] = ["first-run"];

export const canView = (id: Screen | "unknown", view: ViewRole): boolean => id === "unknown" || view === "admin" || !ADMIN_ONLY.includes(id);

/** The one sentence a worker sees when an address names an Admin screen (docs/knack-ux/views.md, the data separation checklist). */
export const ADMIN_GATE = "Switch to Admin to see this";

export function entriesFor(view: ViewRole): NavEntry[] {
  return NAV_ENTRIES.filter((e) => e.group !== "hidden" && (view === "admin" ? e.admin : !e.admin));
}

/** The entries of a group the view may see. In the Admin view the worker's five are not listed: an admin reaches them with View as. */
export function groupOf(view: ViewRole, group: NavGroup): NavEntry[] {
  return NAV_ENTRIES.filter((e) => e.group === group && (view === "admin" ? !!e.admin : !e.admin));
}

export const labelOf = (id: Screen | "unknown"): string => NAV_ENTRIES.find((e) => e.id === id)?.label ?? "Knack";

/* -- The sidebar ---------------------------------------------------------------------------------------------------------------- */

export interface SidebarModel {
  /** The rows of the sidebar: a worker's five, an admin's eight. Cmd-1 and on go to these in order. */
  main: NavEntry[];
  /** The rows behind More (Admin only); none for a worker, who has no More. */
  more: NavEntry[];
  /** Rows drawn: main, then More when it has rows. */
  rows: number;
}

export function sidebarFor(view: ViewRole): SidebarModel {
  const main = groupOf(view, view === "admin" ? "admin" : "primary");
  const more = groupOf(view, "more");
  return { main, more, rows: main.length + (more.length > 0 ? 1 : 0) };
}

/* -- The More sheet ------------------------------------------------------------------------------------------------------------- */

export interface MoreRow {
  id: string;
  label: string;
  path: string;
  /** The heading of its group in the sheet. */
  section: string;
}

export const MORE_MAX = 10;
export const SECTION_MORE = "More";
export const SECTION_ADMIN = "Admin";

const row = (e: NavEntry, section: string): MoreRow => ({ id: e.id, label: e.label, path: `/${e.id}`, section });

/** The rows of the More sheet: none for a worker (five rows is the whole menu), the three behind-the-scenes screens for an admin. */
export function moreFor(view: ViewRole): MoreRow[] {
  return groupOf(view, "more").map((e) => row(e, SECTION_MORE)).slice(0, MORE_MAX);
}

/** The bottom bar at 390 px holds five items. A worker's five fit; an admin's eight do not, so the first five stay and the rest lead the More sheet. */
export const BAR_MAX = 5;
export function compactFor(view: ViewRole): { bar: NavEntry[]; overflow: MoreRow[] } {
  const { main } = sidebarFor(view);
  return { bar: main.slice(0, BAR_MAX), overflow: main.slice(BAR_MAX).map((e) => row(e, SECTION_ADMIN)) };
}

/* -- Clicks ---------------------------------------------------------------------------------------------------------------------- */

/** Clicks from the landing screen (Home for a worker, Firm for an admin) to a screen over the nav graph: 0 for the landing screen, 1 for a sidebar row, 2 through More. */
export function clicksFromHome(id: Screen, view: ViewRole): number {
  if (id === landingFor(view)) return 0;
  const s = sidebarFor(view);
  if (s.main.some((e) => e.id === id)) return 1;
  if (s.more.some((e) => e.id === id)) return 2;
  return Infinity;
}

/** Where each view opens: a worker on Home, an admin on Firm. */
export const landingFor = (view: ViewRole): Screen => (view === "admin" ? "firm" : DEFAULT_SCREEN);

/* -- Growth: one page, five sections --------------------------------------------------------------------------------------------- */

export const GROWTH_SECTIONS = ["progress", "time", "steps", "map", "commits"] as const;
export type GrowthSection = (typeof GROWTH_SECTIONS)[number];
export const GROWTH_SECTION_LABEL: Record<GrowthSection, string> = {
  progress: "My progress",
  time: "Where my time goes",
  steps: "My steps",
  map: "How my routines connect",
  commits: "My commits",
};
/** Words the palette also matches for each section, including what the section used to be called. */
export const GROWTH_SECTION_ALSO: Record<GrowthSection, string> = {
  progress: "independence curve help",
  time: "week calendar meetings focus presence hours idle heatmap",
  steps: "genome work ribbon waterfall gap expert transition",
  map: "graph work graph nodes routines skills notes",
  commits: "git habits programmer commits",
};
export const growthSectionOf = (raw: string | null | undefined): GrowthSection => (GROWTH_SECTIONS as readonly string[]).includes(raw ?? "") ? (raw as GrowthSection) : "progress";
export const growthPath = (s: GrowthSection): string => (s === "progress" ? "/growth" : `/growth?section=${s}`);

/* -- The Firm views: one idea each, each its own top-level address ----------------------------------------------------------- */
export type FirmTab = "overview" | "roles" | "people" | "onboarding" | "automation" | "risk" | "forecasts" | "brief";
export interface FirmTabEntry { id: FirmTab; label: string; hint: string; path: string }
export const FIRM_TABS: FirmTabEntry[] = [
  { id: "overview", label: "Overview", hint: "The few things to know", path: "/firm" },
  { id: "brief", label: "Brief", hint: "A one-page summary to print", path: "/brief" },
  { id: "forecasts", label: "Forecasts", hint: "What to expect, and what to do about it", path: "/forecasts" },
  { id: "roles", label: "Roles", hint: "Experts and juniors side by side", path: "/roles" },
  { id: "people", label: "People", hint: "Everyone, grouped by role", path: "/people" },
  { id: "onboarding", label: "Onboarding", hint: "How fast people reach independence", path: "/onboarding" },
  { id: "automation", label: "Automation", hint: "Repeated work across the firm", path: "/automation" },
  { id: "risk", label: "Risk and coverage", hint: "Approvals, pauses, data coverage", path: "/risk" },
];

const FIRM_SEGMENTS: FirmTab[] = ["brief", "forecasts", "roles", "people", "onboarding", "automation", "risk"];

/**
 * Which Firm view an address shows. Each view is its own top-level address (`/roles`, `/brief`); the old `/firm/<view>` form still reads the same
 * way, though the router rewrites it before anything renders.
 */
export function firmTabOf(path: string): FirmTab {
  const seg = path.split("/")[1] ?? "";
  const top = FIRM_SEGMENTS.find((t) => t === seg);
  if (top) return top;
  const sub = path.split("/")[2] ?? "";
  return (FIRM_SEGMENTS.find((t) => t === sub) ?? "overview") as FirmTab;
}
