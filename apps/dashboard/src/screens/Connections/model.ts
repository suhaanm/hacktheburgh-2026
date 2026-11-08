// Connections: the pure part. What the engine sends for a preset (GET /connections), the words for its state, the consent lines, the fields a real
// connection needs and their checks, and the request body a click makes. No React, no network: the components and the tests both use it.
//
// Rules this file keeps (docs/CONNECTIONS.md): every connection is OFF until the worker clicks; the click carries `confirm: true` and is made on the
// consent lines the engine wrote; a token is typed by the worker, goes in one request body and is not kept anywhere here.

export type ConnState = "off" | "connected" | "needs_reconfirm" | "needs_setup" | "error";
export type ConnMode = "example" | "real";
export type Group = "dev" | "data" | "benefits";

export interface Consent {
  mode: ConnMode;
  summary: string;
  lines: string[];
  example: boolean;
  publisher: string;
  package: string | null;
  version: string | null;
  license?: string;
  hosts: string[];
  needs_token: boolean;
  caution: string;
  params?: { name: string; label: string; kind: "path" | "text" | "url" }[];
  credentials?: { env: string; label: string }[];
  verified?: boolean;
}

export interface Connection {
  id: string;
  app: string;
  group: Group;
  kind: string;
  reads: string;
  short: string;
  caution: string;
  state: ConnState;
  mode: ConnMode | null;
  reason: string | null;
  example: boolean;
  modes: { example: Consent; real: Consent | null };
  tools: Record<string, number>;
  usage: { calls: number; reads: number; changes_asked: number; refused: number; needed_click: number; last_call: string | null };
  probe: { ok: boolean; tools: number; at: string; code: string | null } | null;
  consented_at: string | null;
  roles: string[];
  routines: string[];
  agent?: "online" | "offline";
  note?: string;
}

export const GROUP_LABEL: Record<Group, string> = { dev: "Dev tools", data: "Data tools", benefits: "Benefits tools" };
export const GROUP_ORDER: Group[] = ["dev", "data", "benefits"];

/** A connection the worker switched on, whatever state it is in now. */
export const isOn = (c: Connection): boolean => c.state !== "off";

/** The one word for a connection's state (two words at most, the pill budget). The colour only repeats it. */
export function stateWord(c: Connection): string {
  switch (c.state) {
    case "off": return "Off";
    case "connected": return c.mode === "example" ? "Example" : "On";
    case "needs_reconfirm": return "Changed";
    case "needs_setup": return "Needs setup";
    case "error": return "Problem";
  }
}

export type Tone = "idle" | "good" | "warn" | "bad";
export function stateTone(c: Connection): Tone {
  return c.state === "connected" ? "good" : c.state === "error" ? "bad" : c.state === "off" ? "idle" : "warn";
}

/** What it has read, as counts only (six words at most). */
export function usageLine(c: Connection): string {
  const u = c.usage;
  if (!u || u.calls === 0) return "Not used yet";
  const reads = `${u.reads} ${u.reads === 1 ? "read" : "reads"}`;
  const changes = u.changes_asked === 0 ? "no changes" : `${u.changes_asked} asked to change`;
  return `${reads}, ${changes}`;
}

/** The sentence under a row: what it can read when it is off, what happened when it is on, and why it needs the worker when it does. */
export function metaLine(c: Connection): string {
  if (c.state === "needs_reconfirm") return "It changed since you agreed.";
  if (c.state === "needs_setup") return "Its token is missing.";
  if (c.state === "error") return "It did not start. Nothing was read.";
  if (c.state === "connected") return usageLine(c);
  return c.short || c.reads;
}

export const consentFor = (c: Connection, mode: ConnMode): Consent | null => (mode === "real" ? c.modes.real : c.modes.example);
export const hasReal = (c: Connection): boolean => c.modes.real !== null;

// ---- the fields of a real connection ------------------------------------------------------------------------------------------------------
export interface Field {
  key: string;                 // a param name, or a credential's environment name
  label: string;
  kind: "path" | "text" | "url" | "secret";
  secret: boolean;
}

export function fieldsFor(c: Connection, mode: ConnMode): Field[] {
  if (mode !== "real" || !c.modes.real) return [];
  const real = c.modes.real;
  return [
    ...(real.params ?? []).map((p): Field => ({ key: p.name, label: p.label, kind: p.kind, secret: false })),
    ...(real.credentials ?? []).map((k): Field => ({ key: k.env, label: k.label, kind: "secret", secret: true })),
  ];
}

/** The same rule the engine applies: printable ASCII without space, double quote or backslash, 4 to 4096 characters. */
export const TOKEN_OK = /^[\x21\x23-\x5b\x5d-\x7e]{4,4096}$/;

/** A plain sentence for the first problem with what the worker typed, or null. The token is never repeated in it. */
export function problemWith(c: Connection, mode: ConnMode, values: Record<string, string>): string | null {
  for (const f of fieldsFor(c, mode)) {
    const v = (values[f.key] ?? "").trim();
    if (!v) return `${f.label} is needed.`;
    if (f.secret && !TOKEN_OK.test(v)) return "The token has a space, a quote or a backslash, or is too short. Paste it again without them.";
    if (f.kind === "path" && (!v.startsWith("/") || v.split("/").includes(".."))) return `${f.label} must be a full folder path.`;
    if (f.kind === "url" && !/^https?:\/\/[^/@\s]+/i.test(v)) return `${f.label} must be an address like https://example.org.`;
  }
  return null;
}

/** The body of the one click that connects. `confirm` is true only because the worker pressed the button under the consent lines. */
export function connectBody(c: Connection, mode: ConnMode, values: Record<string, string>): { mode: ConnMode; confirm: true; params?: Record<string, string>; secrets?: Record<string, string> } {
  const params: Record<string, string> = {};
  const secrets: Record<string, string> = {};
  for (const f of fieldsFor(c, mode)) (f.secret ? secrets : params)[f.key] = (values[f.key] ?? "").trim();
  return { mode, confirm: true, ...(Object.keys(params).length ? { params } : {}), ...(Object.keys(secrets).length ? { secrets } : {}) };
}

// ---- lists --------------------------------------------------------------------------------------------------------------------------------
export function byGroup(list: Connection[]): { group: Group; items: Connection[] }[] {
  return GROUP_ORDER.map((g) => ({ group: g, items: list.filter((c) => c.group === g) })).filter((x) => x.items.length > 0);
}

/** Connections the worker has on come first, then the rest in the order the pack gives. */
export function onFirst(list: Connection[]): Connection[] {
  return [...list.filter(isOn), ...list.filter((c) => !isOn(c))];
}

// ---- words and budgets (docs/knack-ux/budgets.json) ------------------------------------------------------------------------------------------
export const BUDGET = { rowTitleWords: 12, rowMetaWords: 6, buttonWords: 3, pillWords: 2, consentWords: 60 } as const;
export const wordCount = (s: string): number => s.trim().split(/\s+/).filter(Boolean).length;

/** Where the traffic goes, printed in the panel (an honesty item: never hidden behind a hint). */
export const TRAFFIC_NOTE = "A connected app's traffic goes from its own process to its own hosts, outside the frame guard. Knack never sends your screen through a connection.";
