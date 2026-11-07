// Uploads L1 steps for routines the worker opted in: POST {engine}/routines/{id}/recording.
// The body validates against packages/schema/recording.schema.json. If the engine does not have the
// endpoint yet (404/405) the buffer is kept (capped) and retried later.
import type { RecordedStep } from "../shared/types";

export interface RecordingDeps {
  fetch: typeof fetch;
  getUrl: () => Promise<string>;
  getTargets: () => string[];
  identity: () => { person: string; role: string };
  now: () => number;
  uuid: () => string;
}

const MAX_BUFFER = 300;
const RETRY_MS = 5 * 60_000;

export class RecordingUploader {
  private buffer: RecordedStep[] = [];
  private skipped = 0;
  private recordingId: string;
  private retryAt = 0;
  lastStatus = 0;

  constructor(private readonly deps: RecordingDeps) {
    this.recordingId = `rec_${deps.uuid().replace(/-/g, "").slice(0, 12)}`;
  }

  size(): number {
    return this.buffer.length;
  }

  addStep(step: RecordedStep): void {
    if (!this.deps.getTargets().length) return;
    this.buffer.push(step);
    if (this.buffer.length > MAX_BUFFER) this.buffer.splice(0, this.buffer.length - MAX_BUFFER);
  }

  addSkipped(n = 1): void {
    this.skipped += n;
  }

  clear(): void {
    this.buffer = [];
    this.skipped = 0;
  }

  async flush(): Promise<void> {
    const targets = this.deps.getTargets();
    if (!targets.length || (!this.buffer.length && !this.skipped)) return;
    if (this.deps.now() < this.retryAt) return;
    const { person, role } = this.deps.identity();
    const steps = this.buffer.slice();
    const skipped = this.skipped;
    let delivered = true;
    for (const id of targets) {
      try {
        const res = await this.deps.fetch(`${await this.deps.getUrl()}/routines/${id}/recording`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ schema: 1, routine_id: id, recording_id: this.recordingId, role, person, steps, skipped_sensitive: skipped }),
        });
        this.lastStatus = res.status;
        if (res.status === 404 || res.status === 405 || res.status >= 500) {
          delivered = false;
          this.retryAt = this.deps.now() + RETRY_MS;
        }
      } catch {
        delivered = false;
        this.retryAt = this.deps.now() + 15_000;
      }
    }
    if (delivered) {
      this.buffer.splice(0, steps.length);
      this.skipped = Math.max(0, this.skipped - skipped);
    }
  }
}
