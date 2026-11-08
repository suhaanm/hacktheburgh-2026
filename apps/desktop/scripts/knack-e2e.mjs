#!/usr/bin/env node
// Hidden end-to-end run of the REAL app (src/main/index.ts, built) with the Knack shell on: nothing is shown (KNACK_HIDDEN=1: activation policy "prohibited", no Dock icon,
// no menu bar item, windows never shown), no global shortcut is taken, no permission is asked, and no real click, keystroke or capture is made. The services are stand-ins on
// private ports with a private data folder (never 7700, 7710, 5173 or the repository's data); voice, awareness and Cue are switched off. It then runs scripts/shell-smoke.mjs against
// the app's debug server, so the whole path (index.ts, the shell, the machine, the HUD, the debug hooks) is exercised.
//
//   cd apps/desktop && scripts/electron-lock.sh KNACK node scripts/knack-e2e.mjs
//
// With --real-services there are no stand-ins: the app starts the repository's REAL engine and agent itself (through uv, in example-data mode, on free ports, on the repository's own
// data/demo-home and data/demo-data), the run waits until both answer, then checks that quitting stops exactly those two and leaves nothing listening. It needs uv and a first run
// takes a minute or two (the demo data is made once). It never uses 7700, 7710 or 5173 and never starts the sandbox sites.
//
//   cd apps/desktop && scripts/electron-lock.sh KNACK node scripts/knack-e2e.mjs --real-services
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
const fake = (health, runs = []) =>
  new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      res.setHeader('content-type', 'application/json')
      if (req.url === '/health') return res.end(JSON.stringify(health))
      if (req.url?.startsWith('/agents/runs')) return res.end(JSON.stringify(runs))
      res.statusCode = 404
      res.end('{"error":{"code":"not_found","message":"stand-in"}}')
    })
    server.listen(0, '127.0.0.1', () => resolve({ server, port: server.address().port }))
  })
const real = process.argv.includes('--real-services')
// In the real mode the "stand-ins" are only the two free port numbers the app's own services will take.
const engine = real ? { server: { close() {} }, port: await freePort() } : await fake({ ok: true, mock: true })
// The agent stand-in lists two records a dead process left behind, as the real service does (it lists the runs it has on disk, with their last state): a run "planning" with one
// child and none done ("0 of 1"), and one "running". Three days old: no real run lasts more than 15 minutes. The pill must never start for them.
const threeDaysAgo = new Date(Date.now() - 3 * 24 * 60 * 60_000).toISOString().replace(/\.\d+Z$/, 'Z')
const ghosts = [
  { run_id: 'r_ghost001', kind: 'data.profile', mode: 'foreground', state: 'planning', started: threeDaysAgo, person: null, children: [{ id: 'c1', role: 'worker', state: 'created' }] },
  { run_id: 'r_ghost002', kind: 'data.profile', mode: 'foreground', state: 'running', started: threeDaysAgo, person: null, children: [] },
]
const agent = real ? { server: { close() {} }, port: await freePort() } : await fake({ ok: true, mock: true, supervisor: { state: 'idle', generation: 1 } }, ghosts)
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
  KNACK_SITES: '0', // the sandbox sites bind fixed ports (7801 to 7803) that belong to whoever runs the demo
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
const answers = async (port) => {
  try {
    return (await fetch(`http://127.0.0.1:${port}/health`, { signal: AbortSignal.timeout(1500) })).ok
  } catch {
    return false
  }
}
let code = 1
if (await up()) {
  if (real) {
    // The app starts the real engine and agent itself (a first run also makes the demo data): wait until both answer.
    let both = false
    for (let i = 0; i < 400 && exited === null && !both; i++) {
      both = (await answers(engine.port)) && (await answers(agent.port))
      if (!both) await sleep(1000)
    }
    const health = both ? await fetch(`http://127.0.0.1:${agent.port}/health`).then((r) => r.json()).catch(() => ({})) : {}
    const okStart = both && health.mock === true
    console.log(`${okStart ? 'PASS' : 'FAIL'} the app started the real engine and agent itself, example data (mock models), and both answer (${both ? `agent mock ${health.mock}` : 'they did not come up'})`)
    code = okStart ? 0 : 1
  } else {
    await sleep(2500) // the shell attaches once the services answer
    const smoke = spawnSync('node', [path.join(here, 'shell-smoke.mjs'), '--port', String(debugPort), '--hidden', '--ghosts'], { encoding: 'utf8' })
    process.stdout.write(smoke.stdout)
    process.stderr.write(smoke.stderr)
    code = smoke.status ?? 1
  }
} else {
  console.log(`FAIL the app did not come up (exit ${exited}). Last log lines:\n${log.split('\n').slice(-25).join('\n')}`)
}
// Quit through the real path (before-quit, the quit guard, will-quit, the services stop, exit): a termination signal asks the app to quit, and it must leave by itself with code 0.
// With real services it also stops exactly the two it started (each gets 4 s to end before it is forced), so the limit is longer.
const quitLimit = real ? 30 : 8
const quitAt = Date.now()
if (exited === null) child.kill('SIGTERM')
for (let i = 0; i < quitLimit * 10 && exited === null; i++) await sleep(100)
const quitMs = Date.now() - quitAt
const clean = exited === 0
console.log(`${clean ? 'PASS' : 'FAIL'} the app quits by itself after a termination signal, exit code 0, in under ${quitLimit} seconds (exit ${exited}, ${quitMs} ms)`)
if (!clean) code = 1
if (exited === null) child.kill('SIGKILL')
if (real) {
  await sleep(500)
  const left = [(await answers(engine.port)) ? 'engine' : null, (await answers(agent.port)) ? 'agent' : null].filter(Boolean)
  console.log(`${left.length === 0 ? 'PASS' : 'FAIL'} quitting stopped the engine and the agent it started: nothing listens on their ports${left.length ? ` (still up: ${left.join(', ')})` : ''}`)
  if (left.length) {
    code = 1
    // Whatever is still listening on these two free ports was started by this run: do not leave it behind.
    for (const port of [engine.port, agent.port]) {
      const pids = spawnSync('lsof', ['-ti', `tcp:${port}`, '-sTCP:LISTEN'], { encoding: 'utf8' }).stdout.split('\n').filter(Boolean)
      for (const pid of pids) spawnSync('kill', ['-TERM', pid])
    }
  }
}
engine.server.close()
agent.server.close()
if (code !== 0) console.log(`app log (tail):\n${log.split('\n').slice(-30).join('\n')}`)
fs.rmSync(work, { recursive: true, force: true })
process.exit(code)
