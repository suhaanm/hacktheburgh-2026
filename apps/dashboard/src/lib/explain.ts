import type { ExplainAction, ExplainResult, ExplainSection, ExplainSentence, PacketFact } from "../types";
import { fmtDuration } from "./format";

/** The questions offered as chips. The text is what is sent; the id is only for the example answers shown when the engine is not there. */
export const CHIPS: { id: string; text: string }[] = [
  { id: "where_time_went", text: "Where did my time go?" },
  { id: "why_slow", text: "Why was I slow?" },
  { id: "biggest_habit", text: "What is my biggest habit?" },
  { id: "how_sure", text: "How sure are you?" },
  { id: "what_to_practise", text: "What should I practise?" },
];
export const MAX_QUESTION = 400;

/** What the badge says in the words the rest of the page uses. */
export function badgeText(b: ExplainResult["badge"]): string {
  const unit = b.n_unit === "people" ? (b.n === 1 ? "person" : "people") : b.n_unit;
  return `n = ${b.n.toLocaleString("en-GB")} ${unit}`;
}

export interface SourceReading { label: string; detail: string }

/** Where the words came from, in plain terms. Every source says the numbers were checked, and none claims the words are true. */
export function sourceReading(r: Pick<ExplainResult, "source" | "model">): SourceReading {
  switch (r.source) {
    case "local": return { label: "Written by a model on this laptop", detail: "The model saw only numbers and fixed ids, never your names or text." };
    case "cloud": return { label: "Written by a cloud model", detail: "It was sent only numbers and fixed ids, through the privacy guard, and the call is in the Privacy ledger." };
    default: return { label: "Written from a fixed template", detail: "No model wrote these words." };
  }
}

/** The check, in words. A pass says what was matched; it never says the numbers are true, only that they trace to the data. */
export function checkReading(c: ExplainResult["check"]): { ok: boolean; text: string } {
  const n = c.checked?.numbers, i = c.checked?.intervals, s = c.checked?.sentences;
  if (!c.ok) return { ok: false, text: "This answer did not pass the check, so do not rely on its numbers." };
  const parts = [typeof n === "number" ? `${n} ${n === 1 ? "number" : "numbers"}` : null, typeof i === "number" && i > 0 ? `${i} ${i === 1 ? "interval" : "intervals"}` : null].filter(Boolean);
  const what = parts.length ? parts.join(" and ") : typeof s === "number" ? `${s} ${s === 1 ? "sentence" : "sentences"}` : "every number";
  return { ok: true, text: `Checked by code: ${what} in these words match the data. That shows they come from the data, not that the data is right.` };
}

const REASON_WORDS: Record<string, string> = {
  schema: "the model's words did not follow the required form",
  provenance: "a number or name in the model's words did not match the data",
  timeout: "the model did not answer in time",
  unavailable: "the model was not available",
  mock_mode: "mock mode uses the template only",
};

/**
 * Did this answer come from the fixed template because a model's words were turned away? Returns the sentence to show, or null when
 * the template was simply the plan (mock mode, or no model is switched on).
 */
export function fallbackReading(r: Pick<ExplainResult, "source" | "fallback_reason" | "attempts">): string | null {
  const failed = r.attempts.filter((a) => !a.ok);
  if (r.source !== "template" || (failed.length === 0 && !r.fallback_reason)) return null;
  const reason = r.fallback_reason ?? failed[failed.length - 1]?.reason ?? null;
  const why = reason ? REASON_WORDS[reason] ?? reason.replace(/_/g, " ") : "a model's words could not be used";
  return `This answer came from the fixed template because ${why}. Nothing from the rejected words is shown.`;
}

/** The worker typed a time (such as 14 minutes): say whether it matches this case. Only the number is quoted back, never the question. */
export function askedTimeNote(q: ExplainResult["question"]): string | null {
  if (q.asked_s == null) return null;
  return q.matches_case === false
    ? `You mentioned about ${fmtDuration(q.asked_s)}. That does not match this case, so the answer is about the case as recorded.`
    : q.matches_case === true ? `You mentioned about ${fmtDuration(q.asked_s)}, which matches this case.` : null;
}

export const sectionOf = (r: ExplainResult, ...kinds: ExplainSection["kind"][]): ExplainSection | null => r.sections.find((s) => kinds.includes(s.kind)) ?? null;

/** The main words: the explanation, or the answer to a question. */
export function bodySentences(r: ExplainResult): ExplainSentence[] {
  const s = sectionOf(r, "explanation", "answer");
  return s && (s.kind === "explanation" || s.kind === "answer") ? s.sentences : [];
}
export function actionsOf(r: ExplainResult): ExplainAction[] {
  const s = sectionOf(r, "coaching");
  return s && s.kind === "coaching" ? s.actions : [];
}
export function limitsOf(r: ExplainResult): { id: string; text: string }[] {
  const s = sectionOf(r, "limits");
  return s && s.kind === "limits" ? s.sentences : [];
}

export function isAnswer(r: ExplainResult): boolean {
  return !!sectionOf(r, "answer");
}

/** A packet value with its unit, written for a person: seconds become minutes, shares become percent. */
export function fmtFact(f: Pick<PacketFact, "value" | "unit">): string {
  const v = f.value;
  switch (f.unit) {
    case "s": return Math.abs(v) >= 60 ? fmtDuration(v) : `${Math.round(v * 10) / 10} s`;
    case "share": case "p": case "probability": return `${Math.round(v * 1000) / 10}%`;
    case "gbp": return `£${Math.round(v).toLocaleString("en-GB")}`;
    case "count": return Number.isInteger(v) ? String(v) : String(Math.round(v * 100) / 100);
    default: return `${Math.round(v * 1000) / 1000}${f.unit ? ` ${f.unit}` : ""}`;
  }
}

/** The packet facts a sentence cites, in the order it cites them. A path the packet does not hold is kept, marked missing, so a gap is visible. */
export function usesWithFacts(uses: string[], facts: PacketFact[]): { path: string; fact: PacketFact | null }[] {
  const by = new Map(facts.map((f) => [f.path, f]));
  return uses.map((path) => ({ path, fact: by.get(path) ?? null }));
}

/** "gap.case_s" as "gap, case s": the path is a pointer into the packet, shown as it is but easier to read. */
export const pathWords = (p: string): string => p.replace(/\./g, " · ").replace(/_/g, " ");

/** A trimmed question ready to send: control characters out, whitespace collapsed, at most 400 characters. Empty becomes undefined (the default question). */
export function cleanQuestion(q: string): string | undefined {
  const spaced = q.replace(/\s+/g, " "); // tabs and line breaks become one space first, so words never run together
  const t = Array.from(spaced).filter((ch) => ch >= " " && ch !== "\u007f").join("").trim().slice(0, MAX_QUESTION);
  return t || undefined;
}
