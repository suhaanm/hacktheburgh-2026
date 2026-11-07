// The service worker's logic, separated from chrome.* so it can be tested with a fake API.
import type { RectResult, RectWant } from "../content/rect";
import { defaultUuid, makeEvent } from "../shared/events";
import { ensureConfig, ensureSalt, normaliseConfig, type StorageArea } from "../shared/config";
import { DEFAULT_CONFIG, STORAGE_KEYS, type CaptureRecord, type InstallConfig, type RecordedStep } from "../shared/types";
import { Batcher, type Stats } from "./engine_client";
import { pollConsent } from "./consent";
import { RecordingUploader } from "./recording";
import { RectPoller } from "./rect_poller";

export interface WorkerApi {
  storage: StorageArea;
  /** Sends to one frame of a tab; resolves with the content script's answer or null. */
  sendToTab(tabId: number, msg: unknown, frameId: number): Promise<unknown>;
  queryActiveTab(): Promise<{ id: number } | null>;
  getFrameIds(tabId: number): Promise<number[]>;
  /** An extension API call that resets the service worker idle timer. */
  keepAlive(): void;
}

export interface WorkerDeps {
  fetch: typeof fetch;
  now: () => number;
  uuid?: () => string;
  setTimer: (fn: () => void, ms: number) => unknown;
  clearTimer: (h: unknown) => void;
  sleep: (ms: number) => Promise<void>;
}

export type ContentMessage =
  | { kind: "record"; record: CaptureRecord }
  | { kind: "l1"; step: RecordedStep }
  | { kind: "l1_skipped" }
  | { kind: "get_salt" }
  | { kind: "popup_status" };

export function createWorker(api: WorkerApi, deps: WorkerDeps) {
  const uuid = deps.uuid ?? defaultUuid;
  let cfg: InstallConfig = { ...DEFAULT_CONFIG };
  let salt = "";
  let l1TargetIds: string[] = [];
  let l1Timer: unknown = null;
  let rectRunning = false;
  let rectReachable = false;

  const batcher = new Batcher({
    fetch: deps.fetch,
    getUrl: async () => cfg.engine_url,
    load: async () => ((await api.storage.get(STORAGE_KEYS.queue))[STORAGE_KEYS.queue] as never[] | undefined) ?? [],
    save: (q) => api.storage.set({ [STORAGE_KEYS.queue]: q }),
    setTimer: deps.setTimer,
    clearTimer: deps.clearTimer,
    now: deps.now,
    onStats: (s: Stats) => void api.storage.set({ [STORAGE_KEYS.stats]: s }),
  });

  const uploader = new RecordingUploader({
    fetch: deps.fetch,
    getUrl: async () => cfg.engine_url,
    getTargets: () => (cfg.capturing ? l1TargetIds : []),
    identity: () => ({ person: cfg.person, role: cfg.role }),
    now: deps.now,
    uuid,
  });

  const poller = new RectPoller({
    fetch: deps.fetch,
    getDesktopUrl: async () => cfg.desktop_url,
    now: deps.now,
    resolve: async (want: RectWant) => {
      if (!cfg.capturing) return null;
      const tab = await api.queryActiveTab();
      if (!tab) return null;
      const first = want.frame_id === "top" ? 0 : Number(want.frame_id.slice(1));
      const order = [first, ...(await api.getFrameIds(tab.id).catch(() => [] as number[]))].filter((f, i, a) => a.indexOf(f) === i);
      for (const fid of order) {
        const r = (await api.sendToTab(tab.id, { kind: "rect", want }, fid).catch(() => null)) as RectResult | null;
        if (r && r.found) return { ...r, frame_id: fid === 0 ? "top" : `f${fid}` };
      }
      return null;
    },
  });

  async function init(): Promise<void> {
    cfg = await ensureConfig(api.storage);
    salt = await ensureSalt(api.storage);
    const got = await api.storage.get(STORAGE_KEYS.l1Targets);
    const ids = got[STORAGE_KEYS.l1Targets];
    l1TargetIds = Array.isArray(ids) ? ids.filter((x): x is string => typeof x === "string") : [];
    if (cfg.capturing) void startRect();
  }

  /** Storage changed (popup toggled capture, or the config was edited). */
  async function onConfigChanged(raw: unknown): Promise<void> {
    const was = cfg.capturing;
    cfg = normaliseConfig(raw);
    if (!cfg.person) cfg = await ensureConfig(api.storage);
    if (was && !cfg.capturing) {
      await batcher.clear(); // consent revoked: forget what has not been sent
      uploader.clear();
      await api.storage.set({ [STORAGE_KEYS.l1Targets]: [] });
      l1TargetIds = [];
    }
    if (!was && cfg.capturing) {
      void refreshConsent();
      void startRect();
    }
  }

  function scheduleL1Flush(): void {
    if (l1Timer !== null) return;
    l1Timer = deps.setTimer(() => {
      l1Timer = null;
      void uploader.flush();
    }, 3000);
  }

  async function handleMessage(msg: ContentMessage): Promise<unknown> {
    switch (msg?.kind) {
      case "record": {
        if (!cfg.capturing || !cfg.person) return { ok: false };
        const ev = makeEvent(msg.record, cfg, { now: deps.now, uuid });
        if (!ev) return { ok: false };
        await batcher.add(ev);
        return { ok: true };
      }
      case "l1":
        if (cfg.capturing && l1TargetIds.length) {
          uploader.addStep(msg.step);
          scheduleL1Flush();
        }
        return { ok: true };
      case "l1_skipped":
        uploader.addSkipped();
        return { ok: true };
      case "get_salt":
        return { salt: salt || (salt = await ensureSalt(api.storage)) };
      case "popup_status":
        return { config: cfg, stats: batcher.stats, queued: batcher.size(), l1_targets: l1TargetIds, l1_buffer: uploader.size(), desktop_reachable: rectReachable };
      default:
        return { ok: false };
    }
  }

  async function onTabActivated(tabId: number): Promise<void> {
    if (!cfg.capturing) return;
    const info = (await api.sendToTab(tabId, { kind: "page_info" }, 0).catch(() => null)) as { domain_hash?: string; zone?: string } | null;
    if (!info?.domain_hash) return;
    const record: CaptureRecord = { type: "tab", target: { role: "tab", domain_hash: info.domain_hash } };
    if (info.zone) record.meta = { zone: info.zone };
    await handleMessage({ kind: "record", record });
  }

  async function refreshConsent(): Promise<void> {
    if (!cfg.capturing) return;
    const ids = await pollConsent(deps.fetch, cfg.engine_url);
    if (ids === null) return; // engine unreachable: keep the previous answer
    if (JSON.stringify(ids) !== JSON.stringify(l1TargetIds)) {
      l1TargetIds = ids;
      await api.storage.set({ [STORAGE_KEYS.l1Targets]: ids });
    }
    if (!ids.length) uploader.clear();
  }

  async function onAlarm(name: string): Promise<void> {
    if (name === "tick") {
      await batcher.flush();
      await uploader.flush();
      await refreshConsent();
      if (cfg.capturing) void startRect();
    }
  }

  async function startRect(): Promise<void> {
    if (rectRunning) return;
    rectRunning = true;
    try {
      while (cfg.capturing) {
        const out = await poller.tick();
        rectReachable = out.reachable;
        if (out.reachable) api.keepAlive();
        else if (out.delay >= 8000) break; // desktop app not running: the next alarm tries again
        if (out.delay > 0) await deps.sleep(out.delay);
      }
    } finally {
      rectRunning = false;
    }
  }

  return {
    init, handleMessage, onTabActivated, onConfigChanged, onAlarm, refreshConsent, startRect,
    batcher, uploader, poller,
    get config() { return cfg; },
    get l1Targets() { return l1TargetIds; },
  };
}
