// Live updates for the screens that show work in progress (Needs you, Routines, the background tasks list): the page refreshes itself, so a task that
// finishes in the background shows as finished without the worker leaving and coming back. Owner request REQ-15, 8 Nov 2026.
//
// How, in this order:
//   1. A run the page knows by id has an event stream on the agent service (GET /run/{id}/stream, server-sent events). Every event asks for one refresh
//      (at most one every 400 ms); the `end` event asks for a last one and closes it. A stream that cannot open or breaks is dropped and polling covers it.
//   2. Polling: every 2 s while any run is active, every 15 s otherwise. A poll waits for the one before it to finish, so a slow engine is not hammered.
//   3. The window coming back into focus, or the tab becoming visible, refreshes at once.
// A refresh only calls the screen's own reload, which keeps the last good data on screen while it loads: an open row stays open and the scroll stays
// where it was. Nothing here stores anything or sends anything but the GETs the screen already makes.
import { useEffect, useRef, useSyncExternalStore } from "react";
import { AGENT_URL } from "../api";

export const FAST_MS = 2000;
export const SLOW_MS = 15000;
const STREAM_THROTTLE_MS = 400;
const FOCUS_DEBOUNCE_MS = 500;
const MAX_STREAMS = 4;
const RETRY_STREAM_MS = 30_000;
/** After a poke (something was just started or answered) the screens ask every 2 s for this long, even if nothing shows as running yet. */
const BOOST_MS = 30_000;

const controllers = new Set<LiveController>();
/** Something the worker just did (sent a task, answered a card) may change what a screen shows: every live screen refreshes now and asks fast for half a minute. */
export function pokeLive(): void { for (const c of [...controllers]) c.poke(); }

/** The parts of the browser the controller needs, so a test can give it a fake clock and a fake stream. */
export interface LiveEnv {
  setTimeout(fn: () => void, ms: number): unknown;
  clearTimeout(id: unknown): void;
  now(): number;
  /** A stream opener, or null when the browser has none. */
  openStream: ((url: string) => LiveStream) | null;
  /** Calls `fn` when the window gains focus or the tab becomes visible; returns the remover. */
  onWake(fn: () => void): () => void;
  /** True while the tab is hidden: nothing is polled then (it refreshes when the tab comes back). */
  hidden(): boolean;
}
export interface LiveStream {
  close(): void;
  onevent: ((name: string) => void) | null;
  onerror: (() => void) | null;
}

export interface LiveState {
  active: boolean;
  /** Ids of runs that have a stream on the agent's run route. */
  streams: string[];
  /** Stream addresses used as given (the tasks service's event stream). */
  urls?: string[];
}

/**
 * The controller behind the hook: pure of React, driven by an environment. `update` says whether anything is running and which runs have a stream; it
 * returns nothing and can be called as often as the screen renders. `stop` ends every timer and stream.
 */
export class LiveController {
  private state: LiveState = { active: false, streams: [], urls: [] };
  private failedAt = 0;
  private timer: unknown = null;
  private busy = false;
  private stopped = false;
  private lastStream = -Infinity;
  private streamTimer: unknown = null;
  private focusAt = -Infinity;
  private open = new Map<string, LiveStream>();
  private failed = new Set<string>();
  private off: () => void;
  private boostUntil = -Infinity;

  constructor(private reload: () => unknown, private env: LiveEnv) {
    this.off = env.onWake(() => this.wake());
    controllers.add(this);
  }

  /** Refresh now and keep the fast pace for a while. */
  poke(): void {
    if (this.stopped) return;
    this.boostUntil = this.env.now() + BOOST_MS;
    void this.refresh();
    this.schedule();
  }

  update(next: LiveState): void {
    if (this.stopped) return;
    const was = this.state.active;
    this.state = { active: next.active, streams: next.streams.slice(0, MAX_STREAMS), urls: (next.urls ?? []).slice(0, MAX_STREAMS) };
    this.syncStreams();
    if (this.timer === null || was !== next.active) this.schedule();
  }

  stop(): void {
    this.stopped = true;
    if (this.timer !== null) this.env.clearTimeout(this.timer);
    if (this.streamTimer !== null) this.env.clearTimeout(this.streamTimer);
    this.timer = this.streamTimer = null;
    for (const s of this.open.values()) s.close();
    this.open.clear();
    this.off();
    controllers.delete(this);
  }

  /** The delay before the next poll: fast while a run is active, slow otherwise. */
  delay(): number { return this.state.active || this.env.now() < this.boostUntil ? FAST_MS : SLOW_MS; }

  private schedule(): void {
    if (this.stopped) return;
    if (this.timer !== null) this.env.clearTimeout(this.timer);
    this.timer = this.env.setTimeout(() => { this.timer = null; void this.poll(); }, this.delay());
  }

  private async poll(): Promise<void> {
    if (this.stopped) return;
    // A stream that broke is tried again after half a minute (a service that restarted comes back).
    if (this.failed.size > 0 && this.env.now() - this.failedAt >= RETRY_STREAM_MS) { this.failed.clear(); this.syncStreams(); }
    if (!this.env.hidden()) await this.refresh();
    this.schedule();
  }

  /** One refresh, never two at once. */
  private async refresh(): Promise<void> {
    if (this.busy || this.stopped) return;
    this.busy = true;
    try { await this.reload(); } catch { /* a failed refresh leaves the screen as it was; the next poll tries again */ }
    finally { this.busy = false; }
  }

  private wake(): void {
    const t = this.env.now();
    if (this.stopped || t - this.focusAt < FOCUS_DEBOUNCE_MS || this.env.hidden()) return;
    this.focusAt = t;
    void this.refresh();
  }

  /** An event from a stream: refresh now unless one ran in the last 400 ms, in which case one refresh is queued for when that time is up. */
  private streamEvent(name: string, id: string): void {
    if (this.stopped) return;
    if (name === "end") { this.closeStream(id); this.failed.add(id); this.failedAt = this.env.now(); void this.refresh(); return; }
    const t = this.env.now();
    const wait = STREAM_THROTTLE_MS - (t - this.lastStream);
    if (wait <= 0) { this.lastStream = t; void this.refresh(); return; }
    if (this.streamTimer === null) this.streamTimer = this.env.setTimeout(() => { this.streamTimer = null; this.lastStream = this.env.now(); void this.refresh(); }, wait);
  }

  private closeStream(id: string): void {
    const s = this.open.get(id);
    if (s) { s.close(); this.open.delete(id); }
  }

  private wanted(): string[] {
    return [...this.state.streams.map((id) => `${AGENT_URL}/run/${encodeURIComponent(id)}/stream`), ...(this.state.urls ?? [])].slice(0, MAX_STREAMS);
  }

  private syncStreams(): void {
    if (!this.env.openStream) return;
    const want = this.wanted();
    for (const url of [...this.open.keys()]) if (!want.includes(url)) this.closeStream(url);
    for (const url of want) {
      if (this.open.has(url) || this.failed.has(url)) continue;
      try {
        const s = this.env.openStream(url);
        s.onevent = (name) => this.streamEvent(name, url);
        s.onerror = () => { this.failed.add(url); this.failedAt = this.env.now(); this.closeStream(url); };      // polling covers it
        this.open.set(url, s);
      } catch { this.failed.add(url); this.failedAt = this.env.now(); }
    }
  }
}

/** The browser's own parts. */
export function browserEnv(): LiveEnv {
  return {
    setTimeout: (fn, ms) => window.setTimeout(fn, ms),
    clearTimeout: (id) => window.clearTimeout(id as number),
    now: () => Date.now(),
    openStream: typeof EventSource === "undefined" ? null : (url) => {
      const es = new EventSource(url);
      const out: LiveStream = { close: () => es.close(), onevent: null, onerror: null };
      for (const name of ["step", "state", "progress", "result", "approval", "end", "message", "snapshot", "task_started", "task_progress", "task_finished"]) es.addEventListener(name, () => out.onevent?.(name));   // "heartbeat" is left out: it says nothing changed
      es.onerror = () => out.onerror?.();
      return out;
    },
    onWake: (fn) => {
      const onVis = () => { if (document.visibilityState === "visible") fn(); };
      window.addEventListener("focus", fn);
      document.addEventListener("visibilitychange", onVis);
      return () => { window.removeEventListener("focus", fn); document.removeEventListener("visibilitychange", onVis); };
    },
    hidden: () => typeof document !== "undefined" && document.visibilityState === "hidden",
  };
}

/**
 * Keep a screen fresh. `reload` is the screen's own reload (it keeps the data on screen while it loads); `active` is true while any run is going;
 * `streams` are the ids of runs that have an event stream. Re-rendering with the same values does nothing.
 */
export function useLive(reload: () => unknown, active: boolean, streams: string[] = [], urls: string[] = []): void {
  const fn = useRef(reload);
  fn.current = reload;
  const ctl = useRef<LiveController | null>(null);
  useEffect(() => {
    const c = new LiveController(() => fn.current(), browserEnv());
    ctl.current = c;
    return () => { c.stop(); ctl.current = null; };
  }, []);
  const key = streams.join(",");
  const urlKey = urls.join(",");
  useEffect(() => { ctl.current?.update({ active, streams: key ? key.split(",") : [], urls: urlKey ? urlKey.split(",") : [] }); }, [active, key, urlKey]);
}

/* -- The runs that have an event stream ---------------------------------------------------------------------------------------------- */
// A run the page started itself (Run now) is on the agent's own run route, which has a stream. Runs listed by /agents/runs are in another namespace with no
// stream, so they are polled. The registry holds the ids of the first kind while they run; `trackRoutineRun` adds and removes them.
const registered = new Set<string>();
const listeners = new Set<() => void>();
let snapshot: string[] = [];
const publish = () => { snapshot = [...registered]; listeners.forEach((l) => l()); };
export const streamRegistry = {
  add(id: string) { if (id && !registered.has(id)) { registered.add(id); publish(); } },
  remove(id: string) { if (registered.delete(id)) publish(); },
  list: (): string[] => snapshot,
  clear() { registered.clear(); publish(); },
};
/** The ids of runs that have a stream right now, as a stable array (same array until something changes). */
export function useRegisteredStreams(): string[] {
  return useSyncExternalStore((cb) => { listeners.add(cb); return () => { listeners.delete(cb); }; }, () => snapshot, () => snapshot);
}
