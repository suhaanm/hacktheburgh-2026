// Service worker entry: binds chrome.* to the testable core.
import { createWorker, type ContentMessage, type WorkerApi } from "./worker_core";
import { STORAGE_KEYS } from "../shared/types";

const api: WorkerApi = {
  storage: chrome.storage.local as unknown as WorkerApi["storage"],
  sendToTab: (tabId, msg, frameId) => chrome.tabs.sendMessage(tabId, msg, { frameId }).catch(() => null),
  queryActiveTab: async () => {
    const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    return tab?.id !== undefined ? { id: tab.id } : null;
  },
  getFrameIds: async (tabId) => {
    const frames = await chrome.webNavigation.getAllFrames({ tabId });
    return (frames ?? []).map((f) => f.frameId);
  },
  keepAlive: () => void chrome.runtime.getPlatformInfo(() => void 0),
};

const worker = createWorker(api, {
  fetch: (...a) => fetch(...a),
  now: () => Date.now(),
  setTimer: (fn, ms) => setTimeout(fn, ms),
  clearTimer: (h) => clearTimeout(h as ReturnType<typeof setTimeout>),
  sleep: (ms) => new Promise((r) => setTimeout(r, ms)),
});

const ready = worker.init();

chrome.runtime.onMessage.addListener((msg: ContentMessage, sender, sendResponse) => {
  // Only our own content scripts and popup talk to the worker.
  if (sender.id !== chrome.runtime.id) return false;
  ready.then(() => worker.handleMessage(msg)).then(sendResponse, () => sendResponse({ ok: false }));
  return true;
});

chrome.tabs.onActivated.addListener((info) => {
  void ready.then(() => worker.onTabActivated(info.tabId));
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && changes[STORAGE_KEYS.config]) void ready.then(() => worker.onConfigChanged(changes[STORAGE_KEYS.config]?.newValue));
});

chrome.alarms.create("tick", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener((a) => void ready.then(() => worker.onAlarm(a.name)));
chrome.runtime.onInstalled.addListener(() => void ready);
