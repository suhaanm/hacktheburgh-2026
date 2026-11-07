// Batched, persistent delivery of L0 events to the engine (POST /events). The queue lives in storage so a
// service worker restart loses nothing; it is capped, and revoking consent clears it.
import type { L0Event } from "../shared/types";

export interface Stats {
  accepted: number;
  rejected: number;
  dropped: number;
  last_error: string | null;
  last_ok_at: string | null;
}

export interface BatcherDeps {
  fetch: typeof fetch;
  getUrl: () => Promise<string>;
  load: () => Promise<L0Event[]>;
  save: (q: L0Event[]) => Promise<void>;
  setTimer: (fn: () => void, ms: number) => unknown;
  clearTimer: (h: unknown) => void;
  now: () => number;
  onStats?: (s: Stats) => void;
}

export interface BatcherOpts {
  maxBatch: number;
  flushMs: number;
  maxQueue: number;
  backoffMaxMs: number;
}

const DEFAULT_OPTS: BatcherOpts = { maxBatch: 25, flushMs: 2000, maxQueue: 1000, backoffMaxMs: 60_000 };

export class Batcher {
  private queue: L0Event[] = [];
  private loaded = false;
  private timer: unknown = null;
  private flushing: Promise<void> | null = null;
  private fails = 0;
  private notBefore = 0;
  readonly stats: Stats = { accepted: 0, rejected: 0, dropped: 0, last_error: null, last_ok_at: null };
  private readonly opts: BatcherOpts;

  constructor(private readonly deps: BatcherDeps, opts: Partial<BatcherOpts> = {}) {
    this.opts = { ...DEFAULT_OPTS, ...opts };
  }

  private async ensureLoaded(): Promise<void> {
    if (this.loaded) return;
    this.loaded = true;
    const stored = await this.deps.load();
    this.queue = [...stored, ...this.queue].slice(-this.opts.maxQueue);
  }

  size(): number {
    return this.queue.length;
  }

  async add(ev: L0Event): Promise<void> {
    await this.ensureLoaded();
    this.queue.push(ev);
    if (this.queue.length > this.opts.maxQueue) {
      const over = this.queue.length - this.opts.maxQueue;
      this.queue.splice(0, over);
      this.stats.dropped += over;
    }
    await this.deps.save(this.queue);
    if (this.queue.length >= this.opts.maxBatch) void this.flush();
    else this.schedule(this.opts.flushMs);
  }

  /** The engine's identity replaced ours: unsent events join the engine's person instead of staying orphaned. */
  async retag(person: string, role: string): Promise<void> {
    await this.ensureLoaded();
    for (const ev of this.queue) {
      ev.person = person;
      ev.role = role;
    }
    await this.deps.save(this.queue);
  }

  /** Consent revoked: forget everything not yet sent. */
  async clear(): Promise<void> {
    await this.ensureLoaded();
    this.queue = [];
    if (this.timer !== null) this.deps.clearTimer(this.timer);
    this.timer = null;
    await this.deps.save([]);
  }

  private schedule(ms: number): void {
    if (this.timer !== null) return;
    this.timer = this.deps.setTimer(() => {
      this.timer = null;
      void this.flush();
    }, ms);
  }

  flush(): Promise<void> {
    if (this.flushing) return this.flushing;
    this.flushing = this.doFlush().finally(() => {
      this.flushing = null;
    });
    return this.flushing;
  }

  private async doFlush(): Promise<void> {
    await this.ensureLoaded();
    while (this.queue.length) {
      const wait = this.notBefore - this.deps.now();
      if (wait > 0) {
        this.schedule(wait);
        return;
      }
      const batch = this.queue.slice(0, this.opts.maxBatch);
      let status = 0;
      let body: unknown = null;
      try {
        const res = await this.deps.fetch(`${await this.deps.getUrl()}/events`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(batch),
        });
        status = res.status;
        if (res.ok) body = await res.json().catch(() => null);
      } catch (e) {
        this.fail(`network: ${(e as Error).message ?? "error"}`);
        return;
      }
      if (status >= 200 && status < 300) {
        const b = (body ?? {}) as { accepted?: number; rejected?: unknown[] };
        this.stats.accepted += typeof b.accepted === "number" ? b.accepted : batch.length;
        this.stats.rejected += Array.isArray(b.rejected) ? b.rejected.length : 0;
        this.stats.last_error = null;
        this.stats.last_ok_at = new Date(this.deps.now()).toISOString();
        this.fails = 0;
        this.notBefore = 0;
        this.queue.splice(0, batch.length);
        await this.deps.save(this.queue);
        this.deps.onStats?.({ ...this.stats });
      } else if (status >= 400 && status < 500) {
        // The engine will not accept this batch however often we ask: drop it, do not retry.
        this.stats.dropped += batch.length;
        this.stats.last_error = `engine answered ${status}`;
        this.queue.splice(0, batch.length);
        await this.deps.save(this.queue);
        this.deps.onStats?.({ ...this.stats });
      } else {
        this.fail(`engine answered ${status}`);
        return;
      }
    }
  }

  private fail(msg: string): void {
    this.fails += 1;
    this.stats.last_error = msg;
    const wait = Math.min(this.opts.backoffMaxMs, 1000 * 2 ** Math.min(this.fails, 10));
    this.notBefore = this.deps.now() + wait;
    this.deps.onStats?.({ ...this.stats });
    this.schedule(wait);
  }
}
