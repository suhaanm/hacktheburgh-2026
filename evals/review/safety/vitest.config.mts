// Runs only the TypeScript reproducers in this folder against the desktop sources, hermetically (fakes only).
// From apps/desktop:  ./node_modules/.bin/vitest run --config ../../evals/review/safety/vitest.config.mts
export default {
  root: new URL('../../../', import.meta.url).pathname,
  cacheDir: 'evals/review/.vite-cache',
  test: { include: ['evals/review/safety/*.test.ts'], globals: true, environment: 'node', testTimeout: 15000 },
}
