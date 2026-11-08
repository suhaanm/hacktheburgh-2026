import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { jsxTexts, scanJson, scanSource, tokenise } from "./visibleWords";
import { PENDING_D57, PENDING_D57_MAX } from "./pendingCopy";

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

/**
 * The words a person never sees (the owner's rules): "demo" (7 Nov) and "synthetic", "synthetically" and "simulated" (D57, 8 Nov 2026: say concretely where numbers
 * come from, in plain words, and draw no tag). A literal that is exactly the bare word is a data enum (`origin: "synthetic"`), not text, and is skipped.
 *
 * PENDING_D57 (src/lib/pendingCopy.ts) is the ratchet for files that are not clean yet, each entry naming its owner. A pending file must still have a finding (so the entry is deleted the
 * moment its track lands) and the list can only shrink; it must be empty by 05:00 on 8 Nov. KNACK_LINT_STRICT=1 ignores it and shows every finding.
 */
const D57_WORDS = ["synthetic", "synthetically", "simulated"] as const;
const STRICT_WORDS = process.env.KNACK_LINT_STRICT === "1";

describe("no visible banned word anywhere", () => {
  it("is scanning real files", () => {
    expect(dashboardSources.length).toBeGreaterThan(100);
    expect(fixtures.length).toBeGreaterThan(30);
    expect(rendererSources.length).toBeGreaterThan(20);
  });

  it("the pending list only shrinks", () => {
    expect(Object.keys(PENDING_D57).length).toBeLessThanOrEqual(PENDING_D57_MAX);
  });

  /** Findings by repo-relative file, then split into the ones a pending entry covers and the ones nothing covers. A pending file of this kind must still have a finding. */
  const judge = (bad: { file: string; line: string }[], inScope: (file: string) => boolean): { unexpected: string[]; stale: string[] } => {
    const by = new Map<string, string[]>();
    for (const b of bad) by.set(b.file, [...(by.get(b.file) ?? []), b.line]);
    const unexpected = [...by].filter(([f]) => STRICT_WORDS || !(f in PENDING_D57)).flatMap(([, l]) => l);
    const stale = STRICT_WORDS ? [] : Object.keys(PENDING_D57).filter((f) => inScope(f) && !by.has(f));
    return { unexpected, stale };
  };
  const inDashboardSource = (f: string) => /^apps\/dashboard\/src\/.*\.(ts|tsx)$/.test(f);
  const inFixtures = (f: string) => /^apps\/dashboard\/src\/fixtures\/.*\.json$/.test(f);
  const inRenderer = (f: string) => f.startsWith("apps/desktop/src/renderer/");

  const sourceHits = (words: readonly string[]) => dashboardSources.flatMap((f) => words.flatMap((w) => scanSource(readFileSync(f, "utf8"), w).map((h) => ({ file: relative(repo, f), line: `${relative(repo, f)}:${h.line}  [${w}] ${h.text.slice(0, 90)}` }))));
  const fixtureHits = (words: readonly string[]) => fixtures.flatMap((f) => {
    let v: unknown;
    try { v = JSON.parse(readFileSync(f, "utf8")); } catch { return []; }
    return words.flatMap((w) => scanJson(v, w).map((h) => ({ file: relative(repo, f), line: `${relative(repo, f)} ${h.path}  [${w}] ${h.text.slice(0, 90)}` })));
  });
  const rendererHits = (words: readonly string[]) => rendererSources.flatMap((f) => words.flatMap((w) => scanSource(readFileSync(f, "utf8"), w).map((h) => ({ file: relative(repo, f), line: `${relative(repo, f)}:${h.line}  [${w}] ${h.text.slice(0, 90)}` }))));

  // "demo" has no pending list: it was cleaned on 7 Nov.
  it('no visible "demo" in the dashboard, its fixtures, the desktop renderer or the page', () => {
    for (const hits of [sourceHits(["demo"]), fixtureHits(["demo"]), rendererHits(["demo"])]) expect(hits.map((h) => h.line)).toEqual([]);
    const html = readFileSync(join(dashboard, "index.html"), "utf8").replace(/<!--[\s\S]*?-->/g, "");
    expect(/\bdemo\b/i.test(html)).toBe(false);
  });

  it('no visible "synthetic" or "simulated" in the dashboard\'s screens and components', () => {
    expect(judge(sourceHits(D57_WORDS), inDashboardSource)).toEqual({ unexpected: [], stale: [] });
  });
  it('no visible "synthetic" or "simulated" in the dashboard\'s fixtures (what the example data says on screen)', () => {
    expect(judge(fixtureHits(D57_WORDS), inFixtures)).toEqual({ unexpected: [], stale: [] });
  });
  it('no visible "synthetic" or "simulated" in the desktop renderer (the panel, the dock, the overlay)', () => {
    expect(judge(rendererHits(D57_WORDS), inRenderer)).toEqual({ unexpected: [], stale: [] });
  });
  it('no visible "synthetic" or "simulated" in the page itself', () => {
    const html = readFileSync(join(dashboard, "index.html"), "utf8").replace(/<!--[\s\S]*?-->/g, "");
    for (const w of D57_WORDS) expect(new RegExp(`\\b${w}\\b`, "i").test(html), w).toBe(false);
  });

  it("finds the new words the way it finds demo, and leaves the data enum alone", () => {
    expect(scanSource('t = "Synthetic firm";', "synthetic").length).toBe(1);
    expect(scanSource('t = "a simulated worker";', "simulated").length).toBe(1);
    expect(scanSource('o = { origin: "synthetic" }; p = "ana-synthetic-origin";', "synthetic")).toEqual([]);
    expect(scanJson({ meta: { origin: "synthetic", note: "Generated people." } }, "synthetic")).toEqual([]);
    expect(scanJson({ meta: { origin: "synthetic", note: "Synthetic personas." } }, "synthetic").map((h) => h.path)).toEqual(["$.meta.note"]);
  });
});
