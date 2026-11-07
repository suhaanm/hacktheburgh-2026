import type { OnboardingAnswers, OnboardingQuestions } from "../types";

const PACE: Record<string, string> = { slow: "slowly", gradual: "gradually", fast: "quickly" };
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function daysText(days: number[]): string {
  if (!days.length) return "no fixed days";
  const s = [...days].sort((a, b) => a - b);
  const runs: string[] = [];
  let a = s[0], prev = s[0];
  const flush = () => runs.push(a === prev ? DAYS[a] : `${DAYS[a]} to ${DAYS[prev]}`);
  for (const d of s.slice(1)) {
    if (d === prev + 1) prev = d;
    else { flush(); a = d; prev = d; }
  }
  flush();
  return runs.join(", ");
}

const labelOf = (q: OnboardingQuestions | undefined, id: string, v: string) =>
  q?.questions.find((x) => x.id === id)?.options.find((o) => o.value === v)?.label ?? v;

/**
 * The draft memory file shown while the worker answers. The engine writes the real file on submit;
 * this keeps the preview honest by using only what the worker has said plus the role pack's defaults.
 * Every line that comes from an answer is listed in `fresh` so the screen can highlight it.
 */
export function buildPreview(role: string, q: OnboardingQuestions | undefined, a: Partial<OnboardingAnswers>): { text: string; fresh: Set<number> } {
  const L: string[] = [];
  const fresh = new Set<number>();
  const add = (s: string, isNew = false) => { if (isNew) fresh.add(L.length); L.push(s); };
  const tone = a.tone ?? q?.pack.tone_defaults.length ?? "short";
  const voice = q?.pack.tone_defaults.voice ?? "plain";
  add("---");
  add(`role: ${role || "(choose a role)"}`);
  add("revision: 1");
  add("---");
  add("## Preferences");
  add(`- Summaries: ${tone}. Tone: ${voice}.`, !!a.tone);
  add(`- Help fades: ${PACE[a.pace ?? "gradual"] ?? a.pace}.`, !!a.pace);
  if (a.hours) add(`- Working hours: ${daysText(a.hours.days)}, ${a.hours.start} to ${a.hours.end}.`, true);
  if (a.capture === true) add("- Capture: times only", true);
  add("## Procedure");
  add("- (learned from your own work, never from page text)");
  add("## Routines");
  add("- (none yet. You choose each one.)");
  add("## Corrections");
  add("- (3 consistent corrections become a proposed rule)");
  add("## Skill state");
  const cogs = q?.pack.extra_cogs ?? [];
  add(cogs.length ? `- starts empty; this role tracks ${cogs.slice(0, 3).map((c) => c.toLowerCase().replace(/_/g, " ")).join(", ")} and more` : "- starts empty");
  add("## Never");
  const risky = a.risky ?? [];
  if (risky.length) add(`- ${risky.map((r) => labelOf(q, "risky", r).toLowerCase()).join("; ")} without me`, true);
  else add(`- ${(q?.pack.risk_classes.irreversible ?? ["submit", "send"]).join(", ")} without me (role default)`);
  if (a.tools?.length) { add("## Tools"); add(`- ${a.tools.map((t) => labelOf(q, "tools", t)).join("; ")}`, true); }
  return { text: L.join("\n"), fresh };
}
