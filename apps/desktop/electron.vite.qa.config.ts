import { resolve } from 'node:path'
import { defineConfig } from 'electron-vite'

// The hidden check of the Knack shell (scripts/knack-qa.mjs) is its own main entry, built by itself into the folder the app was just built into. It is not an
// extra entry of electron.vite.config.ts on purpose: a second entry makes the bundler move shared code into chunks, and code that finds its preload and renderer
// files relative to __dirname would then look in the wrong folder.
export default defineConfig({
  main: {
    build: { emptyOutDir: false, rollupOptions: { input: { 'knack-qa': resolve(__dirname, 'src/main/knack/qa-main.ts') } } },
  },
})
