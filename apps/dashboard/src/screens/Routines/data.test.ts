// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api";
import { exampleHitlist } from "../../fixtures/repeats";
import { exampleKind, hideRow, loadFirm, loadRepeats, resetCounts, restoreExample, unhideRow, watchFirst } from "./data";

const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }));
let calls: { url: string; init?: RequestInit }[] = [];
const stub = (impl: (url: string, init?: RequestInit) => Promise<Response>) => {
  calls = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => { calls.push({ url, init }); return impl(url, init); }));
};

beforeEach(() => restoreExample());
afterEach(() => vi.unstubAllGlobals());

describe("reading the hit list", () => {
  it("asks for the window, reads {meta, data} and says it is live", async () => {
    const live = { meta: { origin: "synthetic", n: 5, n_unit: "episodes", split: null, interval_level: 0.95, generated_at: "x" }, data: exampleHitlist(7) };
    stub(() => json(200, live));
    const r = await loadRepeats(7);
    expect(calls[0].url).toMatch(/\/hitlist\?window=7$/);
    expect(calls[0].init?.method).toBe("GET");
    expect(r.source).toBe("live");
    expect(r.why).toBeNull();
    expect(r.data.rows.length).toBeGreaterThan(0);
    expect(r.meta?.n).toBe(5);
  });

  it("falls back to the example week, badged and explained, when the engine does not answer", async () => {
    stub(() => Promise.reject(new TypeError("Failed to fetch")));
    const r = await loadRepeats(30);
    expect(r.source).toBe("demo");
    expect(r.why?.kind).toBe("offline");
    expect(r.why?.message).toMatch(/not running/);
    expect(r.data.window_days).toBe(30);
    expect(r.meta?.origin).toBe("synthetic");
  });

  it("says the layer is switched off when the route is not there, whatever words the engine uses for a missing route", async () => {
    for (const body of [{ error: { code: "extension_off", message: "The hitlist layer is off." } }, { error: { code: "not_found", message: "There is no such route or item." } }, { detail: "Not Found" }]) {
      stub(() => json(404, body));
      const r = await loadRepeats(7);
      expect(r.source).toBe("demo");
      expect(r.why?.kind).toBe("extension_off");
      expect(r.why?.message).toContain("UNDERSTUDY_X_HITLIST=1");
      expect(r.why?.message).not.toContain("engine said");
    }
  });

  it("retries without the person when the engine does not know the stored one, and errors when it still cannot answer", async () => {
    const live = { meta: { origin: "synthetic", n: 5, n_unit: "episodes", split: null, interval_level: 0.95, generated_at: "x" }, data: exampleHitlist(7) };
    const { setState } = await import("../../store");
    setState({ person: "p_stale" });
    stub((url) => (url.includes("person=") ? json(404, { error: { code: "unknown_person", message: "No events for that person." } }) : json(200, live)));
    const r = await loadRepeats(7);
    expect(r.source).toBe("live");
    expect(calls).toHaveLength(2);
    expect(calls[0].url).toContain("person=p_stale");
    expect(calls[1].url).not.toContain("person=");
    stub(() => json(404, { error: { code: "unknown_person", message: "No events for that person." } }));
    await expect(loadRepeats(7)).rejects.toMatchObject({ status: 404, code: "unknown_person" });
    setState({ person: null });
  });

  it("shows a real refusal as an error, not as example data", async () => {
    stub(() => json(422, { error: { code: "bad_window", message: "window must be 7 or 30 (days)." } }));
    await expect(loadRepeats(7)).rejects.toMatchObject({ status: 422, code: "bad_window" });
  });

  it("previews every empty state only on request", async () => {
    stub(() => Promise.reject(new TypeError("down")));
    for (const k of ["new_user", "too_little_data", "nothing_repeats", "all_handled", "counting_again", "capture_off"] as const) {
      expect((await loadRepeats(7, k)).data.state).toBe(k);
    }
    expect((await loadRepeats(7)).data.state).toBe("ok");
    expect(exampleKind("new_user")).toBe("new_user");
    expect(exampleKind("nonsense")).toBeNull();
    expect(exampleKind(null)).toBeNull();
  });

  it("reads the firm the same way", async () => {
    stub(() => Promise.reject(new TypeError("down")));
    const f = await loadFirm(7);
    expect(f.source).toBe("demo");
    expect(f.data.people).toBe(60);
    expect(f.meta?.n_unit).toBe("people");
    stub(() => json(200, { meta: { origin: "synthetic", n: 60, n_unit: "people", split: null, interval_level: 0.95 }, data: f.data }));
    const live = await loadFirm(30);
    expect(calls[0].url).toMatch(/\/hitlist\/firm\?window=30$/);
    expect(live.source).toBe("live");
  });

  it("the firm read is the admin's and says so in its role header; the worker's own read never does", async () => {
    stub(() => json(200, { meta: { origin: "synthetic", n: 60, n_unit: "people", split: null, interval_level: 0.95 }, data: exampleHitlist(7) }));
    await loadFirm(7);
    expect((calls[0].init?.headers as Record<string, string>)["x-understudy-role"]).toBe("admin");
    stub(() => json(200, { meta: { origin: "synthetic", n: 5, n_unit: "episodes", split: null, interval_level: 0.95, generated_at: "x" }, data: exampleHitlist(7) }));
    await loadRepeats(7);
    expect(calls.map((c) => c.url).some((u) => /hitlist\/firm/.test(u))).toBe(false);
    expect(JSON.stringify(calls[0].init?.headers ?? {})).not.toMatch(/role/i);
  });

  it("no worker screen asks for the firm: only the admin's Automation screen imports the firm read", () => {
    const here = resolve(__dirname, "..");
    const users = ["Routines/Routines.tsx", "Routines/Peek.tsx", "NeedsYou/NeedsYou.tsx", "Home/Home.tsx", "YourData/YourData.tsx"].map((f) => readFileSync(resolve(here, f), "utf8"));
    for (const src of users) expect(src).not.toMatch(/loadFirm|hitlist\/firm/);
  });
});

describe("the workers own writes", () => {
  it("live: hide, unhide and reset are JSON posts as the worker", async () => {
    stub(() => json(200, {}));
    await hideRow("calc-entry-3x", 7, "live");
    await unhideRow("calc-entry-3x", "live");
    await resetCounts("live");
    expect(calls.map((c) => c.url.replace(/^.*\/hitlist/, "/hitlist"))).toEqual(["/hitlist/hide", "/hitlist/unhide", "/hitlist/reset"]);
    for (const c of calls) {
      expect(c.init?.method).toBe("POST");
      expect((c.init?.headers as Record<string, string>)["X-Understudy-Actor"]).toBe("worker");
      expect((c.init?.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
    }
    expect(JSON.parse(calls[0].init?.body as string)).toEqual({ id: "calc-entry-3x", window: 7 });
    expect(JSON.parse(calls[2].init?.body as string)).toEqual({});
  });

  it("live: a refusal comes back as the engine's own words", async () => {
    stub(() => json(403, { error: { code: "write_refused", message: "Only the worker can change the repeats list." } }));
    await expect(hideRow("x", 7, "live")).rejects.toBeInstanceOf(ApiError);
    await expect(resetCounts("live")).rejects.toThrow("Only the worker can change the repeats list.");
  });

  it("live: an engine that is down says nothing changed", async () => {
    stub(() => Promise.reject(new TypeError("down")));
    await expect(hideRow("x", 7, "live")).rejects.toThrow(/nothing changed/);
  });

  it("example data: the changes live in the page, never in the engine", async () => {
    stub(() => Promise.reject(new TypeError("down")));
    await hideRow("calc-entry-3x", 7, "demo");
    await watchFirst("reconcile-totals", "reconcile-totals", "demo");
    expect(calls).toHaveLength(0);
    let d = (await loadRepeats(7)).data;
    expect(d.rows.some((r) => r.id === "calc-entry-3x")).toBe(false);
    expect(d.rows.find((r) => r.id === "reconcile-totals")?.status).toBe("learning");
    await unhideRow("calc-entry-3x", "demo");
    d = (await loadRepeats(7)).data;
    expect(d.rows.some((r) => r.id === "calc-entry-3x")).toBe(true);
    await resetCounts("demo");
    expect((await loadRepeats(7)).data.state).toBe("counting_again");
    restoreExample();
    expect((await loadRepeats(7)).data.state).toBe("ok");
  });
});
