import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

const repoRoot = fileURLToPath(new URL("../..", import.meta.url));

// Dashboard dev server: port 5173 only. The shared design package lives outside
// this folder, so the dev server is allowed to read the repo root.
export default defineConfig({
  plugins: [react()],
  server: { host: "127.0.0.1", port: 5173, strictPort: true, fs: { allow: [repoRoot] } },
  preview: { host: "127.0.0.1", port: 5173, strictPort: true },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
