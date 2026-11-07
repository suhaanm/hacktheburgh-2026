// The one-quantity rule (docs/KNACK_UX.md section 4): a worker-facing sentence carries at most one quantity, a count ("1 thing needs you") or a
// measure ("about 35 seconds"), never both. A range with its interval counts as one, and so does a rate ("58 times in 3 weeks", "about 1 hour a week")
// or a fraction ("3 of 8", "17 of your last 20 cases"). Dates, times and ids are not quantities. Pure; copy-lint tests and the Home model tests use it.

const MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December";
const WORDS = "one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve";
const NUM = String.raw`\d+(?:\.\d+)?`;

/** Patterns that are not quantities, or that are several numbers read as one. Applied in order; each match is replaced by a neutral token. */
const NEUTRAL: RegExp[] = [
  new RegExp(String.raw`\b\d{1,2}(?:st|nd|rd|th)?\s+(?:${MONTHS})(?:\s+\d{4})?\b`, "gi"), // 9 November, 9 November 2026
  new RegExp(String.raw`\b(?:${MONTHS})\s+\d{1,2}\b`, "gi"), // November 9
  /\b\d{1,2}:\d{2}(?::\d{2})?\b/g, // 09:00, 17:30
  /\b\d{4}-\d{2}-\d{2}\b/g, // 2026-11-09
  /\b[A-Za-z]+[-_][A-Za-z0-9_-]*\d[A-Za-z0-9_-]*\b/g, // CN-2041, p_f_bp05, i_6dd1d0
  /\b[A-Za-z]+\d+[A-Za-z0-9]*\b/g, // A2, S2, calculator3
];
/** One quantity written with several numbers. */
const AS_ONE: RegExp[] = [
  new RegExp(String.raw`\b${NUM}\s*(?:to|-|–)\s*${NUM}\b`, "g"), // 4 to 7, 2.4 to 4.5, 35-40
  new RegExp(String.raw`\b${NUM}\s+of\s+(?:your\s+|the\s+|these\s+|those\s+)?(?:last\s+|first\s+|top\s+)?${NUM}\b`, "g"), // 3 of 8, 17 of your last 20
  new RegExp(String.raw`\b${NUM}\s+\w+\s+(?:in|over|across)\s+(?:the\s+last\s+)?${NUM}\s+\w+\b`, "g"), // 58 times in 3 weeks
  new RegExp(String.raw`\b${NUM}\s+\w+\s+(?:a|per|each|every)\s+\w+\b`, "g"), // 1 hour a week, 35 seconds per case
];

export function quantitiesIn(sentence: string): number {
  let s = sentence;
  for (const re of NEUTRAL) s = s.replace(re, " ");
  let groups = 0;
  for (const re of AS_ONE) s = s.replace(re, () => { groups += 1; return " "; });
  const digits = s.match(new RegExp(String.raw`\b${NUM}\b`, "g"))?.length ?? 0;
  const words = s.match(new RegExp(String.raw`\b(?:${WORDS})\b`, "gi"))?.length ?? 0;
  return groups + digits + words;
}

/** Sentences of a text. A full stop inside a number (3.4) does not end one. */
export const sentencesOf = (text: string): string[] => text.split(/(?<=[.!?])(?<!\d\.)\s+(?=[A-Z0-9])/).map((x) => x.trim()).filter(Boolean);

/** True when every sentence carries at most `max` quantities. */
export function oneQuantity(text: string, max = 1): boolean {
  return sentencesOf(text).every((s) => quantitiesIn(s) <= max);
}

/** The sentences that break the rule, for a lint message. */
export const offenders = (text: string, max = 1): string[] => sentencesOf(text).filter((s) => quantitiesIn(s) > max);
