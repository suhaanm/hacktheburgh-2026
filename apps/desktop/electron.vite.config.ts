import { resolve } from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'electron-vite'

export default defineConfig({
  main: {
    build: { rollupOptions: { input: { index: resolve(__dirname, 'src/main/index.ts') } } },
  },
  preload: {
    build: { rollupOptions: { input: { index: resolve(__dirname, 'src/preload/index.ts'), hud: resolve(__dirname, 'src/preload/hud.ts'), cue: resolve(__dirname, 'src/main/cue/preload.ts'), wakeCard: resolve(__dirname, 'src/main/wake/card-preload.ts') } } },
  },
  renderer: {
    root: resolve(__dirname, 'src/renderer'),
    plugins: [react()],
    build: {
      rollupOptions: {
        input: {
          dock: resolve(__dirname, 'src/renderer/dock/index.html'),
          overlay: resolve(__dirname, 'src/renderer/overlay/index.html'),
          toast: resolve(__dirname, 'src/renderer/toast/index.html'),
          hud: resolve(__dirname, 'src/renderer/hud/index.html'),
          cue: resolve(__dirname, 'src/renderer/cue/card/index.html'),
          heyCard: resolve(__dirname, 'src/renderer/hey-card/index.html'),
        },
      },
    },
  },
})
