// Bundles the extension into dist/ (load that folder unpacked in Chrome).
import { build } from "esbuild";
import { cpSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const dist = join(root, "dist");
rmSync(dist, { recursive: true, force: true });
mkdirSync(dist, { recursive: true });

await build({
  entryPoints: {
    content: join(root, "src/content/main.ts"),
    worker: join(root, "src/background/worker.ts"),
    popup: join(root, "src/popup/popup.ts"),
  },
  outdir: dist,
  bundle: true,
  format: "iife",
  target: "chrome116",
  platform: "browser",
  sourcemap: false,
  minify: false,
  legalComments: "none",
  logLevel: "info",
});
cpSync(join(root, "manifest.json"), join(dist, "manifest.json"));
cpSync(join(root, "popup.html"), join(dist, "popup.html"));
console.log("built", dist);
