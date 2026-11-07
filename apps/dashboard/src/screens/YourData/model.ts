// Your data: what Knack remembers, measures and has sent, with a delete beside each. Pure: no network, no React.
import { SECTION_ORDER } from "../../lib/memory";
import { sentRows } from "../../lib/ledger";
import type { LedgerEntry, Memory } from "../../types";

/** The section ids: the contract with the shell (`#/your-data?section=...`, the old Memory and Privacy addresses redirect to these). */
export const YD_SECTIONS = ["remembers", "measured", "sent", "admin-sees", "switches"] as const;
export type YdSection = (typeof YD_SECTIONS)[number];
export const YD_TITLE: Record<YdSection, string> = {
  remembers: "What Knack remembers",
  measured: "What it measures",
  sent: "What it looked at or sent",
  "admin-sees": "What your admin can see",
  switches: "Capture and screen glances",
};
export const ydSectionOf = (s: string | null | undefined): YdSection | null => ((YD_SECTIONS as readonly string[]).includes(s ?? "") ? (s as YdSection) : null);

/** The memory file's lines in reading order. Notes in the engine's file look like "id:l_ab12 | why": the id is plumbing, only the why is shown. */
export interface MemItem { id: string; section: string; text: string; note: string | null }
const cleanNote = (n: string | null): string | null => { const c = (n ?? "").replace(/^id:\S+\s*\|?\s*/, "").trim(); return c || null; };

export function memoryItems(m: Pick<Memory, "sections">): MemItem[] {
  const names = [...SECTION_ORDER.filter((n) => n in m.sections), ...Object.keys(m.sections).filter((n) => !(SECTION_ORDER as readonly string[]).includes(n))];
  return names.flatMap((section) => m.sections[section].map((l) => ({ id: l.id, section, text: l.text, note: cleanNote(l.note) })));
}

/** The memory file with every line removed and every heading kept, so the role and the shape of the file stay. */
export function clearItemsMarkdown(markdown: string): string {
  const out = markdown.replace(/\r\n/g, "\n").replace(/\n$/, "").split("\n").filter((l) => !/^\s*[-*]\s+/.test(l));
  return out.join("\n") + "\n";
}

/** One line for the model-call list: how many calls, how many were blocked. */
export function sentLine(entries: Pick<LedgerEntry, "status">[]): string {
  const sent = sentRows(entries).length;
  const blocked = entries.length - sent;
  if (entries.length === 0) return "Nothing sent";
  return `${sent} ${sent === 1 ? "call" : "calls"}${blocked ? `, ${blocked} blocked` : ""}`;
}

/** What each section says about itself while it is closed: a few words, never a sentence. */
export function factLine(id: YdSection, f: { lines: number; capture: boolean | null; entries: Pick<LedgerEntry, "status">[]; steps: number | null; shared: number | null }): string {
  switch (id) {
    case "remembers": return `${f.lines} ${f.lines === 1 ? "line" : "lines"}`;
    case "measured": return f.capture === null ? "" : f.capture ? "Times only" : "Capture off";
    case "sent": return sentLine(f.entries);
    case "admin-sees": return f.shared === null ? "" : `${f.shared} summaries`;
    case "switches": return f.capture === null ? "" : f.capture ? "Capture on" : "Capture off";
  }
}

/** The wording of the capture consent, printed whole beside its switch. It says what is recorded, what never is, and where it stays. */
export const CAPTURE_TEXT = "It records when you are active, never what you read: no page text, no URLs, no field values. The record stays on this laptop.";

/** What forgetting the step counts clears, in the worker's words (the Growth curve is drawn from them), and what stays. */
export function stepForgetText(c: { assist: number; delegated: number; automation: number }, example: boolean): { question: string; consequence: string } {
  const total = c.assist + c.delegated + c.automation;
  return {
    question: `Forget ${total} ${total === 1 ? "row" : "rows"}?`,
    consequence: `This deletes ${total} ${total === 1 ? "row" : "rows"} of step counts on this computer (${c.assist} counted, ${c.delegated} done for you, ${c.automation} overnight), the answers you gave to Knack's questions, and the one-line summary in your memory file's Skill state section. It adds one line to the audit log with counts only. Your Growth curve starts again from nothing. ${example ? "These rows are example data, so only this screen changes." : "Nothing else is touched."}`,
  };
}

/* -- Delete everything: say exactly what is cleared ------------------------------------------------------------------------------------ */
export interface DeleteCounts { memoryLines: number; steps: number; calls: number; person: boolean }

/** The one sentence the confirm prints. Every part that will be cleared is named, with its count where Knack has one; what stays is named too. */
export function deleteAllText(c: DeleteCounts): { question: string; consequence: string } {
  const parts = [
    `${c.memoryLines} ${c.memoryLines === 1 ? "line" : "lines"} of your memory file`,
    `${c.steps} ${c.steps === 1 ? "step count" : "step counts"}`,
    `${c.calls} ${c.calls === 1 ? "record" : "records"} of model calls`,
    "what Knack learned about how loud to speak",
    ...(c.person ? ["the counts of your cursor and apps"] : []),
  ];
  const list = `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
  return {
    question: "Delete everything Knack holds about you?",
    consequence: `This clears ${list}, on this Mac, for good. It does not recall anything already sent. Your role, settings and routines stay.`,
  };
}

export type DeletePart = { part: string; ok: boolean; note?: string };

/** After a delete: what was cleared and, if anything was not, which part and why. Nothing is claimed that did not happen. */
export function deleteResultText(parts: DeletePart[]): string {
  const bad = parts.filter((p) => !p.ok);
  if (bad.length === 0) return "Deleted. Everything listed was cleared.";
  const ok = parts.filter((p) => p.ok).map((p) => p.part);
  return `${ok.length ? `Cleared: ${ok.join(", ")}. ` : "Nothing was cleared. "}Not cleared: ${bad.map((p) => `${p.part}${p.note ? ` (${p.note})` : ""}`).join(", ")}. Try again.`;
}
