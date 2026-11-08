// The cohort rule of docs/knack-ux/views.md as code the worker view can run on itself: a worker sees their own work and ONE experienced worker's way of doing
// the task, never other people, never an average of colleagues, never a count of people, never another person's id. Pure (no React, no DOM).
// The patterns are the FIRM rules of scripts/lib/view-rules.mjs (Track R's view audit), kept in step with it by cohortRules.test.ts; the audit is what
// checks a whole rendered page, this is what lets a screen that is still being rebuilt refuse to draw such a string at all.

export interface CohortRule { id: string; re: RegExp; why: string }

export const COHORT_RULES: CohortRule[] = [
  { id: "person-label", re: /\b(?:BP|DA|PR|PG)-\d{2}\b/g, why: "a firm member's label" },
  { id: "cohort-figure", re: /\b(?:average|mean|median|typical)\s+(?:over|across|of|for)\s+(?:all|everyone|the\s+firm|your\s+colleagues|colleagues|the\s+team|other\s+(?:workers|learners|people))\b/gi, why: "an average over other people" },
  { id: "cohort-figure", re: /\bacross\s+(?:the|your)\s+(?:firm|team|company|organisation|organization)\b/gi, why: "a firm or team figure" },
  { id: "cohort-figure", re: /\bfirm[- ]?wide\b|\bwhole\s+firm\b|\bthe\s+firm\b/gi, why: "the firm" },
  { id: "colleagues", re: /\bcolleagues?\b|\bco-?workers?\b|\bteammates?\b/gi, why: "other people as a group" },
  { id: "people-count", re: /\b\d[\d,]*\s+(?:people|persons|colleagues|workers|learners|users|staff|employees|juniors|experts|members)\b/gi, why: "a count of people" },
  { id: "other-people", re: /\b(?:other|all|most|many)\s+(?:learners|workers|people|juniors|novices|users)\b|\beveryone\s+else\b/gi, why: "other people as a group" },
  { id: "peer-rank", re: /\b(?:percentile|leaderboard)\b|\b(?:top|bottom)\s+\d+\s?%|\branked?\s+(?:#|no\.?\s*)?\d+\b|\bbetter\s+than\s+\d+\s?%/gi, why: "a ranking against other people" },
];

/** A person id has a number in it (p_learn01, p_exp06, p_f_bp03) or is one of the four named personas. Field names such as p_stuck are not ids. */
const PERSON_ID = /\bp_(?:irregular|nightowl|ninetofive|shiftwkr)\b|\bp_(?:[a-z]+_)*[a-z]*\d+[a-z0-9_]*\b/gi;

export interface CohortHit { rule: string; why: string; match: string }

/** Everything in `text` that breaks the rule. `ownId` is the worker's own person id: it is never a hit. */
export function cohortHits(text: unknown, ownId?: string | null): CohortHit[] {
  if (typeof text !== "string" || !text) return [];
  const out: CohortHit[] = [];
  for (const r of COHORT_RULES) {
    const re = new RegExp(r.re.source, r.re.flags);
    let m: RegExpExecArray | null;
    while ((m = re.exec(text))) {
      if (m[0] === "") { re.lastIndex++; continue; }
      // The size of a meeting on the worker's own calendar ("Meeting, 5 to 9 people") is their own data, not a count of colleagues.
      if (r.id === "people-count" && /meeting|call|workshop|session/i.test(text.slice(Math.max(0, m.index - 40), m.index))) continue;
      out.push({ rule: r.id, why: r.why, match: m[0] });
      if (out.length >= 20) return out;
    }
  }
  const own = (ownId ?? "").toLowerCase();
  for (const m of text.matchAll(PERSON_ID)) {
    if (own && m[0].toLowerCase() === own) continue;
    out.push({ rule: "person-id", why: "another person's id", match: m[0] });
    if (out.length >= 20) break;
  }
  return out;
}

export const breaksCohortRule = (text: unknown, ownId?: string | null): boolean => cohortHits(text, ownId).length > 0;
