// The live-update controller with a fake clock and a fake event stream: fast polling while a run is active, slow otherwise, a refresh on focus, streams that
// ask for a refresh and close at their end, a broken stream that polling covers, and no two refreshes at once.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FAST_MS, LiveController, SLOW_MS, pokeLive, type LiveEnv, type LiveStream } from "./live";

class FakeStream implements LiveStream {
  onevent: ((name: string) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  constructor(public url: string) {}
  close() { this.closed = true; }
  emit(name: string) { this.onevent?.(name); }
  fail() { this.onerror?.(); }
}

function setup(over: Partial<LiveEnv> = {}) {
  const streams: FakeStream[] = [];
  let wake: (() => void) | null = null;
  let hidden = false;
  const env: LiveEnv = {
    setTimeout: (fn, ms) => setTimeout(fn, ms),
    clearTimeout: (id) => clearTimeout(id as ReturnType<typeof setTimeout>),
    now: () => Date.now(),
    openStream: (url) => { const s = new FakeStream(url); streams.push(s); return s; },
    onWake: (fn) => { wake = fn; return () => { wake = null; }; },
    hidden: () => hidden,
    ...over,
  };
  const reload = vi.fn(async () => undefined);
  const ctl = new LiveController(reload, env);
  return { ctl, reload, streams, focus: () => wake?.(), setHidden: (h: boolean) => { hidden = h; }, hasWake: () => wake !== null };
}

describe("live updates", () => {
  beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(new Date("2026-11-08T10:00:00Z")); });
  afterEach(() => { vi.useRealTimers(); });

  it("polls every 2 s while a run is active", async () => {
    const { ctl, reload } = setup();
    ctl.update({ active: true, streams: [] });
    await vi.advanceTimersByTimeAsync(FAST_MS - 1);
    expect(reload).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(reload).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(FAST_MS * 3);
    expect(reload).toHaveBeenCalledTimes(4);
    ctl.stop();
  });

  it("polls every 15 s when nothing is active, and speeds up the moment something is", async () => {
    const { ctl, reload } = setup();
    ctl.update({ active: false, streams: [] });
    await vi.advanceTimersByTimeAsync(SLOW_MS - 1);
    expect(reload).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(reload).toHaveBeenCalledTimes(1);
    ctl.update({ active: true, streams: [] });                 // a run started: the next poll is 2 s away, not 15
    await vi.advanceTimersByTimeAsync(FAST_MS);
    expect(reload).toHaveBeenCalledTimes(2);
    ctl.update({ active: false, streams: [] });
    await vi.advanceTimersByTimeAsync(FAST_MS);
    expect(reload).toHaveBeenCalledTimes(2);                   // back to slow
    ctl.stop();
  });

  it("re-rendering with the same state does not reset the clock", async () => {
    const { ctl, reload } = setup();
    ctl.update({ active: true, streams: [] });
    await vi.advanceTimersByTimeAsync(1500);
    ctl.update({ active: true, streams: [] });
    ctl.update({ active: true, streams: [] });
    await vi.advanceTimersByTimeAsync(500);
    expect(reload).toHaveBeenCalledTimes(1);
    ctl.stop();
  });

  it("never runs two refreshes at once: a slow reload holds the next poll back", async () => {
    let release: () => void = () => undefined;
    let calls = 0;
    const slow = vi.fn(() => { calls++; return new Promise<void>((r) => { release = r; }); });
    const e: LiveEnv = { setTimeout: (fn, ms) => setTimeout(fn, ms), clearTimeout: (id) => clearTimeout(id as ReturnType<typeof setTimeout>), now: () => Date.now(), openStream: null, onWake: () => () => undefined, hidden: () => false };
    const ctl = new LiveController(slow, e);
    ctl.update({ active: true, streams: [] });
    await vi.advanceTimersByTimeAsync(FAST_MS * 5);
    expect(calls).toBe(1);                                      // the first is still loading: no second one starts
    release();
    await vi.advanceTimersByTimeAsync(FAST_MS);
    expect(calls).toBe(2);
    ctl.stop();
  });

  it("a failed refresh does not stop the polling", async () => {
    const failing = vi.fn(async () => { throw new Error("engine down"); });
    const e: LiveEnv = { setTimeout: (fn, ms) => setTimeout(fn, ms), clearTimeout: (id) => clearTimeout(id as ReturnType<typeof setTimeout>), now: () => Date.now(), openStream: null, onWake: () => () => undefined, hidden: () => false };
    const ctl = new LiveController(failing, e);
    ctl.update({ active: true, streams: [] });
    await vi.advanceTimersByTimeAsync(FAST_MS * 3);
    expect(failing).toHaveBeenCalledTimes(3);
    ctl.stop();
  });

  it("refreshes at once when the window gains focus, and not twice within half a second", async () => {
    const { ctl, reload, focus } = setup();
    ctl.update({ active: false, streams: [] });
    focus();
    await vi.advanceTimersByTimeAsync(0);
    expect(reload).toHaveBeenCalledTimes(1);
    focus(); focus();
    await vi.advanceTimersByTimeAsync(0);
    expect(reload).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(600);
    focus();
    await vi.advanceTimersByTimeAsync(0);
    expect(reload).toHaveBeenCalledTimes(2);
    ctl.stop();
  });

  it("does not poll while the tab is hidden, and refreshes when it comes back", async () => {
    const { ctl, reload, setHidden, focus } = setup();
    ctl.update({ active: true, streams: [] });
    setHidden(true);
    await vi.advanceTimersByTimeAsync(FAST_MS * 5);
    expect(reload).not.toHaveBeenCalled();
    setHidden(false);
    focus();
    await vi.advanceTimersByTimeAsync(0);
    expect(reload).toHaveBeenCalledTimes(1);
    ctl.stop();
  });

  it("opens a stream per known run, asks for a refresh on an event, and again on the end, then closes it", async () => {
    const { ctl, reload, streams } = setup();
    ctl.update({ active: true, streams: ["r_1"] });
    expect(streams).toHaveLength(1);
    expect(streams[0].url).toMatch(/\/run\/r_1\/stream$/);
    streams[0].emit("step");
    await vi.advanceTimersByTimeAsync(0);
    expect(reload).toHaveBeenCalledTimes(1);
    streams[0].emit("end");
    await vi.advanceTimersByTimeAsync(0);
    expect(reload).toHaveBeenCalledTimes(2);
    expect(streams[0].closed).toBe(true);
    ctl.stop();
  });

  it("answers a burst of events with one refresh now and one queued, not one each", async () => {
    const { ctl, reload, streams } = setup();
    ctl.update({ active: false, streams: ["r_1"] });
    for (let i = 0; i < 20; i++) streams[0].emit("step");
    await vi.advanceTimersByTimeAsync(0);
    expect(reload).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(500);
    expect(reload).toHaveBeenCalledTimes(2);
    ctl.stop();
  });

  it("a stream that breaks is dropped and polling carries on", async () => {
    const { ctl, reload, streams } = setup();
    ctl.update({ active: true, streams: ["r_1"] });
    streams[0].fail();
    expect(streams[0].closed).toBe(true);
    ctl.update({ active: true, streams: ["r_1"] });              // the same id is not opened again
    expect(streams).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(FAST_MS);
    expect(reload).toHaveBeenCalledTimes(1);
    ctl.stop();
  });

  it("closes the stream of a run that is no longer listed, and opens at most four", async () => {
    const { ctl, streams } = setup();
    ctl.update({ active: true, streams: ["a", "b", "c", "d", "e", "f"] });
    expect(streams).toHaveLength(4);
    ctl.update({ active: true, streams: ["a"] });
    expect(streams.filter((s) => s.closed)).toHaveLength(3);
    ctl.stop();
  });

  it("works with no stream support at all (polling only)", async () => {
    const { ctl, reload } = setup({ openStream: null });
    ctl.update({ active: true, streams: ["r_1"] });
    await vi.advanceTimersByTimeAsync(FAST_MS);
    expect(reload).toHaveBeenCalledTimes(1);
    ctl.stop();
  });

  it("stop ends the timers, the streams and the focus listener", async () => {
    const { ctl, reload, streams, hasWake } = setup();
    ctl.update({ active: true, streams: ["r_1"] });
    ctl.stop();
    expect(streams[0].closed).toBe(true);
    expect(hasWake()).toBe(false);
    await vi.advanceTimersByTimeAsync(FAST_MS * 5);
    expect(reload).not.toHaveBeenCalled();
    ctl.update({ active: true, streams: [] });                  // an update after stop does nothing
    await vi.advanceTimersByTimeAsync(FAST_MS * 5);
    expect(reload).not.toHaveBeenCalled();
  });

  it("opens a stream at an address given whole (the tasks service), and every event of it asks for a refresh", async () => {
    const { ctl, reload, streams } = setup();
    ctl.update({ active: false, streams: [], urls: ["/agent/tasks/events"] });
    expect(streams).toHaveLength(1);
    expect(streams[0].url).toBe("/agent/tasks/events");
    streams[0].emit("snapshot");
    await vi.advanceTimersByTimeAsync(0);
    expect(reload).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(500);
    streams[0].emit("task_finished");
    await vi.advanceTimersByTimeAsync(0);
    expect(reload).toHaveBeenCalledTimes(2);
    ctl.stop();
  });

  it("tries a broken stream again after half a minute, and not before", async () => {
    const { ctl, streams } = setup();
    ctl.update({ active: false, streams: [], urls: ["/agent/tasks/events"] });
    streams[0].fail();
    await vi.advanceTimersByTimeAsync(SLOW_MS);
    expect(streams).toHaveLength(1);                           // 15 s: too soon
    await vi.advanceTimersByTimeAsync(SLOW_MS + 1000);
    expect(streams).toHaveLength(2);                           // 31 s: the service may be back
    ctl.stop();
  });

  it("a run's stream that has ended is not opened again straight away", async () => {
    const { ctl, streams } = setup();
    ctl.update({ active: true, streams: ["r_1"] });
    streams[0].emit("end");
    ctl.update({ active: false, streams: ["r_1"] });
    expect(streams).toHaveLength(1);
    ctl.stop();
  });

  it("a poke refreshes every live screen now and keeps the fast pace for 30 seconds, then goes back to the slow one", async () => {
    const a = setup(), b = setup();
    a.ctl.update({ active: false, streams: [] });
    b.ctl.update({ active: false, streams: [] });
    pokeLive();
    await vi.advanceTimersByTimeAsync(0);
    expect(a.reload).toHaveBeenCalledTimes(1);
    expect(b.reload).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(FAST_MS * 5);
    expect(a.reload).toHaveBeenCalledTimes(6);                  // every 2 s while boosted
    await vi.advanceTimersByTimeAsync(30_000);                  // past the boost
    const before = a.reload.mock.calls.length;
    await vi.advanceTimersByTimeAsync(FAST_MS * 3);
    expect(a.reload.mock.calls.length - before).toBeLessThanOrEqual(1);
    a.ctl.stop(); b.ctl.stop();
  });

  it("a stopped screen is not poked", async () => {
    const a = setup();
    a.ctl.update({ active: false, streams: [] });
    a.ctl.stop();
    pokeLive();
    await vi.advanceTimersByTimeAsync(0);
    expect(a.reload).not.toHaveBeenCalled();
  });
});
