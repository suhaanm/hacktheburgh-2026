// @vitest-environment jsdom
// Identical GETs are made once: in flight they share one request, and an answer from one of the heavy routes is reused for a few seconds. A write, a retry and a
// live refresh forget both. Errors and answers from cheap routes (the kill flag, the queue) are never remembered.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GET_MEMORY_MS, api, forgetBackoff, forgetReads } from "./api";
import { LiveController, type LiveEnv } from "./lib/live";
import { resetSources, setState } from "./store";

let calls: string[] = [];
let release: (() => void) | null = null;

function engine(opts: { slow?: boolean; status?: number } = {}) {
  calls = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push(`${init?.method ?? "GET"} ${String(url).replace(/^https?:\/\/[^/]+/, "").replace(/^\/(engine|agent)/, "")}`);
    if (opts.slow) await new Promise<void>((r) => { release = r; });
    const body = { meta: null, data: { n: calls.length } };
    return new Response(JSON.stringify(opts.status && opts.status >= 400 ? { error: { code: "x", message: "nope" } } : body), { status: opts.status ?? 200, headers: { "Content-Type": "application/json" } });
  }));
}
const gets = (p: string) => calls.filter((c) => c === `GET ${p}`).length;

beforeEach(() => { vi.useFakeTimers({ toFake: ["Date"] }); forgetBackoff(); forgetReads(); resetSources(); setState({ extReady: true, ext: {} }); });
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

describe("identical GETs are made once", () => {
  it("three callers asking for the same heavy route at the same moment send one request and each get their own copy", async () => {
    engine({ slow: true });
    const a = api.coach("p1"), b = api.coach("p1"), c = api.coach("p1");
    await vi.waitFor(() => expect(release).not.toBeNull());
    release!();
    const [ra, rb, rc] = await Promise.all([a, b, c]);
    expect(gets("/coach/state?person=p1")).toBe(1);
    expect(ra.data).toEqual(rb.data);
    expect(rb.data).toEqual(rc.data);
    expect(ra.data).not.toBe(rb.data);                                    // copies: one caller changing its data cannot change another's
  });

  it("a second ask within the memory is answered without a request, and after it a new one is made", async () => {
    engine();
    const first = await api.coach("p1");
    const second = await api.coach("p1");
    expect(gets("/coach/state?person=p1")).toBe(1);
    expect(second.data).toEqual(first.data);
    vi.setSystemTime(Date.now() + GET_MEMORY_MS + 50);
    const third = await api.coach("p1");
    expect(gets("/coach/state?person=p1")).toBe(2);
    expect(third.data).not.toEqual(first.data);
  });

  it("another URL is another request", async () => {
    engine();
    await api.coach("p1");
    await api.coach("p2");
    expect(calls.length).toBe(2);
  });

  it("a write makes the next read go to the service", async () => {
    engine();
    await api.coach("p1");
    await api.clearKill();                                                // any write
    await api.coach("p1");
    expect(gets("/coach/state?person=p1")).toBe(2);
  });

  it("a live refresh and a retry forget the memory too", async () => {
    engine();
    await api.coach("p1");
    forgetBackoff();                                                       // what the page's Retry does
    await api.coach("p1");
    expect(gets("/coach/state?person=p1")).toBe(2);
    let wake: () => void = () => undefined;
    const env: LiveEnv = { setTimeout: () => 0, clearTimeout: () => undefined, now: () => 0, openStream: null, onWake: (fn) => { wake = fn; return () => undefined; }, hidden: () => false };
    const ctl = new LiveController(async () => { await api.coach("p1"); }, env);
    ctl.poke();
    await vi.waitFor(() => expect(gets("/coach/state?person=p1")).toBe(3));
    ctl.stop();
    void wake;
  });

  it("an error is not remembered", async () => {
    engine({ status: 500 });
    await api.coach("p1");
    await api.coach("p1");
    expect(gets("/coach/state?person=p1")).toBe(2);
  });

  it("the kill flag and the queue are always asked afresh: Stop and Resume from outside show at the next look", async () => {
    engine();
    await api.killState();
    await api.killState();
    await api.queue("pending");
    await api.queue("pending");
    expect(gets("/kill")).toBe(2);
    expect(gets("/queue?status=pending")).toBe(2);
  });

  it("the same cheap route asked at the same moment is still one request", async () => {
    engine({ slow: true });
    const a = api.killState(), b = api.killState();
    await vi.waitFor(() => expect(release).not.toBeNull());
    release!();
    await Promise.all([a, b]);
    expect(gets("/kill")).toBe(1);
  });
});
