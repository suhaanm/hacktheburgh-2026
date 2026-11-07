import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    include: ['tests/**/*.test.ts', 'src/**/*.test.ts'],
    environment: 'node',
    testTimeout: 15_000,
    // Every test: a private UNDERSTUDY_DATA_DIR, and no request to the live dev services (:7700 :7710 :5173 :7801-7803).
    setupFiles: ['tests/setup/no-live-services.ts'],
  },
})
