// The glyph on a node must stay readable at every strength, in both themes. A node's disc fades with strength (nodeOpacity); the glyph's ink does not.
// A live node (strength 0.4 and up) wears the token's `--on-*` ink, a lapsed one `--fg`. This reads the real tokens and blends the disc over the
// panel exactly as the canvas draws it, then asks for 3 to 1 (graphics, WCAG 1.4.11) at the faintest and the strongest end of each band.
// The graph's colours are the design system's semantic tokens, so this also holds if a token is retuned.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { LAPSED_BELOW, NODE_COLOUR, NODE_INK, nodeOpacity } from "./graph";
import { NODE_KINDS } from "./nodeIcons";

const tokens = readFileSync(fileURLToPath(new URL("../../../../packages/design/tokens.css", import.meta.url)), "utf8");

function block(sel: string): string {
  const i = tokens.indexOf(sel);
  const s = tokens.indexOf("{", i);
  let d = 1, j = s + 1;
  while (d) { if (tokens[j] === "{") d++; if (tokens[j] === "}") d--; j++; }
  return tokens.slice(s + 1, j - 1);
}
const parse = (b: string): Record<string, string> => { const o: Record<string, string> = {}; for (const m of b.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) o[m[1]] = m[2]; return o; };
const light = parse(block(":root {"));
const dark = { ...light, ...parse(block(':root[data-theme="dark"]')) };

const rgb = (h: string): [number, number, number] => { const n = parseInt(h.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; };
const lin = (c: number) => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
const lum = (c: [number, number, number]) => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
const ratio = (a: [number, number, number], b: [number, number, number]) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
const blend = (fg: [number, number, number], bg: [number, number, number], a: number): [number, number, number] => [0, 1, 2].map((i) => fg[i] * a + bg[i] * (1 - a)) as [number, number, number];
const tok = (theme: Record<string, string>, v: string) => rgb(theme[v.replace(/^var\(--|\)$/g, "")]);

describe("graph glyphs keep their contrast as nodes fade", () => {
  it("strength maps to opacity in two bands that do not overlap, and rises with strength inside each", () => {
    const steps = Array.from({ length: 101 }, (_, i) => i / 100);
    const live = steps.filter((s) => s >= LAPSED_BELOW).map(nodeOpacity);
    const lapsed = steps.filter((s) => s < LAPSED_BELOW).map(nodeOpacity);
    for (const band of [live, lapsed]) for (let i = 1; i < band.length; i++) expect(band[i]).toBeGreaterThanOrEqual(band[i - 1]);
    expect(Math.min(...live)).toBeGreaterThanOrEqual(0.75);
    expect(Math.max(...lapsed)).toBeLessThanOrEqual(0.5);
    expect(Math.min(...lapsed)).toBeGreaterThan(0.15);
    expect(nodeOpacity(1)).toBe(1);
  });
  for (const [name, theme] of [["light", light], ["dark", dark]] as const) {
    for (const kind of NODE_KINDS) {
      it(`${name}: the ${kind} glyph is at least 3 to 1 on its disc across both bands`, () => {
        const panel = tok(theme, "var(--panel)");
        const disc = tok(theme, NODE_COLOUR[kind]);
        const liveInk = tok(theme, NODE_INK[kind]);
        const lapsedInk = tok(theme, "var(--fg)");
        const liveLo = ratio(liveInk, blend(disc, panel, nodeOpacity(LAPSED_BELOW)));
        const liveHi = ratio(liveInk, blend(disc, panel, nodeOpacity(1)));
        const lapsedLo = ratio(lapsedInk, blend(disc, panel, nodeOpacity(0)));
        const lapsedHi = ratio(lapsedInk, blend(disc, panel, nodeOpacity(LAPSED_BELOW - 0.001)));
        for (const [label, v] of Object.entries({ liveLo, liveHi, lapsedLo, lapsedHi })) expect(v, `${name} ${kind} ${label}`).toBeGreaterThanOrEqual(3);
      });
    }
  }
  it("the four kind colours are the design system's semantic tokens, distinct in both themes", () => {
    for (const theme of [light, dark]) {
      const colours = NODE_KINDS.map((k) => theme[NODE_COLOUR[k].replace(/^var\(--|\)$/g, "")]);
      expect(colours.every((c) => /^#[0-9a-f]{6}$/i.test(c))).toBe(true);
      expect(new Set(colours).size).toBe(4);
    }
    // The values the artifact "Understudy Design System" prints for accent, novice, expert and good.
    expect([light.accent, light.novice, light.expert, light.good]).toEqual(["#0a7c78", "#4150c9", "#a55b07", "#177540"]);
    expect([dark.accent, dark.novice, dark.expert, dark.good]).toEqual(["#4fd1c5", "#8b98ff", "#f0a04b", "#5ad08a"]);
  });
});
