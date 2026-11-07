// Install configuration and the per-install salt, kept in chrome.storage.local. Nothing here leaves the device.
import { randomHex } from "./hash";
import { DEFAULT_CONFIG, STORAGE_KEYS, type InstallConfig } from "./types";

export interface StorageArea {
  get(keys: string | string[]): Promise<Record<string, unknown>>;
  set(items: Record<string, unknown>): Promise<void>;
  remove(keys: string | string[]): Promise<void>;
}

const PERSON_RE = /^p_[a-z0-9]{2,16}$/;
const ROLE_RE = /^[a-z][a-z0-9-]{1,40}$/;

export function newPersonId(): string {
  return `p_${randomHex(4)}`;
}

function cleanUrl(v: unknown, fallback: string): string {
  if (typeof v !== "string") return fallback;
  try {
    const u = new URL(v);
    // the engine and desktop app are local services; refuse anything that is not loopback
    if (u.protocol !== "http:" || !["127.0.0.1", "localhost", "[::1]"].includes(u.hostname)) return fallback;
    return `${u.protocol}//${u.host}`;
  } catch {
    return fallback;
  }
}

export function normaliseConfig(raw: unknown): InstallConfig {
  const r = (typeof raw === "object" && raw !== null ? raw : {}) as Record<string, unknown>;
  return {
    capturing: r.capturing === true,
    person: typeof r.person === "string" && PERSON_RE.test(r.person) ? r.person : "",
    role: typeof r.role === "string" && ROLE_RE.test(r.role) ? r.role : DEFAULT_CONFIG.role,
    engine_url: cleanUrl(r.engine_url, DEFAULT_CONFIG.engine_url),
    desktop_url: cleanUrl(r.desktop_url, DEFAULT_CONFIG.desktop_url),
  };
}

export async function loadConfig(area: StorageArea): Promise<InstallConfig> {
  const got = await area.get(STORAGE_KEYS.config);
  return normaliseConfig(got[STORAGE_KEYS.config]);
}

/** Loads the config and makes sure a person id exists (written back once). */
export async function ensureConfig(area: StorageArea): Promise<InstallConfig> {
  const cfg = await loadConfig(area);
  if (!cfg.person) {
    cfg.person = newPersonId();
    await area.set({ [STORAGE_KEYS.config]: cfg });
  }
  return cfg;
}

export async function ensureSalt(area: StorageArea): Promise<string> {
  const got = await area.get(STORAGE_KEYS.salt);
  const existing = got[STORAGE_KEYS.salt];
  if (typeof existing === "string" && /^[0-9a-f]{32}$/.test(existing)) return existing;
  const salt = randomHex(16);
  await area.set({ [STORAGE_KEYS.salt]: salt });
  return salt;
}
