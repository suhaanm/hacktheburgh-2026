// Your data: what Knack remembers, measures and has sent, with a delete beside each. Pure: no network, no React.
import { plainWords } from "../NeedsYou/model";
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
export interface MemItem { id: string; section: string; text: string; /** The line as a worker reads it: sentences, never a code. `text` stays the file's own line (editing and forgetting need it). */ plain: string; note: string | null }
/** A note as the worker reads it: the id plumbing is dropped, a code such as `corr:summary_length=detailed` is dropped (the line already says it), and the seed's own label becomes "set up for you". */
export const cleanNote = (n: string | null): string | null => {
  const c = (n ?? "").replace(/^id:\S+\s*\|?\s*/, "").trim();
  if (!c || /^corr:\S+$/i.test(c) || /^onboarding\b/i.test(c)) return null;   // where a line came from is only worth a word when it is not the set-up itself
  if (/\bdemo\b/i.test(c)) return "set up for you";
  return c;
};

const humanSlug = (s: string): string => s.replace(/[-_]+/g, " ").replace(/\s+/g, " ").trim();
const sentence = (s: string): string => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

/**
 * A line of the memory file in the worker's words. The engine writes some lines as codes ("calc-entry-3x | rung A1 | consent: shadow | unattended: not allowed",
 * "reads-error-first: L1, streak 0, last seen never", "Checklist: read_case, then calc_a", "Run without my click: submit, close case"). Each becomes a sentence;
 * nothing is shown that reads like a granted permission (the last one is the list of steps that ALWAYS need a click, and says so). A line that is the
 * worker's own words is returned as it is.
 */
export function plainMemoryLine(text: string, section?: string): string {
  const t = (typeof text === "string" ? text : "").trim();
  let m = /^([\w.-]+)\s*\|\s*rung\s+A[0-3]\s*\|\s*consent:\s*([\w ]+?)\s*\|\s*unattended:\s*(.+)$/i.exec(t);
  if (m) {
    const set = /^none$/i.test(m[2]) ? "not switched on" : /^shadow$/i.test(m[2]) ? "set to watch first" : /^approval$/i.test(m[2]) ? "set to ask first" : /^unattended$/i.test(m[2]) ? "set to run while you are away" : `set to ${humanSlug(m[2]).toLowerCase()}`;
    const away = /not allowed|no\b|off|false/i.test(m[3]) ? "Away runs are off." : "Away runs are on.";
    return /^none$/i.test(m[2]) ? `${sentence(humanSlug(m[1]))} is ${set}.` : `${sentence(humanSlug(m[1]))} is ${set}. ${away}`;
  }
  m = /^([\w.-]+):\s*L(\d)\b(?:,\s*streak\s*\d+)?(?:,\s*last seen .*)?$/i.exec(t);
  if (m) return `Help on ${humanSlug(m[1])}: level ${m[2]}.`;
  m = /^Checklist:\s*(.+)$/i.exec(t);
  if (m) return `Checklist: ${m[1].replace(/_/g, " ")}`;
  m = /^Run without my click:\s*(.+)$/i.exec(t);
  if (m) return `Always asks you first before: ${m[1].replace(/_/g, " ").replace(/\.$/, "")}.`;
  // A line under 'Never' is read without its heading, so it says what it is.
  if (section === "Never" && t && !/^never\b/i.test(t)) return `Never: ${plainWords(t)}`;
  return plainWords(t);
}

export function memoryItems(m: Pick<Memory, "sections"> | null | undefined): MemItem[] {
  const sections = m?.sections && typeof m.sections === "object" ? m.sections : {};
  const names = [...SECTION_ORDER.filter((n) => n in sections), ...Object.keys(sections).filter((n) => !(SECTION_ORDER as readonly string[]).includes(n))];
  const seen = new Set<string>();
  return names.flatMap((section) => (Array.isArray(sections[section]) ? sections[section] : []).flatMap((l, i): MemItem[] => {
    if (!l || typeof l !== "object" || typeof l.text !== "string") return [];
    if (/^\(.*\)$/.test(l.text.trim())) return [];           // the file's own explanatory comment, not something Knack remembers about the worker
    const id = typeof l.id === "string" && l.id ? l.id : `${section}#${i}`;
    if (seen.has(id)) return [];          // the same line sent twice is one line: forgetting it must not be ambiguous
    seen.add(id);
    return [{ id, section, text: l.text, plain: plainMemoryLine(l.text, section), note: cleanNote(typeof l.note === "string" ? l.note : null) }];
  }));
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
export function factLine(id: YdSection, f: { lines: number; capture: boolean | null; entries: Pick<LedgerEntry, "status">[]; steps: number | null; shared: number | null; rules?: number }): string {
  switch (id) {
    case "remembers": return `${f.lines} ${f.lines === 1 ? "line" : "lines"}${f.rules ? `, ${f.rules} ${f.rules === 1 ? "rule" : "rules"} waiting` : ""}`;
    case "measured": return f.capture === null ? "" : f.capture ? "Times only" : "Capture off";
    case "sent": return "";             // the list is under Settings, Advanced; a worker's row holds one sentence and one link, and no count to read
    case "admin-sees": return f.shared === null ? "" : `${f.shared} summaries`;
    case "switches": return f.capture === null ? "" : f.capture ? "Capture on" : "Capture off";
  }
}

/** The wording of the capture consent, printed whole beside its switch. It says what is recorded, what never is, and where it stays. */
export const CAPTURE_TEXT = "It records when you are active, never what you read: no page text, no URLs, no field values. The record stays on this laptop.";

/** What forgetting the step counts clears, in the worker's words (the Growth curve is drawn from them), and what stays. */
export function stepForgetText(c: { assist: number; delegated: number; automation: number }): { question: string; consequence: string } {
  const total = c.assist + c.delegated + c.automation;
  return {
    question: `Forget ${total} ${total === 1 ? "row" : "rows"}?`,
    consequence: `This deletes ${total} ${total === 1 ? "row" : "rows"} of step counts on this computer (${c.assist} counted, ${c.delegated} done for you, ${c.automation} overnight), the answers you gave to Knack's questions, and the one-line summary in your memory file's Skill state section. It adds one line to the audit log with counts only. Your Growth curve starts again from nothing. Nothing else is touched.`,
  };
}

/* -- Delete everything: say exactly what is cleared ------------------------------------------------------------------------------------ */
export interface DeleteCounts { memoryLines: number; steps: number; calls: number; person: boolean }

/** The one sentence the confirm prints. Every part that will be cleared is named, with its count where Knack has one; what stays is named too. */
export function deleteAllText(c: DeleteCounts): { question: string; consequence: string } {
  const parts = [
    `${c.memoryLines} memory ${c.memoryLines === 1 ? "line" : "lines"}`,
    `${c.steps} step ${c.steps === 1 ? "count" : "counts"}`,
    `${c.calls} call ${c.calls === 1 ? "record" : "records"}`,
    "what it learned about notices",
    ...(c.person ? ["your cursor and app counts"] : []),
  ];
  const list = `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
  return {
    question: "Delete everything Knack holds about you?",
    consequence: `This clears ${list}, for good. Calls already sent are not recalled. Your role, settings and routines stay.`,
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

/** The headline of Your data: how much Knack remembers, and that it stays on this Mac. */
export function dataHeadline(i: { lines: number; capture: boolean | null }): string {
  const n = Math.max(0, Math.floor(i.lines));
  const base = n === 0 ? "Knack remembers nothing about you yet" : `Knack remembers ${n} ${n === 1 ? "thing" : "things"} about you`;
  return `${base}, on this Mac only${i.capture ? ", and learns from when you are active" : ""}.`;
}
