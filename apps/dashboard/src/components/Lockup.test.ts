// The Knack lockup: sizes from the brand sheet, minimums, the word, and the accessible names. Static markup, no DOM needed.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { GLYPH_MIN, Glyph, LOCKUP_SIZES, Lockup, WORD_MIN, wordSize } from "./Lockup";

const html = (el: ReturnType<typeof createElement>) => renderToStaticMarkup(el);

describe("Lockup", () => {
  it("draws the glyph and the word Knack, never capitals in the markup", () => {
    const out = html(createElement(Lockup, {}));
    expect(out).toContain(">Knack<");
    expect(out).toContain("lockup__word");
    expect(out).not.toMatch(/KNACK/);
    expect(out).not.toMatch(/Understudy/i);
  });

  it("uses the sizes of the brand sheet: sidebar glyph 20 px with the word at 17.5 px", () => {
    expect(LOCKUP_SIZES.sidebar).toBe(20);
    expect(LOCKUP_SIZES.firstRun).toBe(56);
    expect(LOCKUP_SIZES.pill).toBe(14);
    expect(LOCKUP_SIZES.favicon).toBe(16);
    expect(wordSize(20)).toBe(17.5);
    const out = html(createElement(Lockup, {}));
    expect(out).toContain("--lockup-glyph:20px");
    expect(out).toContain("--lockup-word:17.5px");
  });

  it("keeps the minimums: glyph 12 px, word 14 px", () => {
    expect(GLYPH_MIN).toBe(12);
    expect(WORD_MIN).toBe(14);
    expect(wordSize(12)).toBe(14);
    const out = html(createElement(Lockup, { size: 4 }));
    expect(out).toContain("--lockup-glyph:12px");
    expect(out).toContain('width="12"');
  });

  it("the glyph box is 78 by 72, so the height follows the width", () => {
    expect(html(createElement(Glyph, { size: 78 }))).toContain('height="72"');
    expect(html(createElement(Glyph, { size: 56 }))).toContain('viewBox="28 30 78 72"');
  });

  it("a link names its destination; the glyph inside is decorative", () => {
    const out = html(createElement(Lockup, { href: "#/home", label: "Knack home" }));
    expect(out).toMatch(/^<a /);
    expect(out).toContain('aria-label="Knack home"');
    expect(out).toContain('aria-hidden="true"');
  });

  it("wordless draws the glyph alone and names it Knack", () => {
    const out = html(createElement(Lockup, { wordless: true, size: "pill" }));
    expect(out).not.toContain("lockup__word");
    expect(out).toContain('role="img"');
    expect(out).toContain('aria-label="Knack"');
  });

  it("mono tone follows currentColor", () => {
    expect(html(createElement(Glyph, { tone: "mono" }))).toContain("glyph--mono");
    expect(html(createElement(Glyph, {}))).toContain("glyph--ui");
  });
});

describe("brand files", () => {
  const dir = fileURLToPath(new URL("../../../../packages/design/brand/", import.meta.url));
  it("are named Knack and carry the Knack label", () => {
    const svgs = readdirSync(dir).filter((f) => f.endsWith(".svg")).sort();
    expect(svgs).toEqual(["knack-glyph.svg", "knack-mark.svg", "knack-tray-template.svg"]);
    for (const f of svgs) expect(readFileSync(`${dir}${f}`, "utf8")).toContain('aria-label="Knack"');
  });
});
