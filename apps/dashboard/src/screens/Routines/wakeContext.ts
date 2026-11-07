// What the dashboard tells the voice conversation about itself: the top Home insight and the running routine (docs/knack-ux/09-wake-voice.md, "The context
// packet"). Ids and counts only: the shell checks them against a strict grammar again, and a value that does not fit is dropped, not repaired. Nothing
// from a screen, a page, a file or a name ever goes through here. In a browser tab (no `window.knackShell.wake`) every call does nothing.
import { AGENT_URL } from "../../api";
import { wakeBridge, type WakeBridge, type WakeContext } from "../Settings/bridge";

/** The shape of an id the shell accepts: lower-case words, digits, dot, dash and underscore. */
export const ID_RE = /^[a-z0-9][a-z0-9_.-]{0,63}$/;

let current: WakeContext = {};
let timer: ReturnType<typeof setTimeout> | undefined;

/** Merge a change into what was last reported (null clears a part) and send the whole packet once, shortly after the last change. */
export function reportWake(patch: WakeContext, bridge: WakeBridge | null = wakeBridge(), delayMs = 250): void {
  current = { ...current, ...patch };
  if (!bridge) return;
  if (timer) clearTimeout(timer);
  timer = setTimeout(() => { void bridge.context(current).catch(() => undefined); }, delayMs);
}

/** The top Home insight, by its id and the template id the sentence was built from (Home calls this when it settles on a hero). */
export function reportInsight(id: string | null, template: string | null, bridge?: WakeBridge | null): void {
  reportWake({ insight: id && template && ID_RE.test(id) && ID_RE.test(template) ? { id, template } : null }, bridge);
}

/** What the agent says about a routine run: its state and one entry per navigator with its step. `steps_total` is additive: the total is only known when the agent says it. */
export interface RunStatus { state?: string; steps_total?: number; of?: number; navigators?: { step?: number; state?: string }[] }

/** The routine as the voice context wants it: `{ id, step, of }`, only while it runs and only when both numbers are really known. Never a guess. */
export function routineContext(id: string, s: RunStatus | null): { id: string; step: number; of: number } | null {
  if (!s || s.state !== "running" || !ID_RE.test(id)) return null;
  const of = [s.steps_total, s.of].find((n) => typeof n === "number" && Number.isInteger(n) && n > 0) as number | undefined;
  const done = Math.max(0, ...((s.navigators ?? []).map((n) => (typeof n.step === "number" && Number.isFinite(n.step) ? Math.floor(n.step) : 0))));
  if (!of) return null;
  return { id, step: Math.min(of, done + 1), of };
}

const TERMINAL = new Set(["done", "failed", "stopped", "completed", "cancelled", "killed", "unverified"]);
const tracking = new Map<string, ReturnType<typeof setInterval>>();

async function fetchStatus(runId: string): Promise<RunStatus | null> {
  try {
    const res = await fetch(`${AGENT_URL}/run/${encodeURIComponent(runId)}`);
    return res.ok ? ((await res.json()) as RunStatus) : null;
  } catch { return null; }
}

/**
 * Follow a routine run the worker started with Run now: every 3 s read its status (a GET) and report `{ id, step, of }` while it runs, then clear it.
 * One run at a time; it stops by itself when the run ends, goes missing or ten minutes pass.
 */
export function trackRoutineRun(routineId: string, runId: string, opts: { fetchStatus?: (id: string) => Promise<RunStatus | null>; bridge?: WakeBridge | null; everyMs?: number; maxMs?: number } = {}): () => void {
  const get = opts.fetchStatus ?? fetchStatus;
  const started = Date.now();
  const stop = () => { const t = tracking.get(runId); if (t) clearInterval(t); tracking.delete(runId); reportWake({ routine: null }, opts.bridge, 0); };
  if (tracking.has(runId)) return stop;
  const tick = async () => {
    const s = await get(runId);
    if (!s || TERMINAL.has(s.state ?? "") || Date.now() - started > (opts.maxMs ?? 600_000)) { stop(); return; }
    reportWake({ routine: routineContext(routineId, s) }, opts.bridge, 0);
  };
  tracking.set(runId, setInterval(() => void tick(), opts.everyMs ?? 3000));
  void tick();
  return stop;
}

/** For tests: forget what was reported and stop every follower. */
export function resetWakeContext(): void {
  current = {};
  if (timer) clearTimeout(timer);
  for (const t of tracking.values()) clearInterval(t);
  tracking.clear();
}
export const lastReported = (): WakeContext => current;
