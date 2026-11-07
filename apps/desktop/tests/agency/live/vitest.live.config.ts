import { defineConfig } from 'vitest/config'

// Manual only: npx vitest run --config tests/agency/live/vitest.live.config.ts
export default defineConfig({
  root: process.cwd(),
  test: { include: ['tests/agency/live/*.live.ts'], environment: 'node' },
})
