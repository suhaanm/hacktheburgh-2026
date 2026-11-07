// Bundles the storyboard (and the real card page) into out/cue-harness with the repo's own Vite, for the screenshot script.
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { build } from 'vite'

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../..')
await build({
  root: path.join(repo, 'src/renderer/cue/harness'),
  base: './',
  logLevel: 'warn',
  plugins: [react()],
  build: {
    outDir: path.join(repo, 'out/cue-harness'),
    emptyOutDir: true,
    rollupOptions: { input: path.join(repo, 'src/renderer/cue/harness/index.html') },
  },
})
console.log('[cue-harness] built out/cue-harness')
