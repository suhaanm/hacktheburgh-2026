// Proves that the Cue entries bundle: the real electron.vite.config.ts plus the three lines Cue needs, written to out/cue-check (not out/).
// Run: npx electron-vite build -c src/renderer/cue/harness/electron.vite.check.config.ts
// The three additions for the real config are marked CUE below.
import { resolve } from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'electron-vite'

const app = resolve(__dirname, '../../../..')

export default defineConfig({
  main: { build: { outDir: resolve(app, 'out/cue-check/main'), rollupOptions: { input: { index: resolve(app, 'src/main/index.ts'), cue: resolve(app, 'src/main/cue/index.ts') } } } }, // (the cue entry only proves it bundles; main/index.ts imports it itself)
  preload: {
    build: {
      outDir: resolve(app, 'out/cue-check/preload'),
      rollupOptions: {
        input: {
          index: resolve(app, 'src/preload/index.ts'),
          hud: resolve(app, 'src/preload/hud.ts'),
          cue: resolve(app, 'src/main/cue/preload.ts'), // CUE (1 of 2): the panel window's preload, built to out/preload/cue.js
        },
      },
    },
  },
  renderer: {
    root: resolve(app, 'src/renderer'),
    plugins: [react()],
    build: {
      outDir: resolve(app, 'out/cue-check/renderer'),
      rollupOptions: {
        input: {
          dock: resolve(app, 'src/renderer/dock/index.html'),
          overlay: resolve(app, 'src/renderer/overlay/index.html'),
          toast: resolve(app, 'src/renderer/toast/index.html'),
          hud: resolve(app, 'src/renderer/hud/index.html'),
          cue: resolve(app, 'src/renderer/cue/card/index.html'), // CUE (2 of 2): the panel page, built to out/renderer/cue/card/index.html
        },
      },
    },
  },
})
