// The worker's screens compare the worker with ONE experienced worker, unnamed, never with "the experts" as a group
// (docs/knack-ux/views.md). The engine's own sentences and labels still say "the experts"; this turns them into the worker's words at render time.
// Pure and idempotent: text that already says "an experienced worker" passes through unchanged.

const cap = (match: string, to: string): string => (/^[A-Z]/.test(match) ? to.charAt(0).toUpperCase() + to.slice(1) : to);

export function oneExpert(text: string): string {
  return text
    .replace(/\b(?:the )?reference experts'/gi, (m) => cap(m, "an experienced worker's"))
    .replace(/\bthe experts'/gi, (m) => cap(m, "an experienced worker's"))
    .replace(/\bthe experts\b/gi, (m) => cap(m, "an experienced worker"))
    .replace(/\bexperts'/gi, (m) => cap(m, "an experienced worker's"))
    .replace(/\b(?:the )?nearest expert('s)?\b/gi, (m, poss: string | undefined) => cap(m, `an experienced worker${poss ? "'s" : ""}`))
    .replace(/\bexperts\b/gi, (m) => cap(m, "an experienced worker"));
}

const UNITS = "people|persons|learners|workers|users|experts|novices|personas|participants|apprentices|colleagues|members|staff";
const COUNT = new RegExp(`\\b(?:n\\s*=\\s*)?\\d[\\d,]*\\s+(${UNITS})\\b`, "gi");

/** A group's size is not for a worker's screen ("n = 24 people" says nothing they can use, and counts other people): the group stays, the number goes. */
export function noCounts(text: string): string {
  return text.replace(COUNT, (_m, unit: string) => (/^experts$/i.test(unit) ? "an experienced worker" : /^people$/i.test(unit) ? "a group of people" : `a group of ${unit.toLowerCase()}`));
}

/** What the engine's words become on a worker's screen: no group of experts, no count of other people. */
export const workerText = (text: string): string => oneExpert(noCounts(text));

/**
 * Facts about the group the engine compared the worker with ("cohort_habit.pace.seconds", "gap.cohort_gap_s", "meta.n") are not for a worker's screen:
 * a sentence that rests on one is left out, and the fact is not offered in the list of numbers an explanation can use.
 */
export const isCohortFact = (path: string): boolean => /(^|[._])cohort|^meta\.n$|(^|\.)n_(?:people|learners|experts|novices)\b/i.test(path);
export const restsOnCohort = (uses: string[] | undefined): boolean => (uses ?? []).some(isCohortFact);
/** A limit that speaks of the group's average or the cohort has nothing to qualify on a worker's screen. */
export const aboutCohort = (text: string): boolean => /\bcohort\b|\baverage over (?:all|the)\b/i.test(text);
