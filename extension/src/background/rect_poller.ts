// Element-rect protocol, extension side (packages/schema/ext_rect.schema.json). Polls the desktop app's
// GET /ext/want; 204 means nothing wanted. Answers with POST /ext/rect. Pure logic: the worker supplies
// fetch, the resolver (which asks a content script) and the clock.
import type { RectResult, RectWant } from "../content/rect";

export interface RectPollerDeps {
  fetch: typeof fetch;
  getDesktopUrl: () => Promise<string>;
  resolve: (want: RectWant) => Promise<(RectResult & { frame_id: string }) | null>;
  now: () => number;
}

const REQUEST_ID_RE = /^[A-Za-z0-9_.:-]{1,64}$/;
const FRAME_RE = /^(top|f[0-9]{1,4})$/;
const LABEL_HASH_RE = /^h:[0-9a-f]{4,16}$/;
const ROLE_RE = /^[a-z][a-z0-9_-]{0,31}$/;

export function parseWant(raw: unknown): RectWant | null {
  if (typeof raw !== "object" || raw === null) return null;
  const r = raw as Record<string, unknown>;
  if (typeof r.request_id !== "string" || !REQUEST_ID_RE.test(r.request_id)) return null;
  if (typeof r.frame_id !== "string" || !FRAME_RE.test(r.frame_id)) return null;
  const want: RectWant = { request_id: r.request_id, frame_id: r.frame_id };
  if (typeof r.label_hash === "string" && LABEL_HASH_RE.test(r.label_hash) && r.role === undefined && r.name === undefined) {
    want.label_hash = r.label_hash;
  } else if (typeof r.role === "string" && ROLE_RE.test(r.role) && typeof r.name === "string" && r.name.length > 0 && r.name.length <= 80 && r.label_hash === undefined) {
    want.role = r.role;
    want.name = r.name;
  } else return null;
  return want;
}

export type PollOutcome = { delay: number; reachable: boolean; answered: boolean };

export class RectPoller {
  private failures = 0;
  constructor(private readonly deps: RectPollerDeps) {}

  async tick(): Promise<PollOutcome> {
    const base = await this.deps.getDesktopUrl();
    let res: Response;
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), 1500);
    try {
      res = await this.deps.fetch(`${base}/ext/want`, { method: "GET", headers: { accept: "application/json" }, signal: ctl.signal });
    } catch {
      this.failures += 1;
      return { delay: Math.min(30_000, 2000 * 2 ** Math.min(this.failures, 4)), reachable: false, answered: false };
    } finally {
      clearTimeout(timer);
    }
    this.failures = 0;
    if (res.status === 204) return { delay: 400, reachable: true, answered: false };
    if (!res.ok) return { delay: 2000, reachable: true, answered: false };
    const want = parseWant(await res.json().catch(() => null));
    if (!want) return { delay: 400, reachable: true, answered: false };
    const found = await this.deps.resolve(want).catch(() => null);
    const body = found && found.found
      ? { request_id: want.request_id, frame_id: found.frame_id, found: true, rect: found.rect, window_offset: found.window_offset, scroll: found.scroll, dpr: found.dpr, age_ms: Math.max(0, this.deps.now() - found.measured_at) }
      : { request_id: want.request_id, frame_id: want.frame_id, found: false, age_ms: 0 };
    try {
      await this.deps.fetch(`${base}/ext/rect`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
    } catch {
      // the desktop app went away between want and answer; the next tick finds out
    }
    return { delay: 0, reachable: true, answered: true };
  }
}
