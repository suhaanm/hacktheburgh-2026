import type { LedgerEntry, PrivacySummary } from "../types";

export const PURPOSE_LABEL: Record<string, string> = {
  briefing_wording: "Wording a briefing card",
  calendar_suggestion_wording: "Wording a calendar suggestion",
  commit_digest_summary: "Summarising commit digests",
  worker_requested_step: "A step you asked for",
  weekly_summary_wording: "Wording the weekly summary",
};
export const purposeLabel = (p: string): string => PURPOSE_LABEL[p] ?? p.replace(/_/g, " ");

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(2)} GB`;
}

/** Calls by purpose, most first. */
export function purposesSorted(by: Record<string, number>): [string, number][] {
  return Object.entries(by).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

/** Calls today (local day) by purpose, from the ledger itself, so the summary and the list can never disagree. */
export function callsToday(entries: Pick<LedgerEntry, "t" | "purpose">[], now = new Date()): Record<string, number> {
  const out: Record<string, number> = {};
  const day = now.toDateString();
  for (const e of entries) if (new Date(e.t).toDateString() === day) out[e.purpose] = (out[e.purpose] ?? 0) + 1;
  return out;
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
