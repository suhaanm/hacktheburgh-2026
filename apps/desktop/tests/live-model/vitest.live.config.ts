import { defineConfig } from 'vitest/config'

// Manual only (costs a few cents): the real Live model, with synthetic speech as the microphone and a fixture image as the frame.
//   cd apps/desktop && ../../scripts/heavy.sh uv run --env-file ../../.env npx vitest run --config tests/live-model/vitest.live.config.ts
export default defineConfig({
  root: process.cwd(),
  test: { include: ['tests/live-model/*.live.ts'], environment: 'node', testTimeout: 900_000, hookTimeout: 120_000, fileParallelism: false },
})
