// The Monday note: a short plain-text note a worker can copy. The engine sends ready text when it has it (built from its fixed
// sentences); otherwise the page builds the same shape from the pointers' own sentences and fixed connecting words. Nothing typed
// here carries a number: every figure arrives inside a pointer sentence or the `try` item.
import type { WireWorker } from "../firm/wire";
import { APP_NAME } from "../../brand";

export const MONDAY_INTRO = (n: number): string => `${APP_NAME} has ${n} ${n === 1 ? "pointer" : "pointers"} for your week.`;
const END = (s: string): string => (/[.!?]$/.test(s.trim()) ? s.trim() : `${s.trim()}.`);

/** Null when there is nothing to say: a week with no pointers has no note. */
export function mondayNote(w: Pick<WireWorker, "pointers" | "try" | "monday_note">): string | null {
  const sent = w.monday_note?.trim();
  if (sent) return sent;
  if (w.pointers.length === 0) return null;
  const parts = [MONDAY_INTRO(w.pointers.length), ...w.pointers.map((p) => END(p.headline))];
  if (w.try) parts.push(`One thing to try: ${w.try.label.toLowerCase()}, ${w.try.value} ${w.try.unit}.`.replace(/\s+\./, "."));
  return parts.join(" ");
}

/** The note as lines, for display: one sentence per line, so a screen reader and a printed copy read it the same way. */
export const noteLines = (note: string): string[] => note.split(/(?<=[.!?])\s+/).map((s) => s.trim()).filter(Boolean);

/** Copy text to the clipboard. Returns false when the browser refuses (blocked clipboard, no secure context), so the page can say so. */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) { await navigator.clipboard.writeText(text); return true; }
  } catch { /* fall through to the older route */ }
  try {
    const ta = document.createElement("textarea");
    ta.value = text; ta.setAttribute("readonly", ""); ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    return ok;
  } catch { return false; }
}
