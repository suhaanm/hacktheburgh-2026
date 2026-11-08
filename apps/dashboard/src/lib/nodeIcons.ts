// Icons for the graph layer, one per node kind. Pure data, so tests and both graphs read the same table.
//
// The design system (artifact "Understudy Design System", section "The work graph") tells nodes apart by colour, size and opacity and says colour never
// carries a meaning alone: "a label, shape or icon always goes with it". It ships no icon for a node kind, so these are drawn in its idiom and the
// repo's icon set (components/Icon.tsx): a 16 px grid, 1.5 px stroke, round caps and joins, `currentColor` (on a filled node: the token's `--on-*`).
// Nothing here is decorative, and none of it is text: the name of a node lives in its aria-label and in the card that opens on hover, focus or a click.
import type { WorkNodeType } from "../types";

export type IconPrim =
  | { t: "path"; d: string }
  | { t: "circle"; cx: number; cy: number; r: number; fill?: boolean };

/** The four kinds of the work graph. Each silhouette differs from the others, so the kind survives a colour-blind reader and a greyscale print. */
export const NODE_ICON: Record<WorkNodeType, IconPrim[]> = {
  // Two arrows chasing each other: the same mark the Routines destination uses.
  routine: [{ t: "path", d: "M3 6h9l-2.5-2.5M13 10H4l2.5 2.5" }],
  // Three rising ticks: the level chip's own mark in the design system (how far along the person is).
  skill: [{ t: "path", d: "M4 12.5v-2M8 12.5V7.5M12 12.5V3.5" }],
  // Lines of a file read one at a time: the memory file.
  memory: [{ t: "path", d: "M3.5 4.5h9M3.5 8h9M3.5 11.5h5.5" }],
  // A play triangle: something that runs by itself, once the person allows it.
  automation: [{ t: "path", d: "M5.5 3.5v9l7-4.5z" }],
};

export const NODE_KINDS: WorkNodeType[] = ["routine", "skill", "memory", "automation"];

export const NODE_NAME: Record<WorkNodeType, string> = { routine: "Routine", skill: "Skill", memory: "Memory", automation: "Automation" };

/** One short line per kind, for the key and the details panel: what it is, in plain words. */
export const NODE_BLURB: Record<WorkNodeType, string> = {
  routine: "Steps you repeat in much the same way.",
  skill: "Something you are learning to do on your own.",
  memory: "A note Knack keeps so it works the way you like.",
  automation: "A script that can run a routine for you.",
};

/** The glyph's side in pixels for a node of radius r: it fills about two thirds of the disc, and never gets large or illegible. */
export function glyphSize(r: number): number {
  return Math.max(9, Math.min(22, Math.round(r * 1.2)));
}

/** Below this radius a glyph cannot be read: the node is drawn as a plain dot of its kind and the card names it. */
export const GLYPH_MIN_R = 7.5;

/* -- The steps of the transition graph ---------------------------------------------------------------------------------------------------------- */

export type StepKind = "read" | "enter" | "search" | "open" | "check" | "compare" | "copy" | "idle" | "revert" | "run" | "plot" | "send" | "decide" | "ask" | "group" | "handoff" | "step";

export const STEP_ICON: Record<StepKind, IconPrim[]> = {
  read: [{ t: "path", d: "M4 2.5h8v11H4zM6.5 6h3M6.5 9h3" }],
  enter: [{ t: "path", d: "M3.5 12.5l.7-2.8 6.2-6.2 2.1 2.1-6.2 6.2zM9.5 4.5l2 2" }],
  search: [{ t: "circle", cx: 7, cy: 7, r: 4.2 }, { t: "path", d: "M10.2 10.2l3.3 3.3" }],
  open: [{ t: "path", d: "M2.5 3.5h11v9h-11zM2.5 6.5h11" }],
  check: [{ t: "path", d: "M3.5 8.5l3 3 6-7" }],
  compare: [{ t: "path", d: "M3.5 5.5h9M3.5 10.5h9" }],
  copy: [{ t: "path", d: "M6 6h7v7H6zM10 6V3H3v7h3" }],
  idle: [{ t: "path", d: "M6 4v8M10 4v8" }],
  revert: [{ t: "path", d: "M4 4v3.5h3.5M4.3 7.5A4.6 4.6 0 1 1 5.6 11" }],
  run: [{ t: "path", d: "M5.5 3.5v9l7-4.5z" }],
  plot: [{ t: "path", d: "M3 3v10h10M5.5 10l2.5-3 2 1.5 2.5-4" }],
  send: [{ t: "path", d: "M8 10.5V3M5 6l3-3 3 3M3 13h10" }],
  decide: [{ t: "path", d: "M8 2.5l5.5 5.5L8 13.5 2.5 8z" }],
  ask: [{ t: "path", d: "M6 6.2a2 2 0 1 1 3 1.7c-.7.4-1 .9-1 1.6M8 12v.1" }],
  group: [{ t: "path", d: "M11.5 4h-7l4 4-4 4h7" }],
  handoff: [{ t: "path", d: "M6.5 4H3v9h9V9.5M8 8l5-5M9.5 3H13v3.5" }],
  step: [{ t: "circle", cx: 8, cy: 8, r: 2.2, fill: true }],
};

export const STEP_NAME: Record<StepKind, string> = {
  read: "Reading", enter: "Entering", search: "Searching", open: "Opening", check: "Checking", compare: "Comparing", copy: "Copying", idle: "Waiting", revert: "Going back",
  run: "Running", plot: "Charting", send: "Sending out", decide: "Deciding", ask: "Asking", group: "Grouping", handoff: "Handing off", step: "Step",
};

/**
 * Which icon a step gets, from its cog name. The cogs are the three role packs' (READ_RESULT, CHECK_CLIFF, COPY_TO_NOTE; LOAD_DATA, RUN_QUERY, PLOT;
 * READ_CODE, EDIT_CODE, RUN_TESTS, COMMIT) and the engine's base cogs. A cog nobody has drawn yet is a plain step, so a new pack never breaks the graph.
 */
export function stepKind(cog: string): StepKind {
  const c = cog.toUpperCase();
  if (c.includes("SEARCH") || c.includes("FIND") || c.includes("REFORMULATE")) return "search";
  if (c.includes("REVERT") || c.includes("UNDO") || c.includes("ROLLBACK")) return "revert";
  if (c.includes("IDLE") || c.includes("WAIT") || c.includes("PAUSE")) return "idle";
  if (c.includes("COPY") || c.includes("PASTE")) return "copy";
  if (c.includes("HANDOFF") || c.includes("HAND_OFF") || c.includes("ESCALATE") || c.includes("DELEGATE")) return "handoff";
  if (c.includes("EXPORT") || c.includes("COMMIT") || c.includes("PUBLISH") || c.includes("SEND") || c.includes("PUSH")) return "send";
  if (c.includes("CHECK") || c.includes("VERIFY")) return "check";
  if (c.includes("COMPARE") || c.includes("RECONCILE") || c.includes("DIFF")) return "compare";
  if (c.includes("DECIDE") || c.includes("DECISION")) return "decide";
  if (c.includes("PLOT") || c.includes("CHART")) return "plot";
  if (c.includes("GROUP") || c.includes("AGG")) return "group";
  if (c.startsWith("RUN") || c.includes("EXECUTE") || c.includes("PROBE")) return "run";
  if (c === "ASK" || c.startsWith("ASK_")) return "ask";
  if (c.includes("OPEN") || c.includes("SWITCH") || c.includes("NAVIGATE") || c.includes("LOAD")) return "open";
  if (c.startsWith("READ") || c.includes("INSPECT") || c.includes("PROFILE") || c.includes("SCAN")) return "read";
  if (c.startsWith("ENTER") || c.includes("TYPE") || c.includes("FILL") || c.includes("WRITE") || c.includes("EDIT") || c.includes("CLEAN")) return "enter";
  return "step";
}

/** Every icon's path data, for tests: all of it sits inside the 16 px grid. */
export function allPrims(): IconPrim[] {
  return [...Object.values(NODE_ICON).flat(), ...Object.values(STEP_ICON).flat()];
}
