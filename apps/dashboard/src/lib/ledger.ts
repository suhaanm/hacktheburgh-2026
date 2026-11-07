import type { LedgerEntry, PrivacySummary } from "../types";

export const PURPOSE_LABEL: Record<string, string> = {
  briefing_wording: "Wording a briefing card",
  calendar_suggestion_wording: "Wording a calendar suggestion",
  commit_digest_summary: "Summarising commit digests",
  worker_requested_step: "A step you asked for",
  weekly_summary_wording: "Wording the weekly summary",
};
export const purposeLabel = (p: string): string => PURPOSE_LABEL[p] ?? p.replace(/_/g, " ");

export function fmtBytes(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "size not known";
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(2)} GB`;
}

/** Calls by purpose, most first. */
export function purposesSorted(by: Record<string, number>): [string, number][] {
  return Object.entries(by).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

/** Calls today (local day) by purpose, from the ledger itself, so the summary and the list can never disagree. A blocked row is not a call: nothing was sent. */
export function callsToday(entries: Pick<LedgerEntry, "t" | "purpose" | "status">[], now = new Date()): Record<string, number> {
  const out: Record<string, number> = {};
  const day = now.toDateString();
  for (const e of entries) if (e.status !== "blocked" && new Date(e.t).toDateString() === day) out[e.purpose] = (out[e.purpose] ?? 0) + 1;
  return out;
}

/* -- Screen frames. The ledger never holds a picture or any text read off one: only size, a short hash, the model and the verdict. -- */
export const BLOCK_REASON: Record<string, string> = {
  unattended: "A background run may never look at your real screen.",
  no_consent: "You have not opted in to screen glances.",
  secure_input: "A password or other secure field was in focus.",
  denylisted_app: "The app in front is on the list you keep private.",
};
export const blockReasonLabel = (r: string | null | undefined): string => (r && BLOCK_REASON[r]) || (r ? r.replace(/_/g, " ") : "The gate refused it.");

export const IMAGE_KIND_LABEL: Record<string, string> = { glance: "Screen glance", point: "Pointing at a target", verify: "Checking an agent's work", live_frame: "Live frame" };
export const SOURCE_LABEL: Record<string, string> = { real_screen: "Your real screen", sandbox: "A sandbox site" };
export const sourceLabel = (s: string | null | undefined): string => (s && SOURCE_LABEL[s]) || (s ? s.replace(/_/g, " ") : "Unknown source");

export type RowClass = "text" | "image" | "image_blocked";
export function rowClass(e: Pick<LedgerEntry, "kind" | "status">): RowClass {
  if (e.kind !== "image") return "text";
  return e.status === "blocked" ? "image_blocked" : "image";
}

export type LedgerFilter = "all" | "text" | "images" | "blocked";
export function filterLedger<T extends Pick<LedgerEntry, "kind" | "status">>(entries: T[], f: LedgerFilter): T[] {
  if (f === "all") return entries;
  return entries.filter((e) => { const c = rowClass(e); return f === "text" ? c === "text" : f === "images" ? c !== "text" : c === "image_blocked"; });
}

/** Rows that really sent something to a model. Blocked rows are listed but are not calls. */
export const sentRows = <T extends Pick<LedgerEntry, "status">>(entries: T[]): T[] => entries.filter((e) => e.status !== "blocked");

/** A count map as labelled lines, largest first. */
export function countLines(by: Record<string, number> | undefined, label: (k: string) => string): { key: string; label: string; n: number }[] {
  return Object.entries(by ?? {}).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([key, n]) => ({ key, label: label(key), n }));
}

/** "640 x 400" or "size not recorded". */
export function imageSize(e: Pick<LedgerEntry, "image">): string {
  const w = e.image?.width, h = e.image?.height;
  return typeof w === "number" && typeof h === "number" ? `${w} × ${h} px` : "size not recorded";
}

/** The file the worker can save: exactly what is listed, as it was sent. */
export function exportLedger(entries: LedgerEntry[]): string {
  return JSON.stringify({ exported_at: new Date().toISOString(), note: "Egress ledger from this laptop. Payloads are exactly as sent.", entries }, null, 2);
}

export interface CanaryReading { tone: "clear" | "leak" | "none"; text: string }
/** The canary result in plain words. It is a test with planted strings: evidence, not proof. */
export function canaryReading(c: PrivacySummary["canary"]): CanaryReading {
  if (!c || !c.runs) return { tone: "none", text: "The canary check has not run yet." };
  if (c.leaked > 0) return { tone: "leak", text: `${c.leaked} of ${c.planted} planted test strings appeared in an outbound request across ${c.runs} runs. This is a leak and must be fixed.` };
  return { tone: "clear", text: `None of the ${c.planted} planted test strings (names, emails, titles, paths, commit messages) appeared in an outbound request across ${c.runs} runs. That is evidence from a test, not a proof.` };
}
