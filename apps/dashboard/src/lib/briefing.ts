import type { Prepared } from "../types";

/** Trim, and drop steps left empty, so what is saved is what the worker meant. */
export function cleanPrepared(p: Prepared): Prepared {
  const out: Prepared = {};
  if (typeof p.text === "string") out.text = p.text.trim();
  if (Array.isArray(p.steps)) out.steps = p.steps.map((s) => s.trim()).filter(Boolean);
  if (p.artifact_ref) out.artifact_ref = p.artifact_ref;
  return out;
}

export function preparedDirty(a: Prepared, b: Prepared): boolean {
  const x = cleanPrepared(a), y = cleanPrepared(b);
  return (x.text ?? "") !== (y.text ?? "") || JSON.stringify(x.steps ?? []) !== JSON.stringify(y.steps ?? []);
}

/** "in 5 h", "in 40 min", "tomorrow", or "expired". */
export function expiresIn(iso: string, now = Date.now()): string {
  const ms = new Date(iso).getTime() - now;
  if (Number.isNaN(ms)) return "";
  if (ms <= 0) return "expired";
  const min = Math.round(ms / 60000);
  if (min < 60) return `in ${Math.max(1, min)} min`;
  const h = Math.round(min / 60);
  return h < 24 ? `in ${h} h` : `in ${Math.round(h / 24)} d`;
}

export const RISK_LABEL: Record<string, string> = { normal: "Normal", outward: "Reaches outside", irreversible: "Cannot be undone" };
export const KIND_LABEL: Record<string, string> = {
  practice: "Practice", automate: "Automate", focus_block: "Focus block", git_habit: "Git habit", agent_result: "Agent result",
};

/** Plain words for what a fired card made: an approval item, a background run, or both unknown. */
export function firedText(f: { queue_id?: string; run_id?: string } | undefined): string {
  if (!f) return "";
  if (f.queue_id && f.run_id) return `Created approval item ${f.queue_id} and started background run ${f.run_id}.`;
  if (f.queue_id) return `Created approval item ${f.queue_id}. Nothing runs until you approve it in the Queue.`;
  if (f.run_id) return `Started background run ${f.run_id}. You can watch or stop it under Agents.`;
  return "Fired. The engine did not say what it created.";
}

/** The consequence of a card that is not routine, in words. It is printed on the card, never left in a Hint. Empty for a normal card. */
export function fireRisk(riskClass?: string): string {
  if (!riskClass || riskClass === "normal") return "";
  return `This one ${riskClass === "irreversible" ? "cannot be undone, so it always stops for your own click in the Queue" : "reaches outside this laptop, so it always stops for your own click in the Queue"}.`;
}

/** What pressing "Approve and run" does, by the card's fire type. Stated before the press, so there is no surprise. */
export function fireWhat(fireType: string | undefined, riskClass?: string): string {
  const risk = fireRisk(riskClass) ? ` ${fireRisk(riskClass)}` : "";
  switch (fireType) {
    case "queue": return `Creates an approval item in the Queue. Nothing runs until you approve it there.${risk}`;
    case "draft": return `Saves a local draft and creates an approval item in the Queue. Nothing is written anywhere else.${risk}`;
    case "agent": return `Starts a background run that only reads. You can watch it, or stop it, under Agents.${risk}`;
    default: return `It either creates an approval item for you to confirm, or starts a background run, and this card will say which.${risk}`;
  }
}

const PART_LABEL: Record<string, string> = { value: "Worth", urgency: "Urgency", freshness: "Freshness", acceptance: "Past acceptance", effort: "Effort" };
export interface RankPart { key: string; label: string; weight: number; contribution: number }
/** The parts of a card's score, largest contribution first. Effort carries a negative weight: it counts against the card. */
export function rankingParts(r: { parts?: Record<string, { x: number; w: number; contribution: number }> } | undefined): RankPart[] {
  return Object.entries(r?.parts ?? {})
    .map(([key, p]) => ({ key, label: PART_LABEL[key] ?? key, weight: p.w, contribution: p.contribution }))
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution));
}

/** The card's own words for what happened when it was checked, or a plain default. */
export function checkedNote(c: { verdict?: string; verify_note?: string }): string {
  if (c.verify_note) return c.verify_note;
  return c.verdict === "confirmed" ? "Checked just now: still true." : "";
}
