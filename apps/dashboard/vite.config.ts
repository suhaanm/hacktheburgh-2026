import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";
import { proxyTable, tokenProxyPlugin } from "./vite.proxy.ts";
import { brandPlugin } from "./vite.brand.ts";

const repoRoot = fileURLToPath(new URL("../..", import.meta.url));

// Dashboard dev server: port 5173 only. The shared design package lives outside
// this folder, so the dev server is allowed to read the repo root.
// The page talks to /engine and /agent on its own origin; vite.proxy.ts forwards them and adds the per-boot token.
export default defineConfig({
  plugins: [react(), brandPlugin(repoRoot), tokenProxyPlugin(process.env, repoRoot)],
  server: { host: "127.0.0.1", port: 5173, strictPort: true, fs: { allow: [repoRoot] }, proxy: proxyTable(process.env) },
  preview: { host: "127.0.0.1", port: 5173, strictPort: true, proxy: proxyTable(process.env) },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
