import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import { installCapture } from "../src/content/capture";
import { STALE_TASK_MS } from "../src/background/worker_core";
import type { CaptureRecord } from "../src/shared/types";
import { matcher, recorder, SALT, validateAgainstEventSchema, zonerFor } from "./helpers";
import { createWorker, type WorkerApi } from "../src/background/worker_core";
import { STORAGE_KEYS } from "../src/shared/types";

const dir = join(dirname(fileURLToPath(import.meta.url)), "fixtures", "sandbox");
const win = window as unknown as Window & typeof globalThis;
const HOST = { a: "127.0.0.1:7801", b: "127.0.0.1:7802", c: "127.0.0.1:7803" } as const;
function load(name: string): void {
  const doc = new DOMParser().parseFromString(readFileSync(join(dir, `${name}.html`), "utf8"), "text/html");
  document.documentElement.innerHTML = doc.documentElement.innerHTML;
}

describe.each(["v1", "v2"] as const)("markers on the real sandbox pages (%s)", (layout) => {
  const nav = (site: keyof typeof HOST, name: string) => {
    load(name);
    const z = zonerFor(HOST[site]);
    return z.markersFor(z.forNav(document), document);
  };
  it("the first page of each calculator starts a task", () => {
    expect(nav("a", `a-step1-${layout}`)).toEqual({ start: { idle_s: 120 }, progress: [] });
    expect(nav("b", `b-form-${layout}`)).toEqual({ start: { idle_s: 120 }, progress: [] });
    expect(nav("c", `c-form-${layout}`)).toEqual({ start: { idle_s: 120 }, progress: [] });
  });
  it("later wizard pages carry no marker", () => {
    expect(nav("a", `a-step2-${layout}`)).toBeUndefined();
  });
  it("a result page marks progress result_read, and starts nothing", () => {
    for (const [site, page] of [["a", "a-result"], ["b", "b-result"], ["c", "c-result"]] as const) {
      expect(nav(site, `${page}-${layout}`)).toEqual({ progress: ["result_read"] });
    }
  });
  it("the case note form is quiet; the saved draft marks progress note_field and ends the task", () => {
    expect(nav("a", `a-casenote-${layout}`)).toBeUndefined();
    expect(nav("a", `a-notedraft-${layout}`)).toEqual({ progress: ["note_field"], end: { reason: "note_saved" } });
  });
});

describe("capture emits the markers with the nav record, as enum tokens only", () => {
  let stop: (() => void) | null = null;
  afterEach(() => stop?.());
  it("a result page navigation carries progress result_read and no text", () => {
    load("a-result-v1");
    const r = recorder();
    stop = installCapture({ win, salt: SALT, matcher, zoner: zonerFor(HOST.a), emit: r.emit, requireTrusted: false, isTop: true });
    const navRec = r.records.find((x) => x.type === "nav")!;
    expect(navRec.markers).toEqual({ progress: ["result_read"] });
    expect(JSON.stringify(navRec)).not.toMatch(/£|GOV-|Estimated|Check cliff/);
  });
  it("a page of an unconfigured host never carries markers, however it is built", () => {
    document.documentElement.innerHTML = '<body><div id="note-status">Draft</div><div id="result-amount">x</div><form action="/step/1"></form></body>';
    const r = recorder();
    stop = installCapture({ win, salt: SALT, matcher, zoner: zonerFor("evil.example"), emit: r.emit, requireTrusted: false, isTop: true });
    expect(r.records[0]!.markers).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------------------------- the worker's task lifecycle
function harness() {
  const store: Record<string, unknown> = {};
  const sent: any[] = [];
  let clock = 1_800_000_000_000;
  const api: WorkerApi = {
    storage: {
      get: async (k) => Object.fromEntries((Array.isArray(k) ? k : [k]).filter((x) => x in store).map((x) => [x, store[x]])),
      set: async (items) => void Object.assign(store, JSON.parse(JSON.stringify(items))),
      remove: async (k) => void (Array.isArray(k) ? k : [k]).forEach((x) => delete store[x]),
    },
    sendToTab: async () => null, queryActiveTab: async () => null, getFrameIds: async () => [], keepAlive: () => {},
  };
  let uuidN = 0, taskN = 0;
  const make = () => createWorker(api, {
    fetch: (async (url: string, init?: RequestInit) => { if (init?.body) sent.push(...JSON.parse(init.body as string)); return new Response(JSON.stringify({ accepted: 1, rejected: [] }), { status: 200 }); }) as unknown as typeof fetch,
    now: () => clock, setTimer: (fn, ms) => setTimeout(fn, ms), clearTimer: (h) => clearTimeout(h as ReturnType<typeof setTimeout>),
    sleep: async () => { clock += 10; await new Promise((r) => setTimeout(r, 0)); },
    uuid: () => `00000000-0000-4000-8000-${String(++uuidN).padStart(12, "0")}`, taskId: () => `t_task${++taskN}`,
  });
  return { api, store, sent, make, advance: (ms: number) => void (clock += ms), now: () => clock };
}
const NAV_START: CaptureRecord = { type: "nav", target: { role: "document", domain_hash: "d:77aa00112233" }, meta: { zone: "calc_site", spa: false }, markers: { progress: [], start: { idle_s: 120 } } };
const NAV_RESULT: CaptureRecord = { type: "nav", target: { role: "document", domain_hash: "d:77aa00112233" }, meta: { zone: "calc_result", spa: false }, markers: { progress: ["result_read"] } };
const NAV_SAVED: CaptureRecord = { type: "nav", target: { role: "document", domain_hash: "d:77aa00112233" }, meta: { zone: "case_note", spa: false }, markers: { progress: ["note_field"], end: { reason: "note_saved" } } };
const CLICK: CaptureRecord = { type: "click", target: { role: "button", domain_hash: "d:77aa00112233" }, meta: { zone: "household_form" } };

async function started() {
  const h = harness();
  const w = h.make();
  await w.init();
  await h.api.storage.set({ [STORAGE_KEYS.config]: { ...(h.store[STORAGE_KEYS.config] as object), capturing: true } });
  await w.onConfigChanged(h.store[STORAGE_KEYS.config]);
  return { ...h, w, flush: async () => { await w.batcher.flush(); } };
}

describe("worker task markers", () => {
  it("task_start comes before the first nav, and every event from there to task_end carries one task id", async () => {
    const h = await started();
    await h.w.handleMessage({ kind: "record", record: NAV_START });
    h.advance(3000); await h.w.handleMessage({ kind: "record", record: CLICK });
    h.advance(3000); await h.w.handleMessage({ kind: "record", record: NAV_RESULT });
    h.advance(3000); await h.w.handleMessage({ kind: "record", record: NAV_SAVED });
    h.advance(3000); await h.w.handleMessage({ kind: "record", record: CLICK });          // after task_end: untagged
    await h.flush();
    const types = h.sent.map((e) => e.type);
    expect(types).toEqual(["task_start", "nav", "click", "nav", "progress", "nav", "progress", "task_end", "click"]);
    const tagged = h.sent.slice(0, 8);
    expect(new Set(tagged.map((e) => e.task_id))).toEqual(new Set(["t_task1"]));
    expect(h.sent[8].task_id).toBeUndefined();
    expect(h.sent.filter((e) => e.type === "progress").map((e) => e.meta.kind)).toEqual(["result_read", "note_field"]);
    expect(h.sent.find((e) => e.type === "task_end").meta).toEqual({ reason: "note_saved" });
    expect(h.sent[0].meta).toEqual({ zone: "calc_site" });
    for (const e of h.sent) expect(validateAgainstEventSchema(e), JSON.stringify([e, validateAgainstEventSchema.errors])).toBe(true);
  });

  it("event times strictly increase, so same-millisecond events keep their order", async () => {
    const h = await started();
    await h.w.handleMessage({ kind: "record", record: NAV_START });
    await h.w.handleMessage({ kind: "record", record: NAV_SAVED });
    await h.flush();
    const times = h.sent.map((e) => Date.parse(e.t));
    for (let i = 1; i < times.length; i++) expect(times[i]!).toBeGreaterThan(times[i - 1]!);
  });

  it("a second calculator page while the task is fresh does not start another task", async () => {
    const h = await started();
    await h.w.handleMessage({ kind: "record", record: NAV_START });
    h.advance(30_000); await h.w.handleMessage({ kind: "record", record: NAV_START });
    await h.flush();
    expect(h.sent.filter((e) => e.type === "task_start")).toHaveLength(1);
    expect(h.sent.filter((e) => e.type === "nav")).toHaveLength(2);
  });

  it("a calculator page after 120 s of silence starts a new task even without a task_end", async () => {
    const h = await started();
    await h.w.handleMessage({ kind: "record", record: NAV_START });
    h.advance(130_000); await h.w.handleMessage({ kind: "record", record: NAV_START });
    await h.flush();
    const ids = h.sent.filter((e) => e.type === "task_start").map((e) => e.task_id);
    expect(ids).toEqual(["t_task1", "t_task2"]);
    expect(h.sent.filter((e) => e.type === "nav").map((e) => e.task_id)).toEqual(["t_task1", "t_task2"]);
  });

  it("events after a long absence are not stuffed into the old task", async () => {
    const h = await started();
    await h.w.handleMessage({ kind: "record", record: NAV_START });
    h.advance(STALE_TASK_MS + 1000); await h.w.handleMessage({ kind: "record", record: CLICK });
    await h.flush();
    expect(h.sent.at(-1).task_id).toBeUndefined();
  });

  it("progress of one kind is not repeated within five seconds (a page that reloads in a loop cannot flood)", async () => {
    const h = await started();
    await h.w.handleMessage({ kind: "record", record: NAV_START });
    for (let i = 0; i < 5; i++) { h.advance(500); await h.w.handleMessage({ kind: "record", record: NAV_RESULT }); }
    await h.flush();
    expect(h.sent.filter((e) => e.type === "progress")).toHaveLength(1);
  });

  it("a note saved with no task open emits progress but no task_end", async () => {
    const h = await started();
    await h.w.handleMessage({ kind: "record", record: NAV_SAVED });
    await h.flush();
    expect(h.sent.map((e) => e.type)).toEqual(["nav", "progress"]);
    expect(h.sent.every((e) => e.task_id === undefined)).toBe(true);
  });

  it("survives a service worker restart in the middle of a task", async () => {
    const h = await started();
    await h.w.handleMessage({ kind: "record", record: NAV_START });
    expect(h.store[STORAGE_KEYS.task]).toMatchObject({ id: "t_task1" });
    const w2 = h.make();
    await w2.init();
    expect(w2.task?.id).toBe("t_task1");
    h.advance(5000);
    await w2.handleMessage({ kind: "record", record: CLICK });
    await w2.batcher.flush();
    expect(h.sent.at(-1)).toMatchObject({ type: "click", task_id: "t_task1" });
  });

  it("a restart after the task went stale does not resurrect it", async () => {
    const h = await started();
    await h.w.handleMessage({ kind: "record", record: NAV_START });
    h.advance(STALE_TASK_MS + 1000);
    const w2 = h.make();
    await w2.init();
    expect(w2.task).toBeNull();
  });

  it("turning capture off forgets the open task", async () => {
    const h = await started();
    await h.w.handleMessage({ kind: "record", record: NAV_START });
    await h.api.storage.set({ [STORAGE_KEYS.config]: { ...(h.store[STORAGE_KEYS.config] as object), capturing: false } });
    await h.w.onConfigChanged(h.store[STORAGE_KEYS.config]);
    expect(h.w.task).toBeNull();
    expect(h.store[STORAGE_KEYS.task]).toBeUndefined();
  });

  it("records without markers behave exactly as before (no task)", async () => {
    const h = await started();
    await h.w.handleMessage({ kind: "record", record: CLICK });
    await h.flush();
    expect(h.sent).toHaveLength(1);
    expect(h.sent[0].task_id).toBeUndefined();
  });

  it("task markers never reach the event: no markers field, only enum tokens", async () => {
    const h = await started();
    await h.w.handleMessage({ kind: "record", record: NAV_START });
    await h.flush();
    expect(JSON.stringify(h.sent)).not.toContain("markers");
    expect(JSON.stringify(h.sent)).not.toMatch(/idle_s/);
  });
});
