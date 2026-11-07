/**
 * The dashboard never calls the engine or the agent service across origins. It calls its own origin under two prefixes and the
 * Vite dev (and preview) server forwards the request. That one hop is where the per-boot token is added:
 *
 *   /engine/*  ->  http://127.0.0.1:<ENGINE_PORT, default 7700>/*
 *   /agent/*   ->  http://127.0.0.1:<AGENT_PORT,  default 7710>/*
 *
 * The token lives in `<data dir>/.token` (mode 0600, made at boot by the first service up). A browser page cannot read that file, and
 * this page never sees the token: the server reads it on every request, so a restart that makes a new token is picked up without
 * restarting Vite, and sets `X-Understudy-Token` on the forwarded request. It is added only after three checks:
 *   1. the request is for one of the two prefixes (nothing else is proxied);
 *   2. the Host is a loopback name, which stops DNS rebinding;
 *   3. a browser Origin, when there is one, is this same origin, and `Sec-Fetch-Site` is not cross-site.
 * A request from any other web page therefore never receives the token. Any token header the page itself sent is thrown away.
 * If the token file is missing nothing is added, and the response carries `X-Understudy-Proxy-Token: missing` so the page can say
 * "restart `make dev`" instead of a bare 403.
 *
 * Pure functions are exported so they can be tested without a browser.
 */
import { readFileSync } from "node:fs";
import { homedir } from "node:os";
import { isAbsolute, join, resolve } from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { Plugin, ProxyOptions } from "vite";

export const ENGINE_PREFIX = "/engine";
export const AGENT_PREFIX = "/agent";
export const TOKEN_HEADER = "x-understudy-token";
export const MISSING_HEADER = "x-understudy-proxy-token";

type Env = Record<string, string | undefined>;

/** `<UNDERSTUDY_DATA_DIR>` when set (the demo uses `data/demo-data`), else `<repo>/data`: the same rule the services use. */
export function dataDir(env: Env, repoRoot: string): string {
  const e = (env.UNDERSTUDY_DATA_DIR ?? "").trim();
  if (!e) return join(repoRoot, "data");
  const expanded = e === "~" ? homedir() : e.startsWith("~/") ? join(homedir(), e.slice(2)) : e;
  return isAbsolute(expanded) ? resolve(expanded) : resolve(repoRoot, expanded);
}

export const tokenFile = (env: Env, repoRoot: string): string => join(dataDir(env, repoRoot), ".token");

/** A token is one line of printable characters, at least 16 long. Anything else is treated as no token, so a half-written file is never sent. */
export function parseToken(raw: string): string | null {
  const t = raw.trim();
  return /^[\x21-\x7e]{16,256}$/.test(t) ? t : null;
}

/** Read it afresh, every time. Returns null when the file is missing or unreadable. */
export function readToken(file: string): string | null {
  try { return parseToken(readFileSync(file, "utf8")); } catch { return null; }
}

const LOOPBACK = new Set(["localhost", "127.0.0.1", "[::1]", "::1"]);
const hostname = (hostHeader: string): string => {
  const h = hostHeader.trim().toLowerCase();
  return h.startsWith("[") ? h.slice(0, h.indexOf("]") + 1) : h.split(":")[0];
};

export type Refusal = { code: "origin_refused" | "host_refused"; message: string };

/** Decide whether a proxied request may carry the token. Returns a refusal, or null when it is fine. */
export function checkRequest(headers: IncomingMessage["headers"]): Refusal | null {
  const host = String(headers.host ?? "");
  if (!LOOPBACK.has(hostname(host))) return { code: "host_refused", message: "The dashboard only answers on this computer's own address." };
  const origin = headers.origin;
  if (typeof origin === "string" && origin !== "") {
    let same = false;
    try {
      const o = new URL(origin);
      same = LOOPBACK.has(o.hostname.toLowerCase()) && o.host.toLowerCase() === host.toLowerCase();
    } catch { same = false; }
    if (!same) return { code: "origin_refused", message: "This request came from another web page, so it was not forwarded to the engine." };
  }
  const site = headers["sec-fetch-site"];
  if (typeof site === "string" && site !== "same-origin" && site !== "none") {
    return { code: "origin_refused", message: "This request came from another web page, so it was not forwarded to the engine." };
  }
  return null;
}

export const isProxied = (url: string | undefined): boolean => {
  const p = (url ?? "").split("?")[0];
  return p === ENGINE_PREFIX || p.startsWith(`${ENGINE_PREFIX}/`) || p === AGENT_PREFIX || p.startsWith(`${AGENT_PREFIX}/`);
};

type Next = (err?: unknown) => void;
type Req = IncomingMessage & { url?: string };

/** The Connect middleware: runs before Vite's own proxy, so the header is on the request when it is forwarded. */
export function makeGuard(opts: { readToken: () => string | null }) {
  return function guard(req: Req, res: ServerResponse, next: Next): void {
    if (!isProxied(req.url)) { next(); return; }
    const refusal = checkRequest(req.headers);
    if (refusal) {
      res.statusCode = 403;
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify({ error: refusal }));
      return;
    }
    delete req.headers[TOKEN_HEADER]; // whatever the page sent is not trusted
    const token = opts.readToken();
    if (token) req.headers[TOKEN_HEADER] = token;
    else res.setHeader(MISSING_HEADER, "missing");
    next();
  };
}

/** The proxy table. The ports come from the same variables `scripts/dev.sh` uses. */
export function proxyTable(env: Env): Record<string, ProxyOptions> {
  const port = (v: string | undefined, d: number) => { const n = Number(v); return Number.isInteger(n) && n > 0 && n < 65536 ? n : d; };
  const strip = (prefix: string) => (path: string) => path.slice(prefix.length) || "/";
  return {
    [ENGINE_PREFIX]: { target: `http://127.0.0.1:${port(env.ENGINE_PORT, 7700)}`, changeOrigin: false, rewrite: strip(ENGINE_PREFIX) },
    [AGENT_PREFIX]: { target: `http://127.0.0.1:${port(env.AGENT_PORT, 7710)}`, changeOrigin: false, rewrite: strip(AGENT_PREFIX) },
  };
}

/** The plugin that installs the guard for both `vite` (dev) and `vite preview`. */
export function tokenProxyPlugin(env: Env, repoRoot: string): Plugin {
  const guard = makeGuard({ readToken: () => readToken(tokenFile(env, repoRoot)) });
  return {
    name: "understudy-token-proxy",
    configureServer(server) { server.middlewares.use(guard); },
    configurePreviewServer(server) { server.middlewares.use(guard); },
  };
}
