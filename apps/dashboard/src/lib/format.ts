import type { Interval } from "../types";

const MINUS = "−";

/** Real minus sign for negatives so figures line up and read correctly. */
export function signed(n: number, digits = 0): string {
  const v = Math.abs(n).toFixed(digits);
  if (n < 0 && Number(v) !== 0) return `${MINUS}${v}`;
  return v;
}

export function fmtNum(n: number, digits = 0): string {
  return signed(n, digits);
}

export function fmtSec(s: number, digits = 0): string {
  return `${signed(s, digits)} s`;
}

/** 276 -> "4 min 36 s"; under a minute -> "44 s". */
export function fmtDuration(s: number): string {
  const total = Math.round(s);
  if (total < 60) return `${total} s`;
  const m = Math.floor(total / 60);
  const r = total % 60;
  return r === 0 ? `${m} min` : `${m} min ${r} s`;
}

export function fmtInterval(iv: Interval, digits = 0, unit = ""): string {
  const u = unit ? ` ${unit}` : "";
  return `[${signed(iv[0], digits)}, ${signed(iv[1], digits)}]${u}`;
}

export function fmtPct(p: number, digits = 0): string {
  return `${(p * 100).toFixed(digits)}%`;
}

export function fmtPctInterval(lo: number, hi: number, digits = 0): string {
  return `[${(lo * 100).toFixed(digits)}, ${(hi * 100).toFixed(digits)}]%`;
}

const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
export const dowName = (d: number) => DOW[((d % 7) + 7) % 7];

export function slotTime(slot: number): string {
  const h = Math.floor(slot / 4);
  const m = (slot % 4) * 15;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "never";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  return `${fmtDate(iso)}, ${fmtTime(iso)}`;
}

/**
 * Plain names for the actions whose id does not read as words once the underscores are gone ("OPEN_PR" is not "Open pr"). The programmer's and the data
 * analyst's actions are here; the benefits processor's and the shared ones read well from their ids ("COPY_TO_NOTE" is "Copy to note").
 */
const COG_NAMES: Record<string, string> = {
  // programmer
  READ_TRACE: "Read the error log", READ_CODE: "Read the code", EDIT_CODE: "Edit the code", RUN_TESTS: "Run the tests", REVIEW_DIFF: "Read the diff",
  INSPECT_INPUT: "Look at the real inputs", WRITE_TEST: "Write a test", PROBE_EDGE: "Try the edge cases", REPRODUCE_LOCALLY: "Reproduce it locally",
  BISECT_CHANGE: "Bisect the change", ADD_LOGGING: "Add logging", WRITE_COMMIT_MSG: "Write the commit message", OPEN_PR: "Open a pull request",
  READ_CI: "Read the CI result", ANSWER_REVIEW: "Answer review comments", REVIEW_PEER: "Review a colleague's change", WATCH_PROD: "Watch the release",
  ROLL_BACK: "Roll back a release", PROFILE_HOTPATH: "Profile the slow path", WRITE_MIGRATION: "Write a migration", SEARCH_DOCS: "Search the docs",
  // data analyst
  LOAD_DATA: "Load the data", PROFILE_DATA: "Profile the data", WRITE_QUERY: "Write the query", RUN_QUERY: "Run the query", INSPECT_RESULT: "Inspect the result",
  PLOT: "Plot it", EXPORT_RESULT: "Export the result", CLEAN_DATA: "Clean the data", RECONCILE_CONTROL: "Reconcile to a control total", GROUP_AGG: "Group and total",
  TRACE_SOURCE: "Trace the source", JOIN_TABLES: "Join the tables", SET_GRAIN: "Set the grain", CHECK_MAGNITUDE: "Check the size looks right",
  QUANTIFY_UNCERTAINTY: "Say how sure you are", WRITE_FINDING: "Write the finding", PEER_CHECK: "Ask for a second look", MAKE_REPRODUCIBLE: "Make it reproducible",
  PARAMETERISE_REPORT: "Parameterise the report", SCHEDULE_REFRESH: "Schedule the refresh", DOCUMENT_METRIC: "Document the metric",
};

/** COPY_TO_NOTE -> "Copy to note"; OPEN_PR -> "Open a pull request". Never throws: an id the service did not send is an empty label. */
export function cogLabel(cog: string): string {
  const id = typeof cog === "string" ? cog.trim() : "";
  if (id === "") return "";
  const known = COG_NAMES[id.toUpperCase()];
  if (known) return known;
  const s = id.toLowerCase().replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}
