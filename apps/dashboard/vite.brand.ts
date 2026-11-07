/**
 * Puts the product name and the app icon into index.html from the brand seam (packages/design/brand/brand.json and the mark file it names),
 * so the tab title and favicon follow the brand files and nothing in index.html names the product by hand.
 *
 *   %APP_NAME%  ->  brand.name
 *   %APP_ICON%  ->  the mark (the ink tile with the disc and ring) as an SVG data URL, which the CSP of the packaged app allows (img-src data:)
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { Plugin } from "vite";

export interface BrandHtml { name: string; icon: string }

export function readBrandHtml(repoRoot: string): BrandHtml {
  const dir = join(repoRoot, "packages/design/brand");
  const brand = JSON.parse(readFileSync(join(dir, "brand.json"), "utf8")) as { name: string; files: { mark: string } };
  const mark = readFileSync(join(dir, brand.files.mark), "utf8").replace(/<!--[\s\S]*?-->/g, "").replace(/\s+/g, " ").trim();
  return { name: brand.name, icon: `data:image/svg+xml,${encodeURIComponent(mark)}` };
}

export const applyBrandToHtml = (html: string, b: BrandHtml): string => html.replace(/%APP_NAME%/g, b.name).replace(/%APP_ICON%/g, b.icon);

export function brandPlugin(repoRoot: string): Plugin {
  const b = readBrandHtml(repoRoot);
  return { name: "knack-brand", transformIndexHtml: { order: "pre", handler: (html: string) => applyBrandToHtml(html, b) } };
}
