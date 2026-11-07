import { defineConfig } from 'vitest/config'

// Manual only: npm run probe:models
export default defineConfig({
  root: process.cwd(),
  test: { include: ['tests/model-port/*.live.ts'], environment: 'node' },
})
