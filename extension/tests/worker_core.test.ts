import { describe, expect, it, vi } from "vitest";
import { createWorker, type WorkerApi } from "../src/background/worker_core";
import { STORAGE_KEYS } from "../src/shared/types";
import { ajvFor, validateAgainstEventSchema } from "./helpers";

const validateRecording = ajvFor("recording.schema.json");

function harness(opts: { identity?: { status: number; body?: unknown }; routines?: unknown; routinesStatus?: number; engineDown?: boolean; recordingStatus?: number; desktop?: (n: number) => Response | Error } = {}) {
  const store: Record<string, unknown> = {};
  const sent: { url: string; method: string; body: any }[] = [];
  let clock = 1_800_000_000_000;
  let desktopCalls = 0;
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(init.body as string) : null;
    sent.push({ url, method, body });
    if (url.startsWith("http://127.0.0.1:7720")) {
      if (method === "POST") return new Response("{}", { status: 200 });
      // default: the desktop app is not running, so the rect loop backs off and ends instead of spinning in a test
      const r = opts.desktop?.(desktopCalls++) ?? new Error("refused");
      if (r instanceof Error) throw r;
      return r;
    }
    if (opts.engineDown) throw new Error("refused");
    if (url.endsWith("/identity")) return new Response(JSON.stringify(opts.identity?.body ?? {}), { status: opts.identity?.status ?? 404 });
    if (url.endsWith("/routines") && method === "GET") return new Response(JSON.stringify(opts.routines ?? []), { status: opts.routinesStatus ?? 200 });
    if (url.endsWith("/recording")) return new Response("{}", { status: opts.recordingStatus ?? 200 });
    if (url.endsWith("/events")) return new Response(JSON.stringify({ accepted: body.length, rejected: [] }), { status: 200 });
    return new Response("{}", { status: 404 });
  });
  const tabMessages: { tabId: number; msg: any; frameId: number }[] = [];
  const api: WorkerApi = {
    storage: {
      get: async (k) => Object.fromEntries((Array.isArray(k) ? k : [k]).filter((x) => x in store).map((x) => [x, store[x]])),
      set: async (items) => void Object.assign(store, JSON.parse(JSON.stringify(items))),
      remove: async (k) => void (Array.isArray(k) ? k : [k]).forEach((x) => delete store[x]),
    },
    sendToTab: async (tabId, msg, frameId) => {
      const m = msg as { kind: string };
      tabMessages.push({ tabId, msg: m, frameId });
      if (m.kind === "page_info") return { domain_hash: "d:77aa00112233", zone: "results_tabs" };
      if (m.kind === "rect") return frameId === 0 ? { found: true, rect: { x: 1, y: 2, w: 3, h: 4 }, window_offset: { x: 0, y: 87 }, scroll: { x: 0, y: 0 }, dpr: 2, measured_at: clock - 40 } : null;
      return null;
    },
    queryActiveTab: async () => ({ id: 7 }),
    getFrameIds: async () => [0, 4],
    keepAlive: vi.fn(),
  };
  const w = createWorker(api, {
    fetch: fetchMock as unknown as typeof fetch,
    now: () => clock,
    setTimer: (fn, ms) => setTimeout(fn, ms),
    clearTimer: (h) => clearTimeout(h as ReturnType<typeof setTimeout>),
    sleep: async () => { clock += 10; await new Promise((r) => setTimeout(r, 0)); },
    uuid: (() => { let n = 0; return () => `00000000-0000-4000-8000-${String(++n).padStart(12, "0")}`; })(),
  });
  const setConfig = async (patch: object) => {
    const cfg = { ...(store[STORAGE_KEYS.config] as object), ...patch };
    store[STORAGE_KEYS.config] = cfg;
    await w.onConfigChanged(cfg);
  };
  return { w, store, sent, tabMessages, setConfig, advance: (ms: number) => void (clock += ms), api };
}

const rec = { kind: "record" as const, record: { type: "click" as const, target: { role: "button", domain_hash: "d:77aa00112233" }, meta: { zone: "household_form" } } };

describe("worker core", () => {
  it("creates a person id and a per-install salt on first run, and starts with capture off", async () => {
    const h = harness();
    await h.w.init();
    expect(h.w.config.person).toMatch(/^p_[0-9a-f]{8}$/);
    expect(h.w.config.capturing).toBe(false);
    expect(h.store[STORAGE_KEYS.salt]).toMatch(/^[0-9a-f]{32}$/);
    const second = harness();
    await second.w.init();
    expect(second.store[STORAGE_KEYS.salt]).not.toBe(h.store[STORAGE_KEYS.salt]);
  });

  it("records nothing until the worker turns capture on", async () => {
    const h = harness();
    await h.w.init();
    expect(await h.w.handleMessage(rec)).toEqual({ ok: false });
    expect(h.w.batcher.size()).toBe(0);
    await h.setConfig({ capturing: true });
    expect(await h.w.handleMessage(rec)).toEqual({ ok: true });
    expect(h.w.batcher.size()).toBe(1);
  });

  it("wraps records into schema-valid events and posts them to the engine", async () => {
    const h = harness();
    await h.w.init();
    await h.setConfig({ capturing: true });
    await h.w.handleMessage(rec);
    await h.w.batcher.flush();
    const post = h.sent.find((s) => s.url === "http://127.0.0.1:7700/events")!;
    expect(post.body).toHaveLength(1);
    expect(validateAgainstEventSchema(post.body[0]), JSON.stringify(validateAgainstEventSchema.errors)).toBe(true);
    expect(post.body[0]).toMatchObject({ origin: "real", actor: "human", source: "browser", person: h.w.config.person });
  });

  it("deletes unsent events and L1 targets when capture is turned off", async () => {
    const h = harness({ engineDown: true });
    await h.w.init();
    await h.setConfig({ capturing: true });
    await h.w.handleMessage(rec);
    expect(h.w.batcher.size()).toBe(1);
    await h.setConfig({ capturing: false });
    expect(h.w.batcher.size()).toBe(0);
    expect(h.store[STORAGE_KEYS.queue]).toEqual([]);
    expect(h.store[STORAGE_KEYS.l1Targets]).toEqual([]);
  });

  it("emits a tab event from the activated tab's page info, with its zone", async () => {
    const h = harness();
    await h.w.init();
    await h.setConfig({ capturing: true });
    await h.w.onTabActivated(7);
    expect(h.tabMessages[0]).toMatchObject({ tabId: 7, frameId: 0, msg: { kind: "page_info" } });
    expect(h.w.batcher.size()).toBe(1);
    await h.w.batcher.flush();
    const ev = h.sent.find((s) => s.url.endsWith("/events"))!.body[0];
    expect(ev).toMatchObject({ type: "tab", target: { role: "tab", domain_hash: "d:77aa00112233" }, meta: { zone: "results_tabs" } });
  });

  it("does not ask tabs anything while capture is off", async () => {
    const h = harness();
    await h.w.init();
    await h.w.onTabActivated(7);
    expect(h.tabMessages).toHaveLength(0);
  });

  it("opts L1 in only for routines the engine says the worker opted in, and uploads valid recordings", async () => {
    const routines = [{ id: "calc-entry-3x", status: "shadow", consent: { mode: "shadow" } }, { id: "case-note-copy", status: "proposed", consent: { mode: "not_now" } }];
    const h = harness({ routines });
    await h.w.init();
    await h.w.handleMessage({ kind: "l1", step: { op: "click", t_ms: 1, selector: "#x" } });
    expect(h.w.uploader.size()).toBe(0); // capture off, nothing buffered
    await h.setConfig({ capturing: true });
    await h.w.refreshConsent();
    expect(h.w.l1Targets).toEqual(["calc-entry-3x"]);
    expect(h.store[STORAGE_KEYS.l1Targets]).toEqual(["calc-entry-3x"]);
    await h.w.handleMessage({ kind: "l1", step: { op: "goto", t_ms: 0, url: "http://127.0.0.1:7801/step/1" } });
    await h.w.handleMessage({ kind: "l1", step: { op: "fill", t_ms: 5, selector: "#a", param: "adults", input_type: "text" } });
    await h.w.handleMessage({ kind: "l1_skipped" });
    await h.w.uploader.flush();
    const up = h.sent.find((s) => s.url.endsWith("/routines/calc-entry-3x/recording"))!;
    expect(h.sent.some((s) => s.url.endsWith("/routines/case-note-copy/recording"))).toBe(false);
    expect(validateRecording(up.body), JSON.stringify(validateRecording.errors)).toBe(true);
    expect(up.body.skipped_sensitive).toBe(1);
    expect(h.w.uploader.size()).toBe(0);
  });

  it("keeps the recording buffer and retries later when the engine has no recording endpoint yet", async () => {
    const h = harness({ routines: [{ id: "calc-entry-3x", status: "shadow", consent: { mode: "shadow" } }], recordingStatus: 404 });
    await h.w.init();
    await h.setConfig({ capturing: true });
    await h.w.refreshConsent();
    await h.w.handleMessage({ kind: "l1", step: { op: "click", t_ms: 1, selector: "#x" } });
    await h.w.uploader.flush();
    expect(h.w.uploader.size()).toBe(1);
    const before = h.sent.length;
    await h.w.uploader.flush(); // within the retry window: no new request
    expect(h.sent.length).toBe(before);
  });

  it("keeps the previous L1 targets when the engine is unreachable", async () => {
    const h = harness({ routines: [{ id: "calc-entry-3x", status: "shadow", consent: { mode: "shadow" } }] });
    await h.w.init();
    await h.setConfig({ capturing: true });
    await h.w.refreshConsent();
    expect(h.w.l1Targets).toEqual(["calc-entry-3x"]);
    const down = harness({ engineDown: true });
    await down.w.init();
    await down.setConfig({ capturing: true });
    await down.w.refreshConsent();
    expect(down.w.l1Targets).toEqual([]);
  });

  it("runs the rect loop: answers a want from the active tab, then backs off when the desktop app disappears", async () => {
    const want = new Response(JSON.stringify({ request_id: "rq1", label_hash: "h:9f2c1a2b3c4d", frame_id: "top" }), { status: 200 });
    const h = harness({ desktop: (n) => (n === 0 ? want : n === 1 ? new Response(null, { status: 204 }) : new Error("refused")) });
    await h.w.init();
    await h.setConfig({ capturing: false });
    h.store[STORAGE_KEYS.config] = { ...(h.store[STORAGE_KEYS.config] as object), capturing: true };
    await h.setConfig({ capturing: true });
    await h.w.startRect();
    const answer = h.sent.find((s) => s.url === "http://127.0.0.1:7720/ext/rect")!;
    expect(answer.body).toMatchObject({ request_id: "rq1", frame_id: "top", found: true, rect: { x: 1, y: 2, w: 3, h: 4 }, dpr: 2 });
    expect(answer.body.age_ms).toBeGreaterThanOrEqual(40);
    expect(h.tabMessages.find((m) => m.msg.kind === "rect")).toMatchObject({ tabId: 7, frameId: 0 });
    expect((h.api.keepAlive as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(0);
  });

  it("does not poll the desktop app, or resolve rects, while capture is off", async () => {
    const h = harness();
    await h.w.init();
    await h.w.startRect();
    expect(h.sent.filter((s) => s.url.startsWith("http://127.0.0.1:7720"))).toHaveLength(0);
  });

  it("reports status for the popup", async () => {
    const h = harness();
    await h.w.init();
    const s = (await h.w.handleMessage({ kind: "popup_status" })) as { queued: number; config: { capturing: boolean } };
    expect(s.queued).toBe(0);
    expect(s.config.capturing).toBe(false);
  });

  it("ignores unknown messages", async () => {
    const h = harness();
    await h.w.init();
    expect(await h.w.handleMessage({ kind: "exec", code: "alert(1)" } as never)).toEqual({ ok: false });
  });

  describe("identity", () => {
    it("adopts the engine's person and role once onboarding has created them, and retags unsent events", async () => {
      const id: { status: number; body?: unknown } = { status: 404 };
      const h = harness({ engineDown: false, identity: id, routines: [] });
      await h.w.init();
      await h.setConfig({ capturing: true });
      const local = h.w.config.person;
      await h.w.handleMessage(rec);
      await h.w.refreshIdentity();                       // before onboarding: still ours
      expect(h.w.config.person).toBe(local);
      id.status = 200; id.body = { person: "p_ana1", role: "data-analyst" };
      await h.w.refreshIdentity();
      expect(h.w.config).toMatchObject({ person: "p_ana1", role: "data-analyst", identity_adopted: true });
      expect((h.store[STORAGE_KEYS.config] as { person: string }).person).toBe("p_ana1");
      expect((h.store[STORAGE_KEYS.queue] as { person: string; role: string }[])[0]).toMatchObject({ person: "p_ana1", role: "data-analyst" });
      await h.w.handleMessage(rec);
      await h.w.batcher.flush();
      const sent = h.sent.find((s) => s.url.endsWith("/events"))!.body as { person: string }[];
      expect(sent.map((e) => e.person)).toEqual(["p_ana1", "p_ana1"]);
    });

    it("keeps the local identity before onboarding (404) and when the engine is down", async () => {
      const a = harness({ identity: { status: 404 } });
      await a.w.init();
      await a.setConfig({ capturing: true });
      await a.w.refreshIdentity();
      expect(a.w.config.identity_adopted).toBe(false);
      const b = harness({ engineDown: true });
      await b.w.init();
      await b.w.refreshIdentity();
      expect(b.w.config.identity_adopted).toBe(false);
    });

    it("ignores a malformed identity answer", async () => {
      for (const body of [{ person: "someone", role: "data-analyst" }, { person: "p_ok1", role: "Not A Role" }, { role: "programmer" }, "x"]) {
        const h = harness({ identity: { status: 200, body } });
        await h.w.init();
        await h.w.refreshIdentity();
        expect(h.w.config.identity_adopted).toBe(false);
      }
    });

    it("follows a later change of role from onboarding, and never goes back once adopted", async () => {
      const first = { person: "p_ana1", role: "data-analyst" };
      const h = harness({ identity: { status: 200, body: first } });
      await h.w.init();
      await h.w.refreshIdentity();
      expect(h.w.config.role).toBe("data-analyst");
      // the popup can no longer change the role: a config write that tries is normalised back by the next identity poll
      await h.setConfig({ role: "programmer" });
      await h.w.refreshIdentity();
      expect(h.w.config.role).toBe("data-analyst");
    });

    it("the capture-off flow does not lose the adopted identity", async () => {
      const h = harness({ identity: { status: 200, body: { person: "p_ana1", role: "programmer" } } });
      await h.w.init();
      await h.setConfig({ capturing: true });
      await h.w.refreshIdentity();
      await h.setConfig({ capturing: false });
      expect(h.w.config).toMatchObject({ person: "p_ana1", identity_adopted: true });
    });

    it("refreshConsent polls the identity too, so a worker that never restarts still adopts it", async () => {
      const h = harness({ identity: { status: 200, body: { person: "p_ana1", role: "programmer" } }, routines: [] });
      await h.w.init();
      await h.setConfig({ capturing: true });
      await h.w.refreshConsent();
      expect(h.w.config.person).toBe("p_ana1");
    });
  });
});
