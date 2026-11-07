// A second dev server for checks and screenshots, on its own port and with its OWN dependency cache, so it can run beside the owner's
// server (:5173) without the two rewriting each other's pre-bundled dependencies (they share node_modules in a worktree).
// Usage (from apps/dashboard):  npx vite --config scripts/vite.qa.config.ts          (port 5193, or QA_PORT=5194)
// The proxy still points at the engine and agent ports of the environment; the checks refuse every non-GET request and can block both
// services entirely (check-copy.mjs --example).
import { fileURLToPath } from "node:url";
import { defineConfig, mergeConfig } from "vite";
import base from "../vite.config.ts";

const root = fileURLToPath(new URL("..", import.meta.url));

export default mergeConfig(
  base,
  defineConfig({
    root,
    cacheDir: fileURLToPath(new URL("../qa/.vite", import.meta.url)),
    server: { port: Number(process.env.QA_PORT ?? 5193), strictPort: true },
    preview: { port: Number(process.env.QA_PORT ?? 5193), strictPort: true },
  }),
);
