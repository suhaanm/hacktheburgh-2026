// The product name and brand files, from one place: packages/design/brand/brand.json (the desktop app reads the same file through
// apps/desktop/src/shared/brand.ts). Anything the person can read that names the product comes from here.
import brand from "../../../packages/design/brand/brand.json";
// The glyph is the brand file itself (currentColor), drawn inline: replace knack-glyph.svg and the wordmark follows.
import glyphSvg from "../../../packages/design/brand/knack-glyph.svg?raw";

export const APP_NAME: string = brand.name;
export const BUNDLE_ID: string = brand.bundleId;
export const BRAND_GLYPH_SVG: string = glyphSvg;

/** "<label> · Knack": the tab and window title shape. */
export const titled = (label: string): string => `${label} · ${APP_NAME}`;
