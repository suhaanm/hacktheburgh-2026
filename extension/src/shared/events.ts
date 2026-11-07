// Building and checking events. validateEvent mirrors packages/schema/event.schema.json by hand because
// MV3 service workers forbid eval, which JSON Schema compilers rely on. Tests cross-check this validator
// against the real schema with Ajv, so the two cannot drift.
import { EVENT_TYPES, type CaptureRecord, type EventType, type InstallConfig, type L0Event, type MetaValue } from "./types";

const PERSON_RE = /^p_[a-z0-9]{2,16}$/;
const ROLE_RE = /^[a-z][a-z0-9-]{1,40}$/;
const TARGET_ROLE_RE = /^[a-z][a-z0-9_-]{0,31}$/;
const LABEL_HASH_RE = /^h:[0-9a-f]{4,16}$/;
const DOMAIN_HASH_RE = /^d:[0-9a-f]{4,16}$/;
const META_KEY_RE = /^[a-z][a-z0-9_]{0,31}$/;
const META_STR_RE = /^[a-z0-9_:\-.]{0,32}$/;
const TASK_RE = /^t_[A-Za-z0-9_-]{1,32}$/;
const ISO_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/;

const KNOWN_KEYS = new Set(["schema", "id", "t", "origin", "actor", "person", "role", "source", "type", "target", "task_id", "meta"]);

export function validateMeta(meta: Record<string, MetaValue> | undefined): string | null {
  if (meta === undefined) return null;
  const keys = Object.keys(meta);
  if (keys.length > 16) return "meta has more than 16 keys";
  for (const k of keys) {
    if (!META_KEY_RE.test(k)) return `meta key ${JSON.stringify(k)} is not allowed`;
    const v = meta[k];
    if (typeof v === "number") {
      if (!Number.isFinite(v)) return `meta.${k} is not finite`;
    } else if (typeof v === "string") {
      if (!META_STR_RE.test(v)) return `meta.${k} is not a short enum token`;
    } else if (typeof v !== "boolean") return `meta.${k} has a disallowed type`;
  }
  return null;
}

/** Returns null when valid, otherwise a short reason. */
export function validateEvent(e: unknown): string | null {
  if (typeof e !== "object" || e === null) return "not an object";
  const ev = e as Record<string, unknown>;
  for (const k of Object.keys(ev)) if (!KNOWN_KEYS.has(k)) return `unknown key ${k}`;
  if (ev.schema !== 1) return "schema must be 1";
  if (typeof ev.id !== "string" || ev.id.length < 8 || ev.id.length > 64) return "bad id";
  if (typeof ev.t !== "string" || !ISO_RE.test(ev.t)) return "bad t";
  if (ev.origin !== "real" && ev.origin !== "synthetic") return "bad origin";
  if (ev.actor !== "human" && ev.actor !== "agent") return "bad actor";
  if (typeof ev.person !== "string" || !PERSON_RE.test(ev.person)) return "bad person";
  if (typeof ev.role !== "string" || !ROLE_RE.test(ev.role)) return "bad role";
  if (!["browser", "screen", "os", "desk", "agent", "coach"].includes(ev.source as string)) return "bad source";
  if (!(EVENT_TYPES as readonly string[]).includes(ev.type as string)) return "bad type";
  if (ev.task_id !== undefined && (typeof ev.task_id !== "string" || !TASK_RE.test(ev.task_id))) return "bad task_id";
  if (ev.target !== undefined) {
    const t = ev.target as Record<string, unknown>;
    if (typeof t !== "object" || t === null) return "bad target";
    for (const k of Object.keys(t)) if (!["role", "label_hash", "domain_hash"].includes(k)) return `unknown target key ${k}`;
    if (t.role !== undefined && (typeof t.role !== "string" || !TARGET_ROLE_RE.test(t.role))) return "bad target.role";
    if (t.label_hash !== undefined && (typeof t.label_hash !== "string" || !LABEL_HASH_RE.test(t.label_hash))) return "bad target.label_hash";
    if (t.domain_hash !== undefined && (typeof t.domain_hash !== "string" || !DOMAIN_HASH_RE.test(t.domain_hash))) return "bad target.domain_hash";
  }
  return validateMeta(ev.meta as Record<string, MetaValue> | undefined);
}

export function isEventType(s: string): s is EventType {
  return (EVENT_TYPES as readonly string[]).includes(s);
}

export interface EventDeps {
  now: () => number;
  uuid: () => string;
}

export function defaultUuid(): string {
  const c = globalThis.crypto;
  if (c?.randomUUID) return c.randomUUID();
  const b = new Uint8Array(16);
  if (c?.getRandomValues) c.getRandomValues(b);
  else for (let i = 0; i < 16; i++) b[i] = Math.floor(Math.random() * 256);
  b[6] = (b[6]! & 0x0f) | 0x40;
  b[8] = (b[8]! & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, "0"));
  return `${h.slice(0, 4).join("")}-${h.slice(4, 6).join("")}-${h.slice(6, 8).join("")}-${h.slice(8, 10).join("")}-${h.slice(10).join("")}`;
}

/** Wrap a content-script record into a full L0 event. Returns null when the result would be invalid. */
export function makeEvent(rec: CaptureRecord, cfg: Pick<InstallConfig, "person" | "role">, deps: EventDeps): L0Event | null {
  const ev: L0Event = {
    schema: 1,
    id: deps.uuid(),
    t: new Date(deps.now()).toISOString(),
    origin: "real",
    actor: "human",
    person: cfg.person,
    role: cfg.role,
    source: "browser",
    type: rec.type,
  };
  if (rec.target && Object.keys(rec.target).length) ev.target = { ...rec.target };
  if (rec.meta && Object.keys(rec.meta).length) ev.meta = { ...rec.meta };
  return validateEvent(ev) === null ? ev : null;
}
