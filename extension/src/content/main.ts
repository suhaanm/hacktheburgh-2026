// Content script entry (isolated world). Starts L0 capture only while the worker has capture switched on,
// L1 recording only while at least one routine is opted in, and answers rect and tab-info requests.
import bundled from "../generated/bundled.json";
import { loadConfig, type StorageArea } from "../shared/config";
import { SensitiveMatcher } from "../shared/sensitive";
import { STORAGE_KEYS, type CaptureRecord, type InstallConfig, type RecordedStep } from "../shared/types";
import { pickSite, Zoner, type ZoneConfig } from "../shared/zones";
import { domainHashOf, installCapture } from "./capture";
import { installL1 } from "./l1";
import { resolveRect, type RectWant } from "./rect";

const matcher = new SensitiveMatcher(bundled.sensitive);
const zoneConfig = bundled.zones as ZoneConfig;
const store = chrome.storage.local as unknown as StorageArea;

let cfg: InstallConfig | null = null;
let salt = "";
let zoner: Zoner | null = null;
let stopCapture: (() => void) | null = null;
let stopL1: (() => void) | null = null;
let l1Active = false;
let appliedRole = "";

const isTop = (() => { try { return window.top === window; } catch { return false; } })();
const send = (msg: unknown) => void chrome.runtime.sendMessage(msg).catch(() => undefined);

async function getSalt(): Promise<string> {
  const got = await store.get(STORAGE_KEYS.salt);
  const s = got[STORAGE_KEYS.salt];
  if (typeof s === "string" && /^[0-9a-f]{32}$/.test(s)) return s;
  const r = (await chrome.runtime.sendMessage({ kind: "get_salt" }).catch(() => null)) as { salt?: string } | null;
  return r?.salt ?? "";
}

function stop(): void {
  stopCapture?.();
  stopL1?.();
  stopCapture = stopL1 = null;
}

async function sync(): Promise<void> {
  cfg = await loadConfig(store);
  const t = (await store.get(STORAGE_KEYS.l1Targets))[STORAGE_KEYS.l1Targets];
  l1Active = Array.isArray(t) && t.length > 0;
  if (!cfg.capturing) return stop();
  if (!salt) salt = await getSalt();
  if (!salt) return stop();
  if (appliedRole && appliedRole !== cfg.role) stop(); // the role (and so the zone config) changed: start over
  appliedRole = cfg.role;
  zoner = new Zoner(zoneConfig, pickSite(zoneConfig, location.host, [cfg.role]));
  if (!stopCapture) {
    stopCapture = installCapture({ win: window, salt, matcher, zoner, emit: (record: CaptureRecord) => send({ kind: "record", record }) });
  }
  if (l1Active && !stopL1) {
    stopL1 = installL1({
      win: window, matcher, active: () => l1Active,
      emit: (step: RecordedStep) => send({ kind: "l1", step }),
      onSkipped: () => send({ kind: "l1_skipped" }),
    });
  } else if (!l1Active && stopL1) {
    stopL1();
    stopL1 = null;
  }
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id || !cfg?.capturing || !salt || !zoner) return false;
  if (msg?.kind === "rect") {
    const want = msg.want as RectWant;
    sendResponse(resolveRect(window, want, { salt, matcher }));
    return false;
  }
  if (msg?.kind === "page_info" && isTop) {
    sendResponse({ domain_hash: domainHashOf(window, salt), zone: zoner.forTab(document) });
    return false;
  }
  return false;
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local") return;
  if (changes[STORAGE_KEYS.salt]) {
    salt = "";
    stop();
  }
  if (changes[STORAGE_KEYS.config] || changes[STORAGE_KEYS.l1Targets] || changes[STORAGE_KEYS.salt]) void sync();
});

void sync();
