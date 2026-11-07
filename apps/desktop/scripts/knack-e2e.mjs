#!/usr/bin/env node
// Hidden end-to-end run of the REAL app (src/main/index.ts, built) with the Knack shell on: nothing is shown (KNACK_HIDDEN=1: activation policy "prohibited", no Dock icon,
// no menu bar item, windows never shown), no global shortcut is taken, no permission is asked, and no real click, keystroke or capture is made. The services are stand-ins on
// private ports with a private data folder (never 7700, 7710, 5173 or the repository's data); voice, awareness and Cue are switched off. It then runs scripts/shell-smoke.mjs against
// the app's debug server, so the whole path (index.ts, the shell, the machine, the HUD, the debug hooks) is exercised.
//
//   cd apps/desktop && scripts/electron-lock.sh KNACK node scripts/knack-e2e.mjs
import { spawn, spawnSync } from 'node:child_process'
import fs from 'node:fs'
import http from 'node:http'
import net from 'node:net'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const desktop = path.resolve(here, '..')
const repo = path.resolve(desktop, '../..')
const work = path.join(desktop, 'out', 'knack-e2e')
fs.rmSync(work, { recursive: true, force: true })
fs.mkdirSync(work, { recursive: true })

const run = (cmd, args, cwd) => {
  const r = spawnSync(cmd, args, { cwd, stdio: ['ignore', 'pipe', 'pipe'], encoding: 'utf8' })
  if (r.status !== 0) {
    console.error(`${cmd} ${args.join(' ')} failed:\n${(r.stdout ?? '').slice(-1500)}\n${(r.stderr ?? '').slice(-1500)}`)
    process.exit(1)
  }
}
const freePort = () =>
  new Promise((resolve) => {
    const s = net.createServer()
    s.listen(0, '127.0.0.1', () => {
      const { port } = s.address()
      s.close(() => resolve(port))
    })
  })

console.log('building the app and the dashboard into private folders')
run(path.join(desktop, 'node_modules/.bin/electron-vite'), ['build', '--outDir', path.join(work, 'app')], desktop)
run(path.join(repo, 'apps/dashboard/node_modules/.bin/vite'), ['build', '--outDir', path.join(work, 'dashboard'), '--emptyOutDir'], path.join(repo, 'apps/dashboard'))

const data = path.join(work, 'data')
fs.mkdirSync(data, { recursive: true })
fs.writeFileSync(path.join(data, '.token'), 'e2e-token-0123456789abcdef')
const fake = (health) =>
  new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      res.setHeader('content-type', 'application/json')
      if (req.url === '/health') return res.end(JSON.stringify(health))
      if (req.url?.startsWith('/agents/runs')) return res.end('[]')
      res.statusCode = 404
      res.end('{"error":{"code":"not_found","message":"stand-in"}}')
    })
    server.listen(0, '127.0.0.1', () => resolve({ server, port: server.address().port }))
  })
const engine = await fake({ ok: true, mock: true })
const agent = await fake({ ok: true, mock: true, supervisor: { state: 'idle', generation: 1 } })
const debugPort = await freePort()
const extPort = await freePort()

const env = {
  ...process.env,
  KNACK_HIDDEN: '1',
  ALONGSIDE_DEBUG: '1',
  ALONGSIDE_DEBUG_PORT: String(debugPort),
  ALONGSIDE_USERDATA: path.join(work, 'user'),
  UNDERSTUDY_DATA_DIR: data,
  ENGINE_PORT: String(engine.port),
  AGENT_PORT: String(agent.port),
  UNDERSTUDY_ENGINE_URL: `http://127.0.0.1:${engine.port}`,
  UNDERSTUDY_AGENT_URL: `http://127.0.0.1:${agent.port}`,
  UNDERSTUDY_EXT_PORT: String(extPort),
  DASHBOARD_PORT: '9',
  KNACK_DIST: path.join(work, 'dashboard'),
  KNACK_REPO: repo,
  ALONGSIDE_MOCK: '1',
  // Nothing that listens, looks or calls out: voice, awareness, Cue, the Gemini key, the real-desktop arm switches.
  UNDERSTUDY_VOICE: '0',
  UNDERSTUDY_FLAG_VOICE: '0',
  UNDERSTUDY_X_LIVE: '0',
  UNDERSTUDY_X_AWARENESS: '0',
  UNDERSTUDY_X_CUE: '0',
  UNDERSTUDY_X_GEMINI: '0',
  GEMINI_API_KEY: '',
  UNDERSTUDY_REAL_ACTUATOR: '0',
  ALONGSIDE_AGENCY_LOOP: '0',
}
delete env.ELECTRON_RUN_AS_NODE
const electron = (await import('electron')).default
const child = spawn(electron, [path.join(work, 'app/main/index.js')], { cwd: desktop, env, stdio: ['ignore', 'pipe', 'pipe'] })
let log = ''
child.stdout.on('data', (d) => (log += d))
child.stderr.on('data', (d) => (log += d))
let exited = null
child.on('exit', (code) => (exited = code))

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const up = async () => {
  for (let i = 0; i < 300 && exited === null; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${debugPort}/health`)
      if (r.ok) return true
    } catch {
      /* not yet */
    }
    await sleep(200)
  }
  return false
}
let code = 1
if (await up()) {
  await sleep(2500) // the shell attaches once the services answer
  const smoke = spawnSync('node', [path.join(here, 'shell-smoke.mjs'), '--port', String(debugPort), '--hidden'], { encoding: 'utf8' })
  process.stdout.write(smoke.stdout)
  process.stderr.write(smoke.stderr)
  code = smoke.status ?? 1
} else {
  console.log(`FAIL the app did not come up (exit ${exited}). Last log lines:\n${log.split('\n').slice(-25).join('\n')}`)
}
// Quit through the real path (before-quit, the quit guard, will-quit, the services stop, exit): a termination signal asks the app to quit, and it must leave by itself with code 0.
const quitAt = Date.now()
if (exited === null) child.kill('SIGTERM')
for (let i = 0; i < 80 && exited === null; i++) await sleep(100)
const quitMs = Date.now() - quitAt
const clean = exited === 0
console.log(`${clean ? 'PASS' : 'FAIL'} the app quits by itself after a termination signal, exit code 0, in under 8 seconds (exit ${exited}, ${quitMs} ms)`)
if (!clean) code = 1
if (exited === null) child.kill('SIGKILL')
engine.server.close()
agent.server.close()
if (code !== 0) console.log(`app log (tail):\n${log.split('\n').slice(-30).join('\n')}`)
fs.rmSync(work, { recursive: true, force: true })
process.exit(code)
