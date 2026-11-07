import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { APP_NAME, BRAND_GLYPH_SVG, BUNDLE_ID, titled } from "./brand";
import { applyBrandToHtml, readBrandHtml } from "../vite.brand";

const repoRoot = fileURLToPath(new URL("../../..", import.meta.url));

describe("the brand seam", () => {
  it("names the product Knack and builds titles from it", () => {
    expect(APP_NAME).toBe("Knack");
    expect(BUNDLE_ID).toBe("app.knack.desktop");
    expect(titled("Growth")).toBe("Growth · Knack");
  });

  it("draws the brand glyph file itself, in the text colour", () => {
    expect(BRAND_GLYPH_SVG).toContain("<svg");
    expect(BRAND_GLYPH_SVG).toContain("currentColor");
    expect(BRAND_GLYPH_SVG).toContain('aria-label="Knack"');
  });

  it("puts the name and the icon into index.html, so the page names the product only through the brand files", () => {
    const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
    expect(html).toContain("%APP_NAME%");
    expect(html).not.toMatch(/Understudy|Alongside/);
    const out = applyBrandToHtml(html, readBrandHtml(repoRoot));
    expect(out).toContain("<title>Knack</title>");
    expect(out).toMatch(/rel="icon" type="image\/svg\+xml" href="data:image\/svg\+xml,%3Csvg/);
    expect(out).not.toContain("%APP_");
  });
});
