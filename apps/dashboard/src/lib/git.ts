import type { GitHabit, Interval } from "../types";

/** "p_git_learner_3" becomes "Learner 3". Anything else is shown as it is. */
export function learnerLabel(id: string): string {
  const m = /^p_git_learner_(\d+)$/.exec(id);
  return m ? `Learner ${m[1]}` : id;
}

/** A share (0 to 1) as a whole percent. Under half a percent shows one decimal so small shares do not read as zero. */
export function fmtShare(x: number): string {
  if (!Number.isFinite(x)) return "n/a";
  const p = x * 100;
  return Math.abs(p) > 0 && Math.abs(p) < 0.5 ? `${p.toFixed(1)}%` : `${Math.round(p)}%`;
}

const MINUS = "−";
/** A difference of shares in percentage points, with a real minus sign: "+19 pp", "−60 pp". */
export function fmtPoints(delta: number, digits = 0): string {
  if (!Number.isFinite(delta)) return "n/a";
  const p = delta * 100;
  const v = Math.abs(p).toFixed(digits);
  if (Number(v) === 0) return `0 pp`;
  return `${p < 0 ? MINUS : "+"}${v} pp`;
}

export function fmtPointsInterval(ci: Interval): string {
  if (!Array.isArray(ci) || !Number.isFinite(ci[0]) || !Number.isFinite(ci[1])) return "no interval";
  const f = (x: number) => { const p = Math.round(x * 100); return `${p < 0 ? MINUS : ""}${Math.abs(p)}`; };
  return `[${f(ci[0])}, ${f(ci[1])}] pp`;
}

export interface HabitReading {
  /** The engine's verdict: the difference is past its floor and its interval excludes zero. */
  flagged: boolean;
  /** Which way the difference points for this habit: worse than the experts, better, or neither. */
  direction: "worse" | "better" | "same";
  /** Plain words for the state. */
  state: string;
  /** Plain words for the direction ("more often than the experts"). */
  words: string;
}

/** The interval excludes zero: the difference is unlikely to be noise at this sample size. */
export const excludesZero = (ci: Interval): boolean => ci[0] > 0 || ci[1] < 0;

export function readHabit(h: Pick<GitHabit, "delta" | "ci" | "bad" | "flagged" | "reason" | "min_delta">): HabitReading {
  const bad = h.bad ?? 1;
  const worse = bad * h.delta > 0;
  const flagged = h.flagged === true;
  const more = h.delta > 0;
  const words = Math.abs(h.delta) < 0.005 ? "about the same as the experts" : `${more ? "more" : "less"} often than the experts`;
  let state: string;
  if (flagged) state = "Differs clearly";
  else if (h.reason === "below_min_delta") state = h.min_delta != null ? `Under the ${Math.round(h.min_delta * 100)} pp floor` : "Too small to act on";
  else if (!excludesZero(h.ci)) state = "Could be noise";
  else state = h.reason ? h.reason.replace(/_/g, " ") : "Not flagged";
  return { flagged, direction: Math.abs(h.delta) < 0.005 ? "same" : worse ? "worse" : "better", state, words };
}

/** Flagged habits first, largest difference first; the rest follow in the same order. */
export function sortHabits<T extends Pick<GitHabit, "delta" | "flagged">>(habits: T[]): T[] {
  return [...habits].sort((a, b) => Number(b.flagged === true) - Number(a.flagged === true) || Math.abs(b.delta) - Math.abs(a.delta));
}

/** The symmetric axis (in share units) that holds every interval, rounded up to a tidy number of points. */
export function habitAxis(habits: Pick<GitHabit, "delta" | "ci" | "min_delta">[]): number {
  const m = Math.max(0.05, ...habits.flatMap((h) => [Math.abs(h.delta), Math.abs(h.ci[0]), Math.abs(h.ci[1]), h.min_delta ?? 0]));
  // Axes whose half is a whole number of points (±10 with 5, ±20 with 10, ±40 with 20 ...), so every tick is readable.
  const ladder = [0.1, 0.2, 0.4, 0.6, 0.8, 1];
  return ladder.find((a) => a >= m - 1e-9) ?? 1;
}

export function gitHeadline(habits: GitHabit[]): string {
  const n = habits.filter((h) => h.flagged).length;
  if (habits.length === 0) return "No commit habits to compare yet";
  if (n === 0) return "No commit habit stands out from the experts";
  return n === 1 ? "One commit habit differs clearly from the experts" : `${n} commit habits differ clearly from the experts`;
}

export const DIGEST_LABEL: Record<string, string> = { model: "A model on this laptop summarised the commits", rules: "Fixed rules summarised the commits" };

/** Break a label into at most two lines near the middle, at a space. */
export function wrapLabel(label: string, max = 34): string[] {
  if (label.length <= max) return [label];
  const words = label.split(" ");
  let best = [label, ""], bestGap = Infinity;
  for (let i = 1; i < words.length; i++) {
    const a = words.slice(0, i).join(" "), b = words.slice(i).join(" ");
    const gap = Math.abs(a.length - b.length);
    if (a.length <= max && b.length <= max + 6 && gap < bestGap) { best = [a, b]; bestGap = gap; }
  }
  return best[1] ? best : [label.slice(0, max - 1) + "…"];
}

/**
 * A suggestion sentence with its counts taken out, so the counts can sit behind a Hint: "22% of your commits changed more than 250 lines
 * (28 of 127); the reference experts' share is 3%." becomes the sentence without "(28 of 127)", and the counts with what they refer to.
 */
export function splitCounts(sentence: string): { text: string; counts: string | null } {
  const m = /\s*\((\d[\d,]* of \d[\d,]*)\)/.exec(sentence);
  if (!m) return { text: sentence, counts: null };
  const text = sentence.replace(m[0], "").replace(/;\s*the reference experts' share is (\d+%)\.?$/, ".").trim();
  const expert = /the reference experts' share is (\d+%)/.exec(sentence);
  return { text, counts: `${m[1]} commits${expert ? `; the reference experts' share is ${expert[1]}` : ""}.` };
}
