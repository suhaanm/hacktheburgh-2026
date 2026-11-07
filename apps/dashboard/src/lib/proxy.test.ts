import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { createServer as createHttp, type IncomingHttpHeaders, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createServer as createVite, type ViteDevServer } from "vite";
import { AGENT_PREFIX, ENGINE_PREFIX, MISSING_HEADER, TOKEN_HEADER, checkRequest, dataDir, isProxied, makeGuard, parseToken, proxyTable, readToken, tokenFile, tokenProxyPlugin } from "../../vite.proxy";

const TOKEN_A = "tok_aaaaaaaaaaaaaaaaaaaaaaaa";
const TOKEN_B = "tok_bbbbbbbbbbbbbbbbbbbbbbbb";

describe("where the token lives", () => {
  it("is in <repo>/data/.token unless a data dir is set, as the services decide it", () => {
    expect(tokenFile({}, "/repo")).toBe("/repo/data/.token");
    expect(tokenFile({ UNDERSTUDY_DATA_DIR: "" }, "/repo")).toBe("/repo/data/.token");
    expect(tokenFile({ UNDERSTUDY_DATA_DIR: "/tmp/demo-data" }, "/repo")).toBe("/tmp/demo-data/.token");
    expect(dataDir({ UNDERSTUDY_DATA_DIR: "data/demo-data" }, "/repo")).toBe("/repo/data/demo-data");
  });
  it("accepts one clean line and nothing else", () => {
    expect(parseToken(`${TOKEN_A}\n`)).toBe(TOKEN_A);
    expect(parseToken("short")).toBeNull();
    expect(parseToken("")).toBeNull();
    expect(parseToken(`${TOKEN_A} extra words`)).toBeNull();
    expect(parseToken(`${TOKEN_A}\nsecond line`)).toBeNull();
  });
  it("reads null when the file is missing", () => {
    expect(readToken("/nonexistent/dir/.token")).toBeNull();
  });
});

describe("which requests may carry the token", () => {
  const ok = { host: "127.0.0.1:5173" };
  it("forwards only the two prefixes", () => {
    expect(isProxied("/engine/health")).toBe(true);
    expect(isProxied("/agent/kill?x=1")).toBe(true);
    expect(isProxied("/engine")).toBe(true);
    expect(isProxied("/engineer")).toBe(false);
    expect(isProxied("/assets/app.js")).toBe(false);
    expect(isProxied(undefined)).toBe(false);
  });
  it("allows the same origin and a request with no Origin", () => {
    expect(checkRequest(ok)).toBeNull();
    expect(checkRequest({ ...ok, origin: "http://127.0.0.1:5173", "sec-fetch-site": "same-origin" })).toBeNull();
    expect(checkRequest({ host: "localhost:5173", origin: "http://localhost:5173" })).toBeNull();
  });
  it("refuses another page, another port, a cross-site fetch and a foreign Host", () => {
    expect(checkRequest({ ...ok, origin: "https://evil.example" })?.code).toBe("origin_refused");
    expect(checkRequest({ ...ok, origin: "http://127.0.0.1:9999" })?.code).toBe("origin_refused");
    expect(checkRequest({ ...ok, origin: "null" })?.code).toBe("origin_refused");
    expect(checkRequest({ ...ok, "sec-fetch-site": "cross-site" })?.code).toBe("origin_refused");
    expect(checkRequest({ host: "evil.example:5173" })?.code).toBe("host_refused");
    expect(checkRequest({})?.code).toBe("host_refused");
  });
});

describe("the proxy table", () => {
  it("points at the engine and agent ports, with the dev.sh variables as overrides", () => {
    const d = proxyTable({});
    expect(d[ENGINE_PREFIX].target).toBe("http://127.0.0.1:7700");
    expect(d[AGENT_PREFIX].target).toBe("http://127.0.0.1:7710");
    const o = proxyTable({ ENGINE_PORT: "7790", AGENT_PORT: "7791" });
    expect(o[ENGINE_PREFIX].target).toBe("http://127.0.0.1:7790");
    expect(o[AGENT_PREFIX].target).toBe("http://127.0.0.1:7791");
    expect(proxyTable({ ENGINE_PORT: "not a port" })[ENGINE_PREFIX].target).toBe("http://127.0.0.1:7700");
  });
  it("forwards the service's own Host, which the services require, and leaves Origin to the browser", () => {
    const t = proxyTable({});
    expect(t[ENGINE_PREFIX].changeOrigin).toBe(true);
    expect(t[AGENT_PREFIX].changeOrigin).toBe(true);
  });
  it("strips its prefix and keeps the query", () => {
    const rw = proxyTable({})[ENGINE_PREFIX].rewrite!;
    expect(rw("/engine/queue?status=all")).toBe("/queue?status=all");
    expect(rw("/engine")).toBe("/");
  });
});

describe("the guard, with plain request objects", () => {
  const fakeRes = () => { const r = { statusCode: 200, headers: {} as Record<string, string>, body: "", setHeader(k: string, v: string) { r.headers[k.toLowerCase()] = v; }, end(b?: string) { r.body = b ?? ""; } }; return r; };
  it("reads the token again on every request", () => {
    let current: string | null = TOKEN_A;
    const guard = makeGuard({ readToken: () => current });
    const run = () => { const req = { url: "/engine/queue/q_1/approve", headers: { host: "127.0.0.1:5173" } as IncomingHttpHeaders }; guard(req as never, fakeRes() as never, () => undefined); return req.headers[TOKEN_HEADER]; };
    expect(run()).toBe(TOKEN_A);
    current = TOKEN_B; // the services restarted and made a new token
    expect(run()).toBe(TOKEN_B);
  });
  it("throws away a token the page sent, even when there is none to add", () => {
    const guard = makeGuard({ readToken: () => null });
    const req = { url: "/agent/kill", headers: { host: "127.0.0.1:5173", [TOKEN_HEADER]: "forged-forged-forged-forged" } as IncomingHttpHeaders };
    const res = fakeRes();
    let called = false;
    guard(req as never, res as never, () => { called = true; });
    expect(called).toBe(true);
    expect(req.headers[TOKEN_HEADER]).toBeUndefined();
    expect(res.headers[MISSING_HEADER]).toBe("missing");
  });
  it("refuses a foreign page with a 403 and never calls on", () => {
    const guard = makeGuard({ readToken: () => TOKEN_A });
    const req = { url: "/engine/kill/clear", headers: { host: "127.0.0.1:5173", origin: "https://evil.example" } as IncomingHttpHeaders };
    const res = fakeRes();
    let called = false;
    guard(req as never, res as never, () => { called = true; });
    expect(called).toBe(false);
    expect(res.statusCode).toBe(403);
    expect(JSON.parse(res.body).error.code).toBe("origin_refused");
    expect(req.headers[TOKEN_HEADER]).toBeUndefined();
  });
  it("leaves every other path alone", () => {
    const guard = makeGuard({ readToken: () => TOKEN_A });
    const req = { url: "/src/main.tsx", headers: { host: "127.0.0.1:5173" } as IncomingHttpHeaders };
    let called = false;
    guard(req as never, fakeRes() as never, () => { called = true; });
    expect(called).toBe(true);
    expect(req.headers[TOKEN_HEADER]).toBeUndefined();
  });
});

/* A real Vite dev server in front of a fake engine, on ephemeral ports: what the upstream receives is what the page's request became. */
describe("through a real Vite server", () => {
  let upstream: Server, vite: ViteDevServer, dir: string, base: string, upstreamPort = 0;
  const seen: { method?: string; url?: string; headers: IncomingHttpHeaders }[] = [];

  beforeAll(async () => {
    dir = mkdtempSync(join(tmpdir(), "understudy-proxy-"));
    upstream = createHttp((req, res) => {
      seen.push({ method: req.method, url: req.url, headers: req.headers });
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify({ ok: true }));
    });
    await new Promise<void>((r) => upstream.listen(0, "127.0.0.1", r));
    const port = (upstream.address() as AddressInfo).port;
    upstreamPort = port;
    const env = { UNDERSTUDY_DATA_DIR: dir, ENGINE_PORT: String(port), AGENT_PORT: String(port) };
    vite = await createVite({
      configFile: false, root: dir, logLevel: "silent", optimizeDeps: { noDiscovery: true, include: [] },
      plugins: [tokenProxyPlugin(env, dir)],
      server: { host: "127.0.0.1", port: 0, strictPort: false, proxy: proxyTable(env), hmr: false, watch: null },
    });
    await vite.listen();
    base = `http://127.0.0.1:${vite.config.server.port}`;
  }, 30_000);

  afterAll(async () => { await vite?.close(); await new Promise<void>((r) => upstream?.close(() => r())); rmSync(dir, { recursive: true, force: true }); });

  const post = (path: string, headers: Record<string, string> = {}) => fetch(`${base}${path}`, { method: "POST", headers: { "Content-Type": "application/json", "X-Understudy-Actor": "worker", ...headers }, body: "{}" });

  it("adds the token the file holds, and the new one after the file changes", async () => {
    writeFileSync(join(dir, ".token"), `${TOKEN_A}\n`, { mode: 0o600 });
    seen.length = 0;
    const r1 = await post("/engine/queue/q_1/approve");
    expect(r1.status).toBe(200);
    expect(r1.headers.get(MISSING_HEADER)).toBeNull();
    expect(seen.at(-1)?.url).toBe("/queue/q_1/approve");
    expect(seen.at(-1)?.headers[TOKEN_HEADER]).toBe(TOKEN_A);
    expect(seen.at(-1)?.headers["x-understudy-actor"]).toBe("worker");
    expect(seen.at(-1)?.headers["content-type"]).toBe("application/json");
    expect(seen.at(-1)?.headers.host).toBe(`127.0.0.1:${upstreamPort}`); // the service's own Host, not the dashboard's
    writeFileSync(join(dir, ".token"), `${TOKEN_B}\n`, { mode: 0o600 });
    await post("/agent/kill");
    expect(seen.at(-1)?.headers[TOKEN_HEADER]).toBe(TOKEN_B);
  });

  it("passes the browser's own Origin through to the service untouched", async () => {
    writeFileSync(join(dir, ".token"), `${TOKEN_A}\n`);
    await post("/engine/queue/q_1/approve", { Origin: base });
    expect(seen.at(-1)?.headers.origin).toBe(base);
  });

  it("replaces a token the page tried to supply", async () => {
    writeFileSync(join(dir, ".token"), `${TOKEN_A}\n`);
    await post("/engine/kill/clear", { "X-Understudy-Token": "forged-forged-forged-forged" });
    expect(seen.at(-1)?.headers[TOKEN_HEADER]).toBe(TOKEN_A);
  });

  it("sends no token, and says so, when the file is missing", async () => {
    rmSync(join(dir, ".token"), { force: true });
    const r = await post("/engine/queue/q_1/approve");
    expect(r.status).toBe(200);
    expect(r.headers.get(MISSING_HEADER)).toBe("missing");
    expect(seen.at(-1)?.headers[TOKEN_HEADER]).toBeUndefined();
  });

  it("does not forward a request from another web page", async () => {
    writeFileSync(join(dir, ".token"), `${TOKEN_A}\n`);
    const before = seen.length;
    const r = await post("/engine/kill/clear", { Origin: "https://evil.example" });
    expect(r.status).toBe(403);
    expect(seen.length).toBe(before); // it never reached the engine
  });
});
