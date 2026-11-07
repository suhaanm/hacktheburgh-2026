import { describe, expect, it } from "vitest";
import { APP_NAME, BRAND_GLYPH_SVG, BUNDLE_ID, titled } from "./brand";

describe("the brand seam", () => {
  it("names the product Knack and builds titles from it", () => {
    expect(APP_NAME).toBe("Knack");
    expect(BUNDLE_ID).toBe("app.knack.desktop");
    expect(titled("Growth")).toBe("Growth · Knack");
  });

  it("holds the brand glyph file itself, in the text colour", () => {
    expect(BRAND_GLYPH_SVG).toContain("<svg");
    expect(BRAND_GLYPH_SVG).toContain("currentColor");
    expect(BRAND_GLYPH_SVG).toContain('aria-label="Knack"');
  });
});
