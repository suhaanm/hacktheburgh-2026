// The one number the sidebar badge, the menu bar and the Dock all show: everything that waits on the worker (approvals, routine proposals,
// prepared actions, paused runs). The shell calls this on start and after a decision; Needs you calls it after every choice.
// It reads through the same api calls the screen uses (so example data counts as example data), and never throws.
import { api } from "../../api";
import { getState, setState } from "../../store";
import { buildItems, needsCount } from "./model";

export const DEMO_PERSON = "p_ninetofive";

/** Whose briefing and runs to count: the person the shell has already read, else the one the engine names now, and only when it names nobody the sample person.
 *  (The shell asks for the identity and for this count in the same tick, so the first count used to read the SAMPLE person's briefing: the badge said 7 while Needs you listed 2.) */
async function whoseCount(): Promise<string> {
  const known = getState().person;
  if (known) return known;
  const who = await api.identity().catch(() => null);
  return who?.person ?? DEMO_PERSON;
}

export async function loadNeedsCount(): Promise<number> {
  const person = await whoseCount();
  const [q, r, b, a, t] = await Promise.allSettled([api.queue("all"), api.routines(), api.briefing(person), api.agentsRuns(person), api.tasks()]);
  const ok = <T,>(x: PromiseSettledResult<T>): T | null => (x.status === "fulfilled" ? x.value : null);
  const bd = ok(b);
  return needsCount(buildItems({ queue: ok(q)?.data, routines: ok(r)?.data, cards: bd?.data.cards, cardsAt: bd?.data.generated_at, runs: ok(a)?.data, tasks: ok(t)?.source === "live" ? ok(t)?.data : null }));
}

/** Publish the count for the badge. Falls quiet on any failure: the badge is optional. */
export async function refreshNeedsBadge(): Promise<void> {
  try { setState({ pendingQueue: await loadNeedsCount() }); } catch { /* the badge is optional */ }
}
