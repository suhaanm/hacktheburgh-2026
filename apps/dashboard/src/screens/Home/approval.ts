// Which pending item takes Home's hero slot. Something the worker must decide outranks something they could learn (docs/KNACK_UX.md section 4):
// an approval that blocks a running job, or a safety pause. Routine proposals, batch results and practice-run differences wait in Needs you instead.
// The words, the labels and the consequence are Needs you's own (screens/NeedsYou/model.ts); this file only decides who takes the slot.
import type { QueueItem } from "../../types";

const BLOCKING: QueueItem["kind"][] = ["injection_pause", "irreversible_step", "outward_step"];

/** A pause for safety: a choice of equal weight, never given a primary button. */
export const isSafetyPause = (it: Pick<QueueItem, "kind">): boolean => it.kind === "injection_pause";

const when = (iso: string | null | undefined): number => { const t = iso ? Date.parse(iso) : NaN; return Number.isNaN(t) ? Infinity : t; };

/** The safety pause first, then an irreversible step, then an outward one; the oldest of each kind first (an item with no readable time goes last). Null when nothing blocks. */
export function blockingItem(items: readonly QueueItem[] | null | undefined): QueueItem | null {
  const pending = (items ?? []).filter((x) => x && x.status === "pending" && BLOCKING.includes(x.kind));
  pending.sort((a, b) => BLOCKING.indexOf(a.kind) - BLOCKING.indexOf(b.kind) || when(a.created_at) - when(b.created_at) || a.id.localeCompare(b.id));
  return pending[0] ?? null;
}

/** What an approval did with the step it released: "submitted", "none" (nothing to submit) or "failed". The answer may carry it at the top or inside `data`; anything else reads as unknown. */
export type Finalize = "submitted" | "none" | "failed";
export function finalizeOf(r: unknown): Finalize | null {
  const pick = (o: unknown): unknown => (o && typeof o === "object" ? (o as { finalize?: unknown }).finalize : undefined);
  const v = pick(r) ?? pick((r as { data?: unknown } | null | undefined)?.data);
  return v === "submitted" || v === "none" || v === "failed" ? v : null;
}

/** How many pending items remain for the "needs you" row once the hero has taken one. Never below zero, and a missing count is zero. */
export const remainingAfter = (pending: number, heroTaken: boolean): number => Math.max(0, (Number.isFinite(pending) ? pending : 0) - (heroTaken ? 1 : 0));
