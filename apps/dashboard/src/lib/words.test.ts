import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { jsxTexts, scanJson, scanSource, tokenise } from "./visibleWords";

// The owner's rule (7 Nov): the word "demo" never appears in anything a person can see or a screen reader reads. This test reads every source
// file of the dashboard and of the desktop renderer, and every fixture, and fails on a visible "demo". The allow-list is empty: the only thing
// skipped is a literal that is exactly the bare word (the `source: "demo"` enum value), which is code, and ids or paths such as `q_demo_1`.
const here = dirname(fileURLToPath(import.meta.url));
const dashboard = join(here, "..", "..");
const repo = join(dashboard, "..", "..");

function walk(dir: string, accept: (p: string) => boolean, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === "dist" || name === "out" || name === ".git") continue;
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) walk(p, accept, out);
    else if (accept(p)) out.push(p);
  }
  return out;
}

const isTest = (p: string) => /\.test\.(ts|tsx)$/.test(p);
const dashboardSources = walk(join(dashboard, "src"), (p) => /\.(ts|tsx)$/.test(p) && !isTest(p));
const fixtures = walk(join(dashboard, "src", "fixtures"), (p) => p.endsWith(".json"));
const rendererRoot = join(repo, "apps", "desktop", "src", "renderer");
// The renderer's own render harnesses are developer tools, not product screens (overlay/demo.* and the harness folders).
const rendererSources = walk(rendererRoot, (p) => /\.(ts|tsx|js)$/.test(p) && !isTest(p) && !/[\\/](overlay[\\/]demo\.|overlay[\\/]harness[\\/]|cue[\\/]harness[\\/])/.test(p));

describe("the scanner itself", () => {
  it("finds the word in strings, templates and JSX text, and only there", () => {
    const src = [
      "// a demo comment is not visible",
      'const a = "no demo here";',
      "const b = `in demo ${x} mode`;",
      'const ok = { source: "demo", demoMode: true, id: "q_demo_1" };',
      "const el = <p>Run the demo now</p>;",
      "/* demo in a block comment */",
    ].join("\n");
    const found = scanSource(src).map((h) => h.text);
    expect(found).toContain("no demo here");
    expect(found.some((t) => t.includes("in demo"))).toBe(true);
    expect(found).toContain("Run the demo now");
    expect(found.some((t) => t.includes("comment"))).toBe(false);
    expect(found).not.toContain("demo");
    expect(found.every((t) => !t.includes("q_demo_1"))).toBe(true);
  });
  it("skips the bare enum literal, identifiers glued with underscores or camel case, and paths", () => {
    expect(scanSource('x = "demo"; y = demoMode; z = r_demo_2; w = "apps/demo-stage/index.html"; v = \'data/demo-data\';')).toEqual([]);
  });
  it("is case-insensitive and respects word boundaries", () => {
    expect(scanSource('t = "Demo data";').length).toBe(1);
    expect(scanSource('t = "Demonstrates the idea";').length).toBe(0);
    expect(scanSource('t = "a demo, then";').length).toBe(1);
  });
  it("reads nested template expressions and regex literals without losing its place", () => {
    const src = 'const re = /"demo"/g; const s = `a ${cond ? "not demo" : "fine"} b`; const t = "after";';
    const found = scanSource(src).map((h) => h.text);
    expect(found).toEqual(["not demo"]);
    expect(tokenise(src).strings.map((s) => s.text)).toContain("after");
  });
  it("finds JSX text across tags and braces", () => {
    expect(jsxTexts("<p>Hello <b>big demo</b> {x} and demo after</p>").map((h) => h.text).join("|")).toMatch(/big demo/);
  });
  it("finds the word in a paragraph that runs over several lines", () => {
    const src = ["<p className=\"note\">", "  The first line says", "  something about a demo here.", "</p>"].join("\n");
    expect(scanSource(src).some((h) => /demo here/.test(h.text))).toBe(true);
  });
  it("walks JSON values and ignores keys", () => {
    expect(scanJson({ demo: "fine", note: "A demo run", nested: [{ t: "ok" }, { t: "the Demo" }], id: "q_demo_1", v: "demo" }).map((h) => h.path)).toEqual(["$.note", "$.nested[1].t"]);
  });
});

describe("no visible 'demo' anywhere", () => {
  it("is scanning real files", () => {
    expect(dashboardSources.length).toBeGreaterThan(100);
    expect(fixtures.length).toBeGreaterThan(30);
    expect(rendererSources.length).toBeGreaterThan(20);
  });

  it("in the dashboard's screens and components", () => {
    const bad: string[] = [];
    for (const f of dashboardSources) for (const h of scanSource(readFileSync(f, "utf8"))) bad.push(`${relative(repo, f)}:${h.line}  ${h.text.slice(0, 90)}`);
    expect(bad).toEqual([]);
  });

  it("in the dashboard's fixtures (what the example data says on screen)", () => {
    const bad: string[] = [];
    for (const f of fixtures) {
      let v: unknown;
      try { v = JSON.parse(readFileSync(f, "utf8")); } catch { continue; }
      for (const h of scanJson(v)) bad.push(`${relative(repo, f)} ${h.path}  ${h.text.slice(0, 90)}`);
    }
    expect(bad).toEqual([]);
  });

  it("in the desktop renderer (the panel, the dock, the overlay)", () => {
    const bad: string[] = [];
    for (const f of rendererSources) for (const h of scanSource(readFileSync(f, "utf8"))) bad.push(`${relative(repo, f)}:${h.line}  ${h.text.slice(0, 90)}`);
    expect(bad).toEqual([]);
  });

  it("in the page itself", () => {
    const html = readFileSync(join(dashboard, "index.html"), "utf8");
    expect(/\bdemo\b/i.test(html.replace(/<!--[\s\S]*?-->/g, ""))).toBe(false);
  });
});
