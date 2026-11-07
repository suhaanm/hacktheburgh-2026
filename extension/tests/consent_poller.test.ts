import { describe, expect, it, vi } from "vitest";
import { l1Targets, pollConsent } from "../src/background/consent";
import { parseWant, RectPoller } from "../src/background/rect_poller";
import { ajvFor } from "./helpers";

describe("l1Targets", () => {
  const r = (id: string, mode: string | undefined, status = "shadow") => ({ id, status, consent: mode ? { mode } : null });
  it("selects only routines the worker opted in", () => {
    const list = [r("calc-entry-3x", "shadow"), r("case-note-copy", "approval", "approval"), r("weekly-refresh", "unattended", "unattended"),
      r("proposed-one", undefined, "proposed"), r("not-now", "not_now", "proposed"), r("never-one", "never", "never"), r("declined-one", "shadow", "declined")];
    expect(l1Targets(list)).toEqual(["calc-entry-3x", "case-note-copy", "weekly-refresh"]);
  });
  it("accepts the analytic envelope and survives junk", () => {
    expect(l1Targets({ meta: {}, data: [r("calc-entry-3x", "shadow")] })).toEqual(["calc-entry-3x"]);
    expect(l1Targets(null)).toEqual([]);
    expect(l1Targets([null, 3, { id: 7 }, { id: "BAD ID", consent: { mode: "shadow" } }])).toEqual([]);
  });
  it("pollConsent returns null when the engine is unreachable or errors, so the old answer is kept", async () => {
    expect(await pollConsent((async () => { throw new Error("x"); }) as unknown as typeof fetch, "http://127.0.0.1:7700")).toBeNull();
    expect(await pollConsent((async () => new Response("", { status: 500 })) as unknown as typeof fetch, "http://127.0.0.1:7700")).toBeNull();
    const f = vi.fn(async () => new Response(JSON.stringify([r("calc-entry-3x", "shadow")]), { status: 200 }));
    expect(await pollConsent(f as unknown as typeof fetch, "http://127.0.0.1:7700")).toEqual(["calc-entry-3x"]);
    expect((f.mock.calls[0] as unknown[])[0]).toBe("http://127.0.0.1:7700/routines");
  });
});

describe("parseWant", () => {
  const validate = ajvFor("ext_rect.schema.json");
  it("accepts the two valid forms from the shared schema examples", () => {
    for (const w of [{ request_id: "rq1", label_hash: "h:9f2c", frame_id: "top" }, { request_id: "rq2", role: "button", name: "Calculate", frame_id: "f3" }]) {
      expect(validate(w)).toBe(true);
      expect(parseWant(w)).toEqual(w);
    }
  });
  it("accepts the zone form and nothing mixed with it", () => {
    const w = { request_id: "rq3", zone: "cliff_button", frame_id: "top" };
    expect(validate(w)).toBe(true);
    expect(parseWant(w)).toEqual(w);
    for (const bad of [{ ...w, label_hash: "h:9f2c" }, { ...w, role: "button", name: "x" }, { ...w, zone: "Cliff Button" }, { ...w, zone: "x" }, { ...w, zone: "https://evil.example" }]) {
      expect(parseWant(bad), JSON.stringify(bad)).toBeNull();
    }
    expect(validate({ ...w, label_hash: "h:9f2c" })).toBe(false);
  });
  it("rejects malformed, mixed and oversized requests", () => {
    for (const w of [null, "x", {}, { request_id: "rq", frame_id: "top" }, { request_id: "rq", frame_id: "bottom", label_hash: "h:9f2c" },
      { request_id: "rq", frame_id: "top", label_hash: "h:9f2c", role: "button", name: "x" }, { request_id: "rq", frame_id: "top", role: "button", name: "x".repeat(81) },
      { request_id: "rq", frame_id: "top", label_hash: "not-a-hash" }, { request_id: "a b", frame_id: "top", label_hash: "h:9f2c" }]) expect(parseWant(w)).toBeNull();
  });
});

describe("RectPoller", () => {
  const found = { found: true, rect: { x: 1, y: 2, w: 3, h: 4 }, window_offset: { x: 0, y: 87 }, scroll: { x: 0, y: 0 }, dpr: 2, measured_at: 900, frame_id: "top" };
  function make(responses: Response[] | Error, resolve = vi.fn(async () => found as never)) {
    const posts: unknown[] = [];
    const queue = Array.isArray(responses) ? [...responses] : null;
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST") { posts.push({ url, body: JSON.parse(init.body as string) }); return new Response("{}", { status: 200 }); }
      if (!queue) throw responses;
      return queue.shift()!;
    });
    return { p: new RectPoller({ fetch: fetchMock as unknown as typeof fetch, getDesktopUrl: async () => "http://127.0.0.1:7720", resolve, now: () => 1000 }), posts, resolve };
  }
  it("idles on 204", async () => {
    const { p, posts } = make([new Response(null, { status: 204 })]);
    expect(await p.tick()).toEqual({ delay: 400, reachable: true, answered: false });
    expect(posts).toHaveLength(0);
  });
  it("carries viewport, outer and screen from the resolved rect into the answer", async () => {
    const validate = ajvFor("ext_rect.schema.json");
    const full = { ...found, viewport: { w: 1280, h: 713 }, outer: { w: 1280, h: 800 }, screen: { x: 0, y: 38 } };
    const { p, posts } = make([new Response(JSON.stringify({ request_id: "rq5", zone: "cliff_button", frame_id: "top" }), { status: 200 })], vi.fn(async () => full as never));
    await p.tick();
    const body = (posts[0] as { body: Record<string, unknown> }).body;
    expect(body).toMatchObject({ viewport: { w: 1280, h: 713 }, outer: { w: 1280, h: 800 }, screen: { x: 0, y: 38 } });
    expect(validate(body), JSON.stringify(validate.errors)).toBe(true);
  });
  it("answers a want with a schema-valid body and an age", async () => {
    const validate = ajvFor("ext_rect.schema.json");
    const { p, posts } = make([new Response(JSON.stringify({ request_id: "rq1", label_hash: "h:9f2c", frame_id: "top" }), { status: 200 })]);
    expect(await p.tick()).toEqual({ delay: 0, reachable: true, answered: true });
    const sent = posts[0] as { url: string; body: Record<string, unknown> };
    expect(sent.url).toBe("http://127.0.0.1:7720/ext/rect");
    expect(sent.body.age_ms).toBe(100);
    expect(validate(sent.body), JSON.stringify(validate.errors)).toBe(true);
  });
  it("answers found:false when the page has no such element", async () => {
    const { p, posts } = make([new Response(JSON.stringify({ request_id: "rq1", label_hash: "h:9f2c", frame_id: "top" }), { status: 200 })], vi.fn(async () => ({ found: false, measured_at: 1 }) as never));
    await p.tick();
    expect((posts[0] as { body: unknown }).body).toEqual({ request_id: "rq1", frame_id: "top", found: false, age_ms: 0 });
  });
  it("ignores a malformed want without calling the resolver", async () => {
    const { p, resolve } = make([new Response(JSON.stringify({ request_id: "rq1", frame_id: "top", label_hash: "h:9f2c", role: "x", name: "y" }), { status: 200 })]);
    await p.tick();
    expect(resolve).not.toHaveBeenCalled();
  });
  it("backs off when the desktop app is not running", async () => {
    const { p } = make(new Error("refused"));
    const a = await p.tick(); const b = await p.tick(); const c = await p.tick();
    expect(a.reachable).toBe(false);
    expect([a.delay, b.delay, c.delay]).toEqual([4000, 8000, 16000]);
  });
});
