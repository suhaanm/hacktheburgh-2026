// Which pending item takes Home's hero slot. Something the worker must decide outranks something they could learn (docs/KNACK_UX.md section 4):
// an approval that blocks a running job, or a safety pause. Routine proposals, batch results and shadow mismatches wait in Needs you instead.
import type { QueueItem } from "../../types";

const BLOCKING: QueueItem["kind"][] = ["injection_pause", "irreversible_step", "outward_step"];

/** The safety pause first, then an irreversible step, then an outward one; the oldest of each kind first. Null when nothing blocks. */
export function blockingItem(items: readonly QueueItem[]): QueueItem | null {
  const pending = items.filter((x) => x.status === "pending" && BLOCKING.includes(x.kind));
  pending.sort((a, b) => BLOCKING.indexOf(a.kind) - BLOCKING.indexOf(b.kind) || a.created_at.localeCompare(b.created_at));
  return pending[0] ?? null;
}

/** The consequence, printed beside the buttons: never only in a hint. */
export function consequence(it: Pick<QueueItem, "kind" | "risk_class">): string | null {
  if (it.kind === "injection_pause") return "Paused for safety.";
  if (it.risk_class === "irreversible") return "Cannot be undone.";
  if (it.risk_class === "outward") return "Reaches outside.";
  return null;
}

export function decisionLabels(kind: QueueItem["kind"]): { yes: string; no: string } {
  switch (kind) {
    case "irreversible_step": return { yes: "Approve and submit", no: "Reject" };
    case "outward_step": return { yes: "Approve and send", no: "Reject" };
    case "injection_pause": return { yes: "Resume the run", no: "Cancel the run" };
    case "shadow_mismatch": return { yes: "Accept its answer", no: "Keep mine" };
    default: return { yes: "Approve", no: "Reject" };
  }
}

/** How many pending items remain for the "needs you" row once the hero has taken one. */
export const remainingAfter = (pending: number, heroTaken: boolean): number => Math.max(0, pending - (heroTaken ? 1 : 0));
