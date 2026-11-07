import { defineConfig } from 'vitest/config'

// Separate from the default config so `npm test` never launches Electron. Files are *.e2e.ts.
export default defineConfig({
  test: {
    include: ['tests/e2e/**/*.e2e.ts'],
    environment: 'node',
    testTimeout: 60_000,
    hookTimeout: 30_000,
    // One app instance, shared state: scenarios run in file order, one at a time.
    fileParallelism: false,
    sequence: { concurrent: false },
  },
})
