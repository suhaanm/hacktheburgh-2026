import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { createServer as createHttp, type IncomingHttpHeaders, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { mkdirSync, mkdtempSync, rmSync, unlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { preview as createPreview, type PreviewServer } from "vite";
import { MISSING_HEADER, TOKEN_HEADER, proxyTable, tokenProxyPlugin } from "../../vite.proxy";

const TOKEN_A = "tok_aaaaaaaaaaaaaaaaaaaaaaaa";
const TOKEN_B = "tok_bbbbbbbbbbbbbbbbbbbbbbbb";

/**
 * `vite preview` serves the built dashboard and has its own plugin hook (configurePreviewServer). The same guard must run there,
 * because the demo may serve the built page. A real preview server stands in front of a fake engine on ephemeral ports.
 */
describe("through vite preview (the built dashboard)", () => {
  let upstream: Server, pv: PreviewServer, dir: string, base: string;
  const seen: { url?: string; headers: IncomingHttpHeaders }[] = [];

  beforeAll(async () => {
    dir = mkdtempSync(join(tmpdir(), "understudy-preview-"));
    mkdirSync(join(dir, "dist"));
    writeFileSync(join(dir, "dist", "index.html"), "<!doctype html><title>built</title>");
    upstream = createHttp((req, res) => {
      seen.push({ url: req.url, headers: req.headers });
      res.setHeader("Content-Type", "application/json");
      res.end("{}");
    });
    await new Promise<void>((r) => upstream.listen(0, "127.0.0.1", r));
    const port = (upstream.address() as AddressInfo).port;
    const env = { UNDERSTUDY_DATA_DIR: dir, ENGINE_PORT: String(port), AGENT_PORT: String(port) };
    pv = await createPreview({
      configFile: false, root: dir, logLevel: "silent", build: { outDir: join(dir, "dist") },
      plugins: [tokenProxyPlugin(env, dir)],
      preview: { host: "127.0.0.1", port: 0, strictPort: false, proxy: proxyTable(env) },
    });
    base = (pv.resolvedUrls?.local[0] ?? "").replace(/\/$/, "");
  }, 30_000);

  afterAll(async () => {
    await pv?.close();
    await new Promise<void>((r) => upstream?.close(() => r()));
    rmSync(dir, { recursive: true, force: true }); // the temporary folder this test made for itself
  });

  const post = (path: string, headers: Record<string, string> = {}) =>
    fetch(`${base}${path}`, { method: "POST", headers: { "Content-Type": "application/json", "X-Understudy-Actor": "worker", ...headers }, body: "{}" });

  it("serves the built page and adds the token to a proxied write, read again on every request", async () => {
    expect((await fetch(`${base}/`)).status).toBe(200);
    writeFileSync(join(dir, ".token"), `${TOKEN_A}\n`, { mode: 0o600 });
    const r = await post("/engine/queue/q_1/approve");
    expect(r.status).toBe(200);
    expect(seen.at(-1)?.url).toBe("/queue/q_1/approve");
    expect(seen.at(-1)?.headers[TOKEN_HEADER]).toBe(TOKEN_A);
    writeFileSync(join(dir, ".token"), `${TOKEN_B}\n`);
    await post("/agent/kill");
    expect(seen.at(-1)?.headers[TOKEN_HEADER]).toBe(TOKEN_B);
  });

  it("refuses a foreign page, replaces a forged token, and flags a missing token file, as in dev", async () => {
    writeFileSync(join(dir, ".token"), `${TOKEN_A}\n`);
    const before = seen.length;
    expect((await post("/engine/kill/clear", { Origin: "https://evil.example" })).status).toBe(403);
    expect(seen.length).toBe(before); // it never reached the engine
    await post("/engine/kill/clear", { "X-Understudy-Token": "forged-forged-forged-forged" });
    expect(seen.at(-1)?.headers[TOKEN_HEADER]).toBe(TOKEN_A);
    unlinkSync(join(dir, ".token"));
    const r = await post("/engine/queue/q_1/approve");
    expect(r.headers.get(MISSING_HEADER)).toBe("missing");
    expect(seen.at(-1)?.headers[TOKEN_HEADER]).toBeUndefined();
  });
});
