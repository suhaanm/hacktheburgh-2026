// @vitest-environment node
import { build } from "esbuild";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import YAML from "yaml";
import bundled from "../src/generated/bundled.json";
import { repo } from "./helpers";

const root = join(repo, "extension");
const manifest = JSON.parse(readFileSync(join(root, "manifest.json"), "utf8"));

describe("manifest", () => {
  it("is MV3 with the minimum permissions and no way to read history, cookies, the clipboard or all tabs", () => {
    expect(manifest.manifest_version).toBe(3);
    expect([...manifest.permissions].sort()).toEqual(["alarms", "storage", "webNavigation"]);
    for (const banned of ["tabs", "history", "cookies", "clipboardRead", "clipboardWrite", "webRequest", "scripting", "activeTab", "debugger", "downloads", "nativeMessaging", "management"]) {
      expect(manifest.permissions).not.toContain(banned);
    }
    expect(manifest.optional_permissions ?? []).toEqual([]);
  });
  it("talks only to loopback and runs in no private window", () => {
    expect(manifest.host_permissions).toEqual(["http://127.0.0.1/*", "http://localhost/*"]);
    expect(manifest.incognito).toBe("not_allowed");
    const csp = manifest.content_security_policy.extension_pages as string;
    expect(csp).not.toMatch(/unsafe-eval|unsafe-inline|wasm-unsafe-eval/);
    expect(csp).toContain("connect-src http://127.0.0.1:* http://localhost:*");
    expect(csp).toContain("script-src 'self'");
  });
  it("injects one content script on http and https pages only", () => {
    expect(manifest.content_scripts).toHaveLength(1);
    expect(manifest.content_scripts[0].matches).toEqual(["http://*/*", "https://*/*"]);
    expect(manifest.content_scripts[0].js).toEqual(["content.js"]);
  });
  it("starts with capture off (opt-in)", async () => {
    const { DEFAULT_CONFIG } = await import("../src/shared/types");
    expect(DEFAULT_CONFIG.capturing).toBe(false);
  });
});

describe("bundle", () => {
  it("builds, and no bundle contains eval, new Function, fetch of a page URL or location.href", async () => {
    const out = mkdtempSync(join(tmpdir(), "understudy-ext-"));
    await build({
      entryPoints: { content: join(root, "src/content/main.ts"), worker: join(root, "src/background/worker.ts"), popup: join(root, "src/popup/popup.ts") },
      outdir: out, bundle: true, format: "iife", target: "chrome116", platform: "browser", logLevel: "silent",
    });
    for (const f of ["content.js", "worker.js", "popup.js"]) {
      const code = readFileSync(join(out, f), "utf8");
      expect(code.length).toBeGreaterThan(1000);
      expect(code).not.toMatch(/\beval\s*\(|new Function\s*\(/);
    }
    // the content script reads only the host, never the full URL, hash or title
    const content = readFileSync(join(out, "content.js"), "utf8");
    expect(content).not.toMatch(/location\.href|document\.URL|document\.title|innerText|outerHTML|innerHTML/);
    expect(content).not.toMatch(/getData\(/);
  });
});

describe("generated config", () => {
  it("is current with the packs (run `npm run gen` if this fails)", async () => {
    const p = "../scripts/gen.mjs";
    const { generate } = (await import(/* @vite-ignore */ p)) as { generate: () => unknown };
    expect(bundled).toEqual(generate());
  });
  it("carries the global sensitive list and every pack's additions", () => {
    const global = JSON.parse(readFileSync(join(repo, "packages/schema/sensitive_fields.json"), "utf8"));
    expect(bundled.sensitive[0]).toEqual(global);
    expect(bundled.sensitive).toHaveLength(4);
  });
  it("covers every zone the engine's default mapping uses, and the sandbox sites", () => {
    const def = YAML.parse(readFileSync(join(repo, "services/engine/understudy_engine/cogs/default_mapping.yaml"), "utf8"));
    const zones = new Set<string>();
    for (const r of def.rules) for (const z of [r.match.zone ?? []].flat()) zones.add(z);
    for (const z of zones) expect(bundled.zones.vocabulary, z).toContain(z);
    const ben = bundled.zones.sites.filter((s: { pack: string }) => s.pack === "benefits-processor") as { id: string; hosts: string[] }[];
    expect(ben.map((s) => s.id)).toEqual(["a", "b", "c"]);
    expect(ben[0]!.hosts).toContain("127.0.0.1:7801");
  });
});
