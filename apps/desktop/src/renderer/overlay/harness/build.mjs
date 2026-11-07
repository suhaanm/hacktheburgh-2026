// Bundles demo.html (+ React) into out/overlay-demo with the repo's own Vite, for the headless harness.
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { build } from 'vite'

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..')
await build({
  root: path.join(repo, 'src/renderer/overlay'),
  base: './',
  logLevel: 'warn',
  plugins: [react()],
  build: {
    outDir: path.join(repo, 'out/overlay-demo'),
    emptyOutDir: true,
    rollupOptions: { input: path.join(repo, 'src/renderer/overlay/demo.html') },
  },
})
console.log('[overlay-harness] built out/overlay-demo')
