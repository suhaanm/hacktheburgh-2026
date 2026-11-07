import { defineConfig } from 'vitest/config'

// Accuracy harness only (`npm run e2e -- --accuracy`). Files are *.acc.ts.
export default defineConfig({
  test: { include: ['tests/e2e/**/*.acc.ts'], environment: 'node', testTimeout: 120_000, hookTimeout: 60_000, fileParallelism: false },
})
