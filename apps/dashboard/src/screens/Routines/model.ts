// Routines: what runs for the worker (Running) and what could (Could automate). Pure: no network, no React.
import type { Routine } from "../../types";

export type Tab = "running" | "could-automate";
export const TABS: { id: Tab; label: string }[] = [{ id: "running", label: "Running" }, { id: "could-automate", label: "Could automate" }];

/** `?tab=` from the address: anything but "could-automate" is Running. */
export const tabOf = (q: string | null | undefined): Tab => (q === "could-automate" ? "could-automate" : "running");

/** Routines the worker switched on: watching first, with approval, or while away. Most minutes a week first. */
export function runningRoutines(rs: Routine[] | null | undefined): Routine[] {
  return (rs ?? []).filter((r) => r.status === "shadow" || r.status === "approval" || r.status === "unattended")
    .map((r, i) => ({ r, i }))
    .sort((a, b) => b.r.minutes_per_week - a.r.minutes_per_week || a.i - b.i)
    .map((x) => x.r);
}

/** Routines the worker said no to. They can say yes again here. */
export const turnedDown = (rs: Routine[] | null | undefined): Routine[] => (rs ?? []).filter((r) => r.status === "declined" || r.status === "never");

/** A sentence of everything it touches, whole: "Touches a, b and c." */
export function touchesSentence(r: Pick<Routine, "touches" | "proposal">): string {
  const t = r.proposal.touches.length ? r.proposal.touches : r.touches;
  if (t.length === 0) return "";
  const head = t.length === 1 ? t[0] : `${t.slice(0, -1).join(", ")} and ${t[t.length - 1]}`;
  return `Touches ${head}.`;
}
