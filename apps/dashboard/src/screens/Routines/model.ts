// Routines: what runs for the worker (Running) and what could (Could automate). Pure: no network, no React.
import { arr, num, uniqueBy } from "../../lib/safeText";
import type { Routine } from "../../types";

export type Tab = "running" | "could-automate";
export const TABS: { id: Tab; label: string }[] = [{ id: "running", label: "Running" }, { id: "could-automate", label: "Could automate" }];

/** `?tab=` from the address: anything but "could-automate" is Running. */
export const tabOf = (q: string | null | undefined): Tab => (q === "could-automate" ? "could-automate" : "running");

const idOf = (r: Routine, i: number): string => (typeof r?.id === "string" && r.id ? r.id : `#${i}`);
/** Real routines only, each id once (the first): a list the engine sent twice, or with a hole in it, is still a list. */
const routinesOf = (rs: unknown): Routine[] => uniqueBy<Routine>(rs, idOf);

/** Routines the worker switched on: watching first, with approval, or while away. Most minutes a week first; a missing or odd number counts as none. */
export function runningRoutines(rs: Routine[] | null | undefined): Routine[] {
  const mpw = (r: Routine): number => num(r.minutes_per_week) ?? 0;
  return routinesOf(rs).filter((r) => r.status === "shadow" || r.status === "approval" || r.status === "unattended")
    .map((r, i) => ({ r, i }))
    .sort((a, b) => mpw(b.r) - mpw(a.r) || a.i - b.i)
    .map((x) => x.r);
}

/** Routines the worker said no to. They can say yes again here. */
export const turnedDown = (rs: Routine[] | null | undefined): Routine[] => routinesOf(rs).filter((r) => r.status === "declined" || r.status === "never");

/** A sentence of everything it touches, whole: "Touches a, b and c." */
export function touchesSentence(r: Pick<Routine, "touches" | "proposal">): string {
  const strings = (x: unknown): string[] => arr<unknown>(x).filter((v): v is string => typeof v === "string" && v.trim() !== "");
  const t = strings(r?.proposal?.touches).length ? strings(r.proposal.touches) : strings(r?.touches);
  if (t.length === 0) return "";
  const head = t.length === 1 ? t[0] : `${t.slice(0, -1).join(", ")} and ${t[t.length - 1]}`;
  return `Touches ${head}.`;
}

/** The headline of Routines: what is going on for the worker right now, most urgent first. Empty when nothing is (the empty state says it). */
export function routinesHeadline(i: { tasksRunning: number; routinesRunning: number; couldMinutes: number }): string {
  const { tasksRunning: t, routinesRunning: n, couldMinutes: m } = i;
  if (t > 0) return `${t === 1 ? "1 task is" : `${t} tasks are`} working in the background${n > 0 ? `, and ${n === 1 ? "1 routine runs" : `${n} routines run`} for you` : ""}.`;
  if (n > 0) return `${n === 1 ? "1 routine runs" : `${n} routines run`} for you.`;
  if (Number.isFinite(m) && m >= 30) return `About ${m >= 90 ? `${Math.round(m / 6) / 10} hours` : `${Math.round(m)} minutes`} a week could be handed over.`;
  return "";
}
