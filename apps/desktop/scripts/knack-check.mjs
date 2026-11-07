#!/usr/bin/env node
// Hidden check of the Knack shell: builds the desktop app and the dashboard into a private folder, then runs src/main/knack/check-main.ts under Electron with
// stand-in services on private ports. Nothing is shown (activation policy "prohibited": no Dock icon, no menu bar, no window), nothing reads the desktop, and
// no real input is made. It never touches ports 7700, 7710 or 5173 or the repository's data folder.
//
//   cd apps/desktop && scripts/electron-lock.sh KNACK node scripts/knack-check.mjs [--out <folder for the pictures>]
//
// Writes knack-check.json and one PNG per page (the page's own pixels) into the folder, and exits non-zero when a check fails.
import { spawn, spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const desktop = path.resolve(here, '..')
const repo = path.resolve(desktop, '../..')
const argv = process.argv.slice(2)
const out = argv.includes('--out') ? path.resolve(argv[argv.indexOf('--out') + 1]) : fs.mkdtempSync(path.join(os.tmpdir(), 'knack-check-out-'))
// Inside apps/desktop (out/ is git-ignored), so the app's external packages (dotenv, zod) resolve from its node_modules as they do in the real build.
const work = path.join(desktop, 'out', 'knack-check')
fs.rmSync(work, { recursive: true, force: true })
fs.mkdirSync(work, { recursive: true })
const brand = JSON.parse(fs.readFileSync(path.join(repo, 'packages/design/brand/brand.json'), 'utf8'))

const run = (cmd, args, cwd) => {
  const r = spawnSync(cmd, args, { cwd, stdio: ['ignore', 'pipe', 'pipe'], encoding: 'utf8' })
  if (r.status !== 0) {
    console.error(`${cmd} ${args.join(' ')} failed:\n${(r.stdout ?? '').slice(-1500)}\n${(r.stderr ?? '').slice(-1500)}`)
    process.exit(1)
  }
}

console.log('building the desktop app (private folder)')
run(path.join(desktop, 'node_modules/.bin/electron-vite'), ['build', '--outDir', path.join(work, 'desktop')], desktop)
run(path.join(desktop, 'node_modules/.bin/electron-vite'), ['build', '--config', 'electron.vite.check.config.ts', '--outDir', path.join(work, 'desktop')], desktop)
console.log('building the dashboard (private folder)')
run(path.join(repo, 'apps/dashboard/node_modules/.bin/vite'), ['build', '--outDir', path.join(work, 'dashboard'), '--emptyOutDir'], path.join(repo, 'apps/dashboard'))

const electron = (await import('electron')).default
const child = spawn(electron, [path.join(work, 'desktop/main/knack-check.js')], {
  cwd: desktop,
  env: { ...process.env, KNACK_CHECK_OUT: out, KNACK_CHECK_DIST: path.join(work, 'dashboard'), KNACK_CHECK_GLYPH: path.join(repo, 'packages/design/brand', brand.files.glyph), ELECTRON_ENABLE_LOGGING: '0' },
  stdio: ['ignore', 'inherit', 'pipe'],
})
let stderr = ''
child.stderr.on('data', (d) => (stderr += d))
const timer = setTimeout(() => child.kill('SIGKILL'), 120_000)
child.on('exit', (code) => {
  clearTimeout(timer)
  if (code !== 0 && stderr.trim()) console.error(stderr.split('\n').filter((l) => !/DeprecationWarning|ERROR:.*(gpu|viz|dbus)/i.test(l)).slice(-12).join('\n'))
  fs.rmSync(work, { recursive: true, force: true })
  console.log(`pictures and results: ${out}`)
  process.exit(code ?? 1)
})
