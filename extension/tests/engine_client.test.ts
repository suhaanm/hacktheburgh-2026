import { describe, expect, it, vi } from "vitest";
import { Batcher } from "../src/background/engine_client";
import type { L0Event } from "../src/shared/types";

const ev = (i: number): L0Event => ({ schema: 1, id: `ev_${String(i).padStart(8, "0")}`, t: "2026-11-07T14:00:00.000Z", origin: "real", actor: "human", person: "p_9f3a", role: "benefits-processor", source: "browser", type: "click" });

function setup(responder: (url: string, init: RequestInit) => Promise<Response> | Response, opts = {}, getFlushMs?: () => number) {
  let clock = 0;
  const timers: { fn: () => void; at: number; id: number }[] = [];
  let nextId = 1;
  const stored: { q: L0Event[] } = { q: [] };
  const calls: { url: string; body: L0Event[] }[] = [];
  const fetchMock = vi.fn(async (url: string, init: RequestInit) => {
    calls.push({ url, body: JSON.parse(init.body as string) });
    return responder(url, init);
  });
  const b = new Batcher({
    fetch: fetchMock as unknown as typeof fetch,
    getUrl: async () => "http://127.0.0.1:7700",
    load: async () => stored.q.slice(),
    save: async (q) => void (stored.q = q.slice()),
    setTimer: (fn, ms) => { const id = nextId++; timers.push({ fn, at: clock + ms, id }); return id; },
    clearTimer: (h) => { const i = timers.findIndex((t) => t.id === h); if (i >= 0) timers.splice(i, 1); },
    now: () => clock,
    getFlushMs,
  }, opts);
  const advance = async (ms: number) => {
    clock += ms;
    for (const t of timers.filter((t) => t.at <= clock).sort((a, c) => a.at - c.at)) { timers.splice(timers.indexOf(t), 1); t.fn(); }
    await new Promise((r) => setTimeout(r, 0));
  };
  return { b, calls, stored, advance, timers };
}
const ok = (accepted: number) => new Response(JSON.stringify({ accepted, rejected: [] }), { status: 200 });

describe("Batcher", () => {
  it("flushes a full batch at once to POST /events", async () => {
    const s = setup(() => ok(25));
    for (let i = 0; i < 25; i++) await s.b.add(ev(i));
    await s.b.flush();
    expect(s.calls).toHaveLength(1);
    expect(s.calls[0]!.url).toBe("http://127.0.0.1:7700/events");
    expect(s.calls[0]!.body).toHaveLength(25);
    expect(s.b.size()).toBe(0);
    expect(s.b.stats.accepted).toBe(25);
  });

  it("flushes a partial batch after the timer", async () => {
    const s = setup(() => ok(2));
    await s.b.add(ev(1)); await s.b.add(ev(2));
    expect(s.calls).toHaveLength(0);
    await s.advance(2100);
    expect(s.calls).toHaveLength(1);
    expect(s.calls[0]!.body).toHaveLength(2);
  });

  it("flush_ms: the default is 2 s; a smaller value sends the first batch that much sooner, and a change applies to the next batch", async () => {
    const dflt = setup(() => ok(1));
    await dflt.b.add(ev(1));
    await dflt.advance(1500);
    expect(dflt.calls).toHaveLength(0);
    await dflt.advance(600);
    expect(dflt.calls).toHaveLength(1);

    let ms = 1000;
    const fast = setup(() => ok(1), {}, () => ms);
    await fast.b.add(ev(1));
    await fast.advance(900);
    expect(fast.calls).toHaveLength(0);
    await fast.advance(200);
    expect(fast.calls).toHaveLength(1);
    ms = 300;                                       // changed in storage: the next timer uses it
    await fast.b.add(ev(2));
    await fast.advance(350);
    expect(fast.calls).toHaveLength(2);
    // events inside the window ride along in one request
    ms = 1000;
    await fast.b.add(ev(3)); await fast.advance(200); await fast.b.add(ev(4)); await fast.advance(900);
    expect(fast.calls[2]!.body.map((e) => e.id)).toEqual(["ev_00000003", "ev_00000004"]);
  });

  it("keeps events and backs off when the engine is down, then delivers", async () => {
    let up = false;
    const s = setup(() => (up ? ok(1) : Promise.reject(new Error("refused"))));
    await s.b.add(ev(1));
    await s.advance(2100);
    expect(s.b.size()).toBe(1);
    expect(s.b.stats.last_error).toContain("network");
    expect(s.stored.q).toHaveLength(1); // persisted across a worker restart
    up = true;
    await s.advance(1000); await s.advance(1500);
    expect(s.b.size()).toBe(0);
    expect(s.b.stats.last_error).toBeNull();
  });

  it("retries on 5xx but drops a batch the engine rejects with 4xx", async () => {
    const s5 = setup(() => new Response("{}", { status: 503 }));
    await s5.b.add(ev(1)); await s5.advance(2100);
    expect(s5.b.size()).toBe(1);
    const s4 = setup(() => new Response("{}", { status: 422 }));
    await s4.b.add(ev(1)); await s4.advance(2100);
    expect(s4.b.size()).toBe(0);
    expect(s4.b.stats.dropped).toBe(1);
  });

  it("counts rejected rows from the engine's answer", async () => {
    const s = setup(() => new Response(JSON.stringify({ accepted: 1, rejected: [{ index: 1, reason: "bad" }] }), { status: 200 }));
    await s.b.add(ev(1)); await s.b.add(ev(2));
    await s.b.flush();
    expect(s.b.stats).toMatchObject({ accepted: 1, rejected: 1 });
  });

  it("caps the queue and counts what it had to drop", async () => {
    const s = setup(() => Promise.reject(new Error("down")), { maxQueue: 5, maxBatch: 100 });
    for (let i = 0; i < 8; i++) await s.b.add(ev(i));
    expect(s.b.size()).toBe(5);
    expect(s.b.stats.dropped).toBe(3);
  });

  it("clear forgets unsent events and stops the timer (consent revoked)", async () => {
    const s = setup(() => ok(1));
    await s.b.add(ev(1));
    await s.b.clear();
    expect(s.b.size()).toBe(0);
    expect(s.stored.q).toHaveLength(0);
    await s.advance(5000);
    expect(s.calls).toHaveLength(0);
  });

  it("restores a persisted queue after a restart", async () => {
    const s = setup(() => ok(1));
    s.stored.q = [ev(1), ev(2)];
    await s.b.add(ev(3));
    await s.b.flush();
    expect(s.calls[0]!.body.map((e) => e.id)).toEqual(["ev_00000001", "ev_00000002", "ev_00000003"]);
  });
});
