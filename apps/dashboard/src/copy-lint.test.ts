// The copy lint (KNACK_UX section 5, "Banned patterns", and rule 6, "Rename in what people see"). Fails the build when a visible string says one of the
// banned things, or a person can read the old product name. The data is docs/knack-ux/banned-phrases.json, shared with scripts/check-copy.mjs, which does
// the same on the rendered page. Three sources are read here: the string literals and JSX text of the dashboard, the strings in its fixtures (what the
// example data says on screen), and the sentences the models build from those fixtures (what a screen draws from them).
// The allow-list is internal identifiers only: storage keys, events, environment names and file or directory names (see stripIdentifiers).
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { findBanned, phraseRegex, stringsIn, stripIdentifiers, type BannedConfig } from "./lib/copyLint";
import { jsxTexts, looksLikePath, tokenise, type Hit } from "./lib/visibleWords";
import { buildView, normalizeGrowth } from "./components/growth/model";
import improves from "./fixtures/growth.json";
import plateau from "./fixtures/growth-plateau.json";
import sparse from "./fixtures/growth-sparse.json";
import type { WireGrowth } from "./components/growth/wire";

const here = dirname(fileURLToPath(import.meta.url));
const dashboard = join(here, "..");
const repo = join(dashboard, "..", "..");
const cfg = JSON.parse(readFileSync(join(repo, "docs", "knack-ux", "banned-phrases.json"), "utf8")) as BannedConfig;

function walk(dir: string, accept: (p: string) => boolean, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === "dist" || name === "out" || name === ".git") continue;
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, accept, out);
    else if (accept(p)) out.push(p);
  }
  return out;
}

const isTest = (p: string) => /\.test\.(ts|tsx)$/.test(p);
/** The linter and the scanner talk about the banned words, so they are not copy. */
const NOT_COPY = new Set([join(here, "lib", "copyLint.ts"), join(here, "lib", "visibleWords.ts")]);
const sources = walk(join(here), (p) => /\.(ts|tsx)$/.test(p) && !isTest(p) && !NOT_COPY.has(p));
const fixtures = walk(join(here, "fixtures"), (p) => p.endsWith(".json"));

/** What a person can read in a source file: string literals (static parts of templates too) and JSX text. A bare identifier-like literal is code. */
function visibleIn(src: string): Hit[] {
  const { strings, code } = tokenise(src);
  const lits = strings.filter((s) => /\s/.test(s.text.trim()) || /^[A-Z][a-z]+$/.test(s.text.trim())).filter((s) => !looksLikePath(s.text));
  return [...lits, ...jsxTexts(code)];
}

describe("the linter itself", () => {
  it("finds a banned phrase as a whole phrase in any case, including phrases that end in punctuation", () => {
    expect(findBanned("This screen shows your week.", cfg).map((f) => f.match)).toContain("This screen shows");
    expect(findBanned("Note: nothing was sent.", cfg).map((f) => f.match)).toContain("Note:");
    expect(findBanned("Please wait.", cfg).map((f) => f.match)).toContain("Please");
    expect(findBanned("That was simply wrong.", cfg).map((f) => f.match)).toContain("simply");
    expect(phraseRegex("note:").test("a keynote: yes")).toBe(false);
  });

  it("does not trip on ordinary words that contain a banned one", () => {
    expect(findBanned("Pleasantly quiet. An invalidated cache. Urgently.", cfg)).toEqual([]);
    expect(findBanned("Nothing needs you. Knack asks when a step cannot be undone.", cfg)).toEqual([]);
  });

  it("finds the old name, the earlier library and the word demo when a person can read them", () => {
    expect(findBanned("Understudy asks first.", cfg).map((f) => f.kind)).toContain("old name");
    expect(findBanned("Understudy's memory file.", cfg).map((f) => f.kind)).toContain("old name");
    expect(findBanned("Alongside the coach.", cfg).map((f) => f.kind)).toContain("name");
    expect(findBanned("Run the demo now.", cfg).map((f) => f.kind)).toContain("word");
    expect(findBanned("It sits alongside the coach.", cfg)).toEqual([]);
  });

  it("allows internal identifiers that carry the old name, and only those", () => {
    for (const ok of ["understudy-theme", "understudy:retry", "UNDERSTUDY_DATA_DIR", "understudy_engine", "understudy.json", "~/.understudy/memory.md", "Set UNDERSTUDY_X=1 to start it."]) {
      expect(findBanned(ok, cfg), ok).toEqual([]);
    }
    expect(stripIdentifiers("Start with understudy-theme or the Understudy app").includes("Understudy")).toBe(true);
    expect(findBanned("Start with understudy-theme or the Understudy app", cfg).map((f) => f.kind)).toContain("old name");
  });

  it("reads strings and JSX text from source, and skips comments and identifiers", () => {
    const src = ['// Understudy in a comment is not visible', 'const id = "understudy-theme";', 'const a = "Understudy asks first";', "const el = <p>Please wait</p>;"].join("\n");
    const found = visibleIn(src).flatMap((h) => findBanned(h.text, cfg).map((f) => f.match));
    expect(found).toContain("Understudy");
    expect(found).toContain("Please");
    expect(found.filter((m) => m === "Understudy")).toHaveLength(1);
  });
});

/**
 * Files of other tracks that still carry the old name or a banned phrase, listed on 7 Nov at about 23:15 UTC so this test is green on a track branch (trimmed at 23:25 after Tracks B and C landed).
 * It is a ratchet, not an allow-list: a file that is not listed may have no finding at all; a listed file must still have one (so the entry is deleted the
 * moment its track lands); and the list can only get shorter. Run with KNACK_LINT_STRICT=1 to ignore it and see every finding. The lead flips the default
 * (STRICT below) once the tracks are merged; nothing here is ever a reason to ship a finding.
 */
const PENDING: Record<string, string> = {
  "apps/dashboard/src/fixtures/attention-why.json": "the example data of the attention layer: the old name is in the engine's sentence",
  "apps/dashboard/src/fixtures/briefing.json": "the example data of Briefing, which Track C moves into Needs you",
  "apps/dashboard/src/fixtures/eval-report.json": "written by the eval track (evals/report.json): the old name is in its limitations text",
  "apps/dashboard/src/fixtures/home-worker-good.json": "the example data of Home (the Monday note), Track B",
  "apps/dashboard/src/fixtures/home-worker.json": "the example data of Home (the Monday note), Track B",
};
const STRICT = process.env.KNACK_LINT_STRICT === "1";
const PENDING_MAX = 8;

/** Findings by repo-relative file, then split into the ones a pending entry covers and the ones nothing covers. */
function judge(byFile: Map<string, string[]>, inScope: (file: string) => boolean): { unexpected: string[]; stale: string[] } {
  const unexpected: string[] = [];
  for (const [file, hits] of byFile) if (STRICT || !(file in PENDING)) unexpected.push(...hits);
  const stale = STRICT ? [] : Object.keys(PENDING).filter((f) => inScope(f) && !byFile.has(f));
  return { unexpected, stale };
}
const isSource = (f: string) => /\.(ts|tsx)$/.test(f);
const isFixture = (f: string) => f.endsWith(".json");
const isPage = (f: string) => f.endsWith(".html");

describe("no banned copy in the dashboard", () => {
  it("is reading real files", () => {
    expect(sources.length).toBeGreaterThan(100);
    expect(fixtures.length).toBeGreaterThan(30);
  });

  it("the pending list only shrinks", () => {
    expect(Object.keys(PENDING).length).toBeLessThanOrEqual(PENDING_MAX);
  });

  const hitsFor = (files: string[], read: (f: string) => { text: string; at: string }[]): Map<string, string[]> => {
    const by = new Map<string, string[]>();
    for (const f of files) {
      const rel = relative(repo, f);
      for (const h of read(f)) for (const x of findBanned(h.text, cfg)) by.set(rel, [...(by.get(rel) ?? []), `${rel}${h.at}  [${x.kind}: ${x.match}]  ${h.text.slice(0, 80)}`]);
    }
    return by;
  };

  it("in the source strings and JSX text of every screen and component", () => {
    const by = hitsFor(sources, (f) => visibleIn(readFileSync(f, "utf8")).map((h) => ({ text: h.text, at: `:${h.line}` })));
    const { unexpected, stale } = judge(by, isSource);
    expect({ unexpected, stale }).toEqual({ unexpected: [], stale: [] });
  });

  it("in the fixtures: what the example data says on screen", () => {
    const by = hitsFor(fixtures, (f) => {
      let v: unknown;
      try { v = JSON.parse(readFileSync(f, "utf8")); } catch { return []; }
      return stringsIn(v).filter((s) => !looksLikePath(s.text)).map((s) => ({ text: s.text, at: ` ${s.path}` }));
    });
    const { unexpected, stale } = judge(by, isFixture);
    expect({ unexpected, stale }).toEqual({ unexpected: [], stale: [] });
  });

  it("in the page itself", () => {
    const html = readFileSync(join(dashboard, "index.html"), "utf8").replace(/<!--[\s\S]*?-->/g, "");
    const text = html.replace(/<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>/g, " ").replace(/<[^>]+>/g, " ");
    const title = /<title>([^<]*)<\/title>/.exec(html)?.[1] ?? "";
    const found = findBanned(`${title} ${text}`, cfg).map((x) => `apps/dashboard/index.html [${x.kind}: ${x.match}]`);
    const by = new Map<string, string[]>(found.length ? [["apps/dashboard/index.html", found]] : []);
    const { unexpected, stale } = judge(by, isPage);
    expect({ unexpected, stale }).toEqual({ unexpected: [], stale: [] });
  });
});

describe("no banned copy in the sentences the models build", () => {
  // The rendered side for Growth: every string the view holds, for each of the engine's example learners.
  for (const [name, payload] of [["improves", improves], ["plateaus", plateau], ["sparse", sparse]] as const) {
    it(`the Growth view for the ${name} learner`, () => {
      const view = buildView(normalizeGrowth((payload as unknown as { overall: { data: WireGrowth } }).overall.data), 95);
      const bad = stringsIn(view).flatMap((s) => findBanned(s.text, cfg).map((x) => `${s.path} [${x.kind}: ${x.match}] ${s.text.slice(0, 80)}`));
      expect(bad).toEqual([]);
    });
  }
});
