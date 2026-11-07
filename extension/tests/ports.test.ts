// @vitest-environment node
import { execFileSync, spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterAll, describe, expect, it } from "vitest";
import bundled from "../src/generated/bundled.json";

const ext = fileURLToPath(new URL("..", import.meta.url));
type Ports = Record<string, number>;
type Site = { pack: string; id: string; hosts: string[] };
type Cfg = { zones: { sites: Site[] } };
interface Gen {
  defaultPorts(): Ports;
  generate(o?: { ports?: Ports }): Cfg;
  portOverrides(env: Record<string, string>): Ports;
  effectivePorts(o?: Ports): Ports;
}
interface Bld {
  buildExtension(o?: { ports?: Ports; outDir?: string; logLevel?: string }): Promise<{ outDir: string; ports: Ports; config: Cfg; isDefault: boolean }>;
  resolveOutArg(name?: string): string;
}
// plain node scripts: loaded through a variable path so TypeScript does not look for declarations
const genPath = "../scripts/gen.mjs";
const bldPath = "../scripts/build.mjs";
const gen = (await import(/* @vite-ignore */ genPath)) as Gen;
const bld = (await import(/* @vite-ignore */ bldPath)) as Bld;

const SIM = { a: 7911, b: 7912, c: 7913 };
const tmp = mkdtempSync(join(tmpdir(), "understudy-ports-"));
afterAll(() => rmSync(tmp, { recursive: true, force: true }));

const hostsOf = (cfg: Cfg, pack = "benefits-processor") =>
  Object.fromEntries(cfg.zones.sites.filter((s) => s.pack === pack).map((s) => [s.id, s.hosts]));

describe("generate with a port triple", () => {
  it("defaults to tasks/sites.yaml (7801 to 7803) and equals the committed bundle", () => {
    expect(gen.defaultPorts()).toEqual({ a: 7801, b: 7802, c: 7803 });
    expect(gen.generate()).toEqual(bundled);
    expect(gen.generate({ ports: { a: 7801, b: 7802, c: 7803 } })).toEqual(bundled);
  });

  it("puts exactly the requested hosts on the benefits sites and no default port anywhere", () => {
    const cfg = gen.generate({ ports: SIM });
    expect(hostsOf(cfg)).toEqual({
      a: ["127.0.0.1:7911", "localhost:7911"],
      b: ["127.0.0.1:7912", "localhost:7912"],
      c: ["127.0.0.1:7913", "localhost:7913"],
    });
    const text = JSON.stringify(cfg);
    for (const p of ["7801", "7802", "7803"]) expect(text, p).not.toContain(p);
  });

  it("changes nothing but those hosts: zones, selectors, markers and the other packs stay identical", () => {
    const sim = gen.generate({ ports: SIM });
    const strip = (c: typeof sim) => ({ ...c, zones: { ...c.zones, sites: c.zones.sites.map((s) => ({ ...s, hosts: [] as string[] })) } });
    expect(strip(sim)).toEqual(strip(bundled as unknown as typeof sim));
    expect(hostsOf(sim, "data-analyst")).toEqual(hostsOf(bundled as unknown as Cfg, "data-analyst"));
    expect(hostsOf(sim, "programmer")).toEqual(hostsOf(bundled as unknown as Cfg, "programmer"));
    const a = sim.zones.sites.find((s) => s.pack === "benefits-processor" && s.id === "a") as unknown as { markers?: unknown; elements: unknown[] };
    expect(a.markers).toBeTruthy();
    expect(a.elements.length).toBeGreaterThan(3);
  });

  it("a partial override leaves the other defaults (the triple is a union, never a mix of the same port)", () => {
    expect(hostsOf(gen.generate({ ports: { b: 7950 } })).b).toEqual(["127.0.0.1:7950", "localhost:7950"]);
    expect(hostsOf(gen.generate({ ports: { b: 7950 } })).a).toEqual(["127.0.0.1:7801", "localhost:7801"]);
  });

  it("rejects ports that cannot work", () => {
    expect(() => gen.portOverrides({ SANDBOX_PORT_A: "80" })).toThrow(/1024 to 65535/);
    expect(() => gen.portOverrides({ SANDBOX_PORT_B: "abc" })).toThrow(/not a port/);
    expect(() => gen.portOverrides({ SANDBOX_PORT_C: "70000" })).toThrow(/not a port/);
    expect(() => gen.portOverrides({ SANDBOX_PORT_C: "7911.5" })).toThrow();
    expect(gen.portOverrides({})).toEqual({});
    expect(gen.portOverrides({ SANDBOX_PORT_A: "7911", SANDBOX_PORT_C: "" })).toEqual({ a: 7911 });
    expect(() => gen.effectivePorts({ a: 7912, b: 7912 })).toThrow(/both use port 7912/);
    expect(() => gen.effectivePorts({ a: 7802 })).toThrow(/both use port 7802/);       // collides with the default of b
  });
});

describe("build for a port triple", () => {
  it("embeds exactly those hosts in every bundle and none of the defaults", async () => {
    const out = join(tmp, "dist-sim");
    const res = await bld.buildExtension({ ports: SIM, outDir: out, logLevel: "silent" });
    expect(res.ports).toEqual(SIM);
    expect(res.isDefault).toBe(false);
    for (const f of ["content.js", "worker.js", "popup.js"]) {
      const code = readFileSync(join(out, f), "utf8");
      if (f !== "worker.js") {
        for (const h of ["127.0.0.1:7911", "127.0.0.1:7912", "127.0.0.1:7913", "localhost:7911"]) expect(code, `${f} ${h}`).toContain(h);
      }
      for (const p of ["7801", "7802", "7803"]) expect(code, `${f} must not contain ${p}`).not.toContain(p);
    }
    expect(existsSync(join(out, "manifest.json")) && existsSync(join(out, "popup.html"))).toBe(true);
  });

  it("the manifest is the same permissions plus a version_name that says which ports", async () => {
    const out = join(tmp, "dist-sim2");
    await bld.buildExtension({ ports: SIM, outDir: out, logLevel: "silent" });
    const m = JSON.parse(readFileSync(join(out, "manifest.json"), "utf8"));
    const base = JSON.parse(readFileSync(join(ext, "manifest.json"), "utf8"));
    expect(m.version_name).toBe("0.1.0 sandbox 7911/7912/7913");
    const { version_name, ...rest } = m;
    expect(rest).toEqual(base);
    // Chrome ignores the port in a match pattern: these two cover 127.0.0.1:7911 to 7913 already, so nothing else is needed
    expect(m.host_permissions).toContain("http://127.0.0.1/*");
    expect(m.content_scripts[0].matches).toContain("http://*/*");
  });

  it("a default build is byte-identical to the checked-in manifest and carries the default hosts", async () => {
    const out = join(tmp, "dist-default");
    const res = await bld.buildExtension({ outDir: out, logLevel: "silent" });
    expect(res.isDefault).toBe(true);
    const m = JSON.parse(readFileSync(join(out, "manifest.json"), "utf8"));
    expect(m).toEqual(JSON.parse(readFileSync(join(ext, "manifest.json"), "utf8")));
    const code = readFileSync(join(out, "content.js"), "utf8");
    expect(code).toContain("127.0.0.1:7801");
    expect(code).not.toContain("127.0.0.1:7911");
  });

  it("two builds for different triples do not touch each other or the committed bundle", async () => {
    const before = readFileSync(join(ext, "src", "generated", "bundled.json"), "utf8");
    const [x, y] = await Promise.all([
      bld.buildExtension({ ports: { a: 7921, b: 7922, c: 7923 }, outDir: join(tmp, "dist-x"), logLevel: "silent" }),
      bld.buildExtension({ ports: { a: 7931, b: 7932, c: 7933 }, outDir: join(tmp, "dist-y"), logLevel: "silent" }),
    ]);
    expect(readFileSync(join(x.outDir, "content.js"), "utf8")).toContain("127.0.0.1:7921");
    expect(readFileSync(join(y.outDir, "content.js"), "utf8")).toContain("127.0.0.1:7931");
    expect(readFileSync(join(x.outDir, "content.js"), "utf8")).not.toContain("7931");
    expect(readFileSync(join(ext, "src", "generated", "bundled.json"), "utf8")).toBe(before);
  });
});

describe("the command line", () => {
  const env = (extra: Record<string, string>) => ({ ...process.env, ...extra });

  it("gen refuses non-default ports without --out, and writes to --out when given", () => {
    const e = env({ SANDBOX_PORT_A: "7911", SANDBOX_PORT_B: "7912", SANDBOX_PORT_C: "7913" });
    const refused = spawnSync("node", ["scripts/gen.mjs"], { cwd: ext, env: e, encoding: "utf8" });
    expect(refused.status).toBe(2);
    expect(refused.stderr).toContain("--out");
    const target = join(tmp, "bundled.7911.json");
    execFileSync("node", ["scripts/gen.mjs", "--out", target], { cwd: ext, env: e });
    const cfg = JSON.parse(readFileSync(target, "utf8"));
    expect(hostsOf(cfg).a).toEqual(["127.0.0.1:7911", "localhost:7911"]);
    expect(JSON.stringify(cfg)).not.toContain("7801");
  });

  it("gen --defaults ignores the environment (npm test is not broken by an exported triple)", () => {
    const r = spawnSync("node", ["scripts/gen.mjs", "--defaults", "--out", join(tmp, "d.json")], { cwd: ext, env: env({ SANDBOX_PORT_A: "7911" }), encoding: "utf8" });
    expect(r.status).toBe(0);
    expect(JSON.parse(readFileSync(join(tmp, "d.json"), "utf8"))).toEqual(bundled);
  });

  it("build refuses an --out that could empty anything but a dist folder", () => {
    for (const bad of ["../x", "/tmp/x", "src", "dist/../src", "dist-", "dist-a b", "node_modules"]) {
      const r = spawnSync("node", ["scripts/build.mjs", "--out", bad], { cwd: ext, encoding: "utf8" });
      expect(r.status, bad).toBe(2);
      expect(r.stderr).toContain("--out");
    }
    expect(existsSync(join(ext, "src"))).toBe(true);
    expect(() => bld.resolveOutArg("dist-sim")).not.toThrow();
    expect(bld.resolveOutArg("dist-world-3")).toBe(join(ext, "dist-world-3"));
    expect(bld.resolveOutArg("dist-sim")).toBe(join(ext, "dist-sim"));
    expect(bld.resolveOutArg(undefined)).toBe(join(ext, "dist"));
  });

  it("build with bad ports or an unknown flag exits 2 with a plain message", () => {
    const r = spawnSync("node", ["scripts/build.mjs", "--out", "dist-badports"], { cwd: ext, env: env({ SANDBOX_PORT_A: "12" }), encoding: "utf8" });
    expect(r.status).toBe(2);
    expect(r.stderr).toContain("SANDBOX_PORT_A");
    expect(existsSync(join(ext, "dist-badports"))).toBe(false);
    expect(spawnSync("node", ["scripts/build.mjs", "--nope"], { cwd: ext, encoding: "utf8" }).status).toBe(2);
  });
});
