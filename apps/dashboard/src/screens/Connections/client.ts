// The Connections client: the engine's /connections routes, and an example fallback when the engine is not running.
//
// Reads and writes go to the engine through the same proxy as the rest of the dashboard (ENGINE_URL), with the same request headers
// (lib/http.ts: JSON and the worker actor). When the engine cannot be reached, or the layer is off, the screen shows the example list from
// fixture.json and says so; a click then only changes that local example state. A token typed into a real connection is sent in ONE request
// body and is not kept: nothing here stores, logs or returns it.
import { ENGINE_URL } from "../../api";
import { requestBody, requestHeaders } from "../../lib/http";
import offlineList from "./fixture.json";
import { connectBody, type Connection, type ConnMode } from "./model";

export interface ConnectionsClient {
  list(role?: string): Promise<{ items: Connection[]; example: boolean }>;
  connect(id: string, body: ReturnType<typeof connectBody>): Promise<Connection>;
  reconfirm(id: string): Promise<Connection>;
  revoke(id: string): Promise<Connection>;
}

export class ConnectionsError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

type Fetch = typeof fetch;
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T;
const exampleList = (): Connection[] => clone((offlineList as { data: Connection[] }).data);
const roleOrder = (role: string): string[] => ((offlineList as { roles?: Record<string, string[]> }).roles ?? {})[role] ?? [];
/** The role's connections in the order its pack gives them (the engine does the same). */
export function forRole(all: Connection[], role?: string): Connection[] {
  if (!role) return all;
  const order = roleOrder(role);
  const mine = all.filter((c) => c.roles.includes(role));
  return order.length ? order.map((id) => mine.find((c) => c.id === id)).filter((c): c is Connection => Boolean(c)) : mine;
}

async function call(f: Fetch, base: string, path: string, method: "GET" | "POST", payload?: unknown, retried = false): Promise<{ status: number; body: unknown } | null> {
  try {
    const res = await f(`${base}${path}`, { method, headers: requestHeaders(method), body: requestBody(method, payload) });
    let body: unknown = null;
    try { body = await res.json(); } catch { body = null; }
    if (!retried && res.status === 403 && method === "POST" && (body as { error?: { code?: string } } | null)?.error?.code === "token_invalid") return call(f, base, path, method, payload, true);
    return { status: res.status, body };
  } catch {
    return null;
  }
}

const dataOf = <T,>(body: unknown): T => (body && typeof body === "object" && "data" in body ? (body as { data: T }).data : (body as T));
const errorOf = (body: unknown, fallback: string): ConnectionsError => {
  const e = (body as { error?: { code?: string; message?: string } } | null)?.error;
  return new ConnectionsError(e?.code ?? "refused", e?.message ?? fallback);
};

/** The engine's own answer, or null when there is none to use (not running, layer off, route absent). */
const unusable = (r: { status: number; body: unknown } | null): boolean => r === null || r.status >= 500 || r.status === 404 && (r.body as { error?: { code?: string } } | null)?.error?.code !== "unknown_connection" || r.status === 405;

export function createClient(f: Fetch = (...a) => fetch(...a), base: string = ENGINE_URL): ConnectionsClient {
  // The example state: what the fixture becomes once the worker clicks while the engine is away.
  let local: Connection[] | null = null;
  const demo = () => (local ??= exampleList());
  const put = (id: string, patch: Partial<Connection>): Connection => {
    const c = demo().find((x) => x.id === id);
    if (!c) throw new ConnectionsError("unknown_connection", "That connection is not in the list.");
    Object.assign(c, patch);
    return clone(c);
  };
  let live = true;
  return {
    async list(role) {
      const r = await call(f, base, `/connections${role ? `?role=${encodeURIComponent(role)}` : ""}`, "GET");
      if (!unusable(r) && r && r.status < 400) { live = true; return { items: dataOf<Connection[]>(r.body), example: false }; }
      live = false;
      const all = demo();
      return { items: clone(forRole(all, role)), example: true };
    },
    async connect(id, body) {
      if (body.confirm !== true) throw new ConnectionsError("consent_required", "Connecting needs your click on the consent lines.");
      if (live) {
        const r = await call(f, base, `/connections/${encodeURIComponent(id)}/connect`, "POST", body);
        if (!unusable(r) && r) {
          if (r.status >= 400) throw errorOf(r.body, "It could not be connected. Nothing was changed.");
          return dataOf<Connection>(r.body);
        }
        live = false;
      }
      const mode: ConnMode = body.mode === "real" ? "real" : "example";   // the example state never keeps a token: it is dropped here
      return put(id, { state: "connected", mode, example: true, reason: null, consented_at: new Date().toISOString() });
    },
    async reconfirm(id) {
      if (live) {
        const r = await call(f, base, `/connections/${encodeURIComponent(id)}/reconfirm`, "POST", { confirm: true });
        if (!unusable(r) && r) {
          if (r.status >= 400) throw errorOf(r.body, "It could not be confirmed. Nothing was changed.");
          return dataOf<Connection>(r.body);
        }
        live = false;
      }
      return put(id, { state: "connected", reason: null });
    },
    async revoke(id) {
      if (live) {
        const r = await call(f, base, `/connections/${encodeURIComponent(id)}/revoke`, "POST", {});
        if (!unusable(r) && r) {
          if (r.status >= 400) throw errorOf(r.body, "It could not be revoked. Try again.");
          return dataOf<{ connection: Connection }>(r.body).connection;
        }
        live = false;
      }
      return put(id, { state: "off", mode: null, example: false, reason: null, consented_at: null, routines: [] });
    },
  };
}

let shared: ConnectionsClient | null = null;
export const defaultClient = (): ConnectionsClient => (shared ??= createClient());
