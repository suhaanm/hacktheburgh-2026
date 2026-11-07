// Guards on the shared design system (packages/design): token names that code depends on are never renamed away, the pairs that carry text
// or a graphic keep their contrast in both themes, and no gradient or glow creeps into a component. Docs: docs/DESIGN_DIFF.md.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const dir = fileURLToPath(new URL("../../../packages/design/", import.meta.url));
const tokens = readFileSync(`${dir}tokens.css`, "utf8");
const components = readFileSync(`${dir}components.css`, "utf8");

function block(sel: string): string {
  const i = tokens.indexOf(sel);
  const s = tokens.indexOf("{", i);
  let d = 1;
  let j = s + 1;
  while (d) { if (tokens[j] === "{") d++; if (tokens[j] === "}") d--; j++; }
  return tokens.slice(s + 1, j - 1);
}
const parse = (b: string): Record<string, string> => {
  const o: Record<string, string> = {};
  for (const m of b.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) o[m[1]] = m[2];
  return o;
};
const light = parse(block(":root {"));
const dark = { ...light, ...parse(block(':root[data-theme="dark"]')) };

const lin = (c: number) => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
const lum = (h: string) => { const n = parseInt(h.slice(1), 16); return 0.2126 * lin((n >> 16) & 255) + 0.7152 * lin((n >> 8) & 255) + 0.0722 * lin(n & 255); };
const ratio = (a: string, b: string) => { const x = lum(a); const y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };

// Names used by the dashboard, the desktop mirror and the preview page. Add to this list; never remove from it.
const NAMES = [
  "bg", "panel", "sunk", "fg", "muted", "line", "line-strong", "control-line", "accent", "accent-strong", "on-accent", "expert", "on-expert", "novice", "on-novice",
  "good", "on-good", "warn", "bad", "on-bad", "accent-soft", "expert-soft", "novice-soft", "good-soft", "warn-soft", "bad-soft", "seq-0", "seq-1", "seq-2", "seq-3", "seq-4",
  "node-routine", "node-skill", "node-memory",
  "font-display", "font-body", "font-mono", "text-xs", "text-sm", "text-md", "text-lg", "text-xl", "text-2xl", "text-3xl", "text-4xl", "lh-tight", "lh-snug", "lh-body",
  "tracking-display", "tracking-label", "measure", "measure-short", "space-1", "space-2", "space-3", "space-4", "space-5", "space-6", "space-7", "space-8", "space-9", "space-10", "space-11", "space-12",
  "gutter", "gutter-wide", "radius-1", "radius-2", "radius-3", "radius-pill", "hair", "hair-strong", "ring-w", "ring-offset", "focus", "elev-0", "elev-1", "elev-2",
  "ease-out", "ease-in-out", "ease-land", "ease-fade", "dur-instant", "dur-fast", "dur-base", "dur-arrive", "dur-land", "dur-fade", "dur-pop", "z-panel", "z-toast", "z-hint", "z-kill", "z-overlay",
  // Knack (KNACK_UX section 6)
  "sidebar-w", "content-read", "content-wide", "page-pad-x", "page-pad-top", "row-h", "control-h", "table-row-h", "pill-h", "bottombar-h", "corner-w", "corner-inset", "text-corner",
  "lh-hero", "lh-title", "lh-row", "lh-read", "weight-regular", "weight-strong",
];

describe("design tokens", () => {
  it("keeps every token name that code depends on", () => {
    const missing = NAMES.filter((n) => !new RegExp(`--${n}:`).test(tokens));
    expect(missing).toEqual([]);
  });

  it("has the Knack layout and density tokens with the values of KNACK_UX section 6", () => {
    const get = (n: string) => new RegExp(`--${n}:\\s*([^;]+);`).exec(tokens)?.[1].trim();
    expect({
      sidebar: get("sidebar-w"), read: get("content-read"), wide: get("content-wide"), row: get("row-h"), control: get("control-h"), pill: get("pill-h"),
      corner: get("corner-w"), inset: get("corner-inset"), corner13: get("text-corner"), regular: get("weight-regular"), strong: get("weight-strong"),
    }).toEqual({ sidebar: "208px", read: "720px", wide: "1080px", row: "44px", control: "32px", pill: "32px", corner: "340px", inset: "16px", corner13: "0.8125rem", regular: "400", strong: "600" });
  });

  it("the motion durations are the documented ones", () => {
    const get = (n: string) => new RegExp(`--${n}:\\s*(\\d+)ms`).exec(tokens)?.[1];
    expect([get("dur-instant"), get("dur-fast"), get("dur-base"), get("dur-arrive"), get("dur-land"), get("dur-fade")]).toEqual(["80", "140", "240", "360", "560", "900"]);
  });

  // [foreground, background, minimum ratio]: text pairs 4.5, graphics 3.
  const PAIRS: [string, string, number][] = [
    ["fg", "bg", 4.5], ["fg", "panel", 4.5], ["muted", "bg", 4.5], ["muted", "panel", 4.5], ["muted", "sunk", 4.5], ["accent", "panel", 4.5], ["bad", "panel", 4.5], ["good", "panel", 4.5], ["warn", "panel", 4.5],
    ["on-accent", "accent", 4.5], ["on-bad", "bad", 4.5], ["fg", "accent-soft", 4.5], ["fg", "bad-soft", 4.5], ["fg", "warn-soft", 4.5], ["fg", "good-soft", 4.5], ["control-line", "panel", 3],
    // notice and insight icons on their tints, graph glyphs on their fills (graphics: 3)
    ["accent", "accent-soft", 3], ["bad", "bad-soft", 3], ["good", "good-soft", 3], ["warn", "warn-soft", 3], ["fg", "sunk", 3],
    ["on-accent", "node-routine", 3], ["on-novice", "node-skill", 3], ["on-expert", "node-memory", 3], ["bg", "fg", 3],
  ];
  for (const [name, theme] of [["light", light], ["dark", dark]] as const) {
    it(`${name}: text and graphic pairs keep their contrast`, () => {
      const bad = PAIRS.filter(([a, b, min]) => ratio(theme[a], theme[b]) < min).map(([a, b, min]) => `${a} on ${b} ${ratio(theme[a], theme[b]).toFixed(2)} < ${min}`);
      expect(bad).toEqual([]);
    });
  }

  it("defines the graph colours in both themes and the dark overrides are present", () => {
    for (const k of ["node-routine", "node-skill", "node-memory"]) {
      expect(light[k]).toMatch(/^#/);
      expect(dark[k]).not.toBe(light[k]);
    }
  });
});

describe("components", () => {
  const css = components.replace(/\/\*[\s\S]*?\*\//g, "");
  it("has the Knack components of section 6", () => {
    for (const c of [".lockup", ".glyph", ".icon", ".column", ".screenhead", ".hero-insight", ".navitem", ".listrow", ".listrows", ".confirm-row", ".inline-banner", ".status-line", ".stop-button", ".sheet", ".crumb", ".keyfigure"]) {
      expect(css, c).toContain(c);
    }
  });
  it("uses two weights only: 400 and 600, no 500 and no 700", () => {
    expect([...css.matchAll(/font(?:-weight)?:\s*(?:[a-z-]+\s+)?(500|700|bold)\b/g)].map((m) => m[0])).toEqual([]);
  });
  it("the origin badge is sentence case in the body face, not tracked capitals", () => {
    const rule = /\.pill--origin \{[^}]*\}/.exec(css)?.[0] ?? "";
    expect(rule).toContain("text-transform: none");
    expect(rule).toContain("var(--font-body)");
  });
  it("the empty-state mark is retired outside errors", () => {
    expect(css).toMatch(/\.state__mark \{ display: none; \}/);
  });
  it("has no glow and no decorative gradient (hatching and the consent half-fill glyph are encodings)", () => {
    const grad = [...css.matchAll(/[a-z-]*gradient\([^;{}]*\)/g)].map((m) => m[0]);
    // Allowed: select caret, consent glyphs, hatch patterns, the radio dot, and the hold-to-approve fill (none uses a colour ramp).
    const decorative = grad.filter((g) => /var\(--(accent|bg|panel)\) 0%,|to (right|bottom|top)/.test(g));
    expect(decorative).toEqual([]);
    expect(css).not.toMatch(/\bglow\b|text-shadow/i);
  });

  it("defines the Hint, with a focus ring and a touch target", () => {
    expect(css).toMatch(/\.hint__btn/);
    expect(css).toMatch(/\.hint__btn:focus-visible/);
    expect(css).toMatch(/@media \(pointer: coarse\)\s*\{\s*\.hint__btn\s*\{\s*width: 44px/);
    expect(css).toMatch(/\.hint__pop\s*\{[^}]*z-index: var\(--z-hint\)/);
  });

  it("zeroes the new animations under reduced motion", () => {
    expect(components).toMatch(/prefers-reduced-motion: reduce[\s\S]*\.alert--live[\s\S]*animation: none/);
  });

  it("uses no hard-coded hex colour in the new components", () => {
    const from = css.indexOf(".hint {");
    const hex = css.slice(from).match(/#[0-9a-fA-F]{3,8}\b/g) ?? [];
    expect(hex).toEqual([]);
  });
});
