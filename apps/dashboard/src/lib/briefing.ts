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
