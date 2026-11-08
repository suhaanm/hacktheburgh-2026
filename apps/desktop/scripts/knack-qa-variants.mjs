#!/usr/bin/env node
// Hidden QA of how the REAL app (src/main/index.ts, built) behaves when its surroundings are wrong: a corrupted settings, window and wake file; a port that another program holds; no key;
// the agent service down and no repository to start it from; the data folder unreadable. Nothing is shown (KNACK_HIDDEN=1: activation policy "prohibited"), no global shortcut, no permission asked,
// no real click, keystroke or capture, no model call (the key is always empty). The services are stand-ins on free ports with a private data folder; never 7700, 7710 or 5173. For each variant it
// checks the app stays up, shows the right state (the main window's state through the debug server), and quits by itself with exit code 0.
//
//   cd apps/desktop && scripts/electron-lock.sh KNACK node scripts/knack-qa-variants.mjs
import { spawn, spawnSync } from 'node:child_process'
import fs from 'node:fs'
import http from 'node:http'
import net from 'node:net'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const desktop = path.resolve(here, '..')
const repo = path.resolve(desktop, '../..')
const work = path.join(desktop, 'out', 'knack-qa-var')
fs.rmSync(work, { recursive: true, force: true })
fs.mkdirSync(work, { recursive: true })
const run = (cmd, args, cwd) => {
  const r = spawnSync(cmd, args, { cwd, stdio: ['ignore', 'pipe', 'pipe'], encoding: 'utf8' })
  if (r.status !== 0) {
    console.error(`${cmd} ${args.join(' ')} failed:\n${(r.stdout ?? '').slice(-1500)}\n${(r.stderr ?? '').slice(-1500)}`)
    process.exit(1)
  }
}
console.log('building the app and the dashboard into private folders')
run(path.join(desktop, 'node_modules/.bin/electron-vite'), ['build', '--outDir', path.join(work, 'app')], desktop)
run(path.join(repo, 'apps/dashboard/node_modules/.bin/vite'), ['build', '--outDir', path.join(work, 'dashboard'), '--emptyOutDir'], path.join(repo, 'apps/dashboard'))

const freePort = () => new Promise((resolve) => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const { port } = s.address(); s.close(() => resolve(port)) }) })
const fake = (health) => new Promise((resolve) => {
  const server = http.createServer((req, res) => {
    res.setHeader('content-type', 'application/json')
    if (req.url === '/health') return res.end(JSON.stringify(health))
    if (req.url?.startsWith('/agents/runs')) return res.end('[]')
    res.statusCode = 404
    res.end('{"error":{"code":"not_found","message":"stand-in"}}')
  })
  server.listen(0, '127.0.0.1', () => resolve({ server, port: server.address().port }))
})
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const electron = (await import('electron')).default
let failed = 0
const check = (name, ok, detail) => { if (!ok) failed += 1; console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${ok ? '' : ` ${JSON.stringify(detail)}`}`) }

async function variant(name, { corrupt = false, engineBusy = false, noAgent = false, noRepo = false, unreadableData = false, packaged = false, expect }) {
  const dir = path.join(work, name)
  const data = path.join(dir, 'data')
  const user = path.join(dir, 'user')
  fs.mkdirSync(data, { recursive: true })
  fs.mkdirSync(user, { recursive: true })
  fs.writeFileSync(path.join(data, '.token'), 'qa-token-0123456789abcdef')
  if (corrupt) {
    fs.writeFileSync(path.join(user, 'settings.json'), '{"useLiveModels": tru')
    fs.writeFileSync(path.join(user, 'window-state.json'), '[[[')
    fs.writeFileSync(path.join(user, 'wake.json'), 'null')
    fs.writeFileSync(path.join(user, 'knack-window.json'), '\u0000\u0000')
  }
  if (unreadableData) fs.chmodSync(data, 0o000)
  const engine = engineBusy
    ? await new Promise((resolve) => { const server = http.createServer((q, r) => { r.statusCode = 503; r.end('not Knack, another program') }); server.listen(0, '127.0.0.1', () => resolve({ server, port: server.address().port })) })
    : await fake({ ok: true, mock: true })
  const agent = noAgent ? { server: { close() {} }, port: await freePort() } : await fake({ ok: true, mock: true, supervisor: { state: 'idle', generation: 1 } })
  const debugPort = await freePort()
  const env = {
    ...process.env,
    KNACK_HIDDEN: '1', ALONGSIDE_DEBUG: '1', ALONGSIDE_DEBUG_PORT: String(debugPort), ALONGSIDE_USERDATA: user, UNDERSTUDY_DATA_DIR: data,
    ENGINE_PORT: String(engine.port), AGENT_PORT: String(agent.port),
    UNDERSTUDY_ENGINE_URL: `http://127.0.0.1:${engine.port}`, UNDERSTUDY_AGENT_URL: `http://127.0.0.1:${agent.port}`, UNDERSTUDY_EXT_PORT: String(await freePort()),
    DASHBOARD_PORT: '9', ...(packaged ? {} : { KNACK_DIST: path.join(work, 'dashboard') }), KNACK_REPO: noRepo ? path.join(dir, 'no-such-repo') : repo, KNACK_SITES: '0', KNACK_NO_SINGLE_INSTANCE: '1', ALONGSIDE_MOCK: '1',
    UNDERSTUDY_VOICE: '0', UNDERSTUDY_FLAG_VOICE: '0', UNDERSTUDY_X_LIVE: '0', UNDERSTUDY_X_AWARENESS: '0', UNDERSTUDY_X_CUE: '0', UNDERSTUDY_X_GEMINI: '0', UNDERSTUDY_X_WAKE: '0',
    GEMINI_API_KEY: '', UNDERSTUDY_REAL_ACTUATOR: '0', ALONGSIDE_AGENCY_LOOP: '0',
  }
  delete env.ELECTRON_RUN_AS_NODE
  // The packaged Knack.app's own executable (never opened with `open`, never shown: KNACK_HIDDEN keeps it prohibited), reading its dashboard, repository path and helper from its own Resources.
  if (packaged) delete env.KNACK_REPO
  const child = packaged
    ? spawn(path.join(desktop, 'dist-app/mac-arm64/Knack.app/Contents/MacOS/Knack'), [], { cwd: dir, env, stdio: ['ignore', 'pipe', 'pipe'] })
    : spawn(electron, [path.join(work, 'app/main/index.js')], { cwd: desktop, env, stdio: ['ignore', 'pipe', 'pipe'] })
  let log = ''
  child.stdout.on('data', (d) => (log += d))
  child.stderr.on('data', (d) => (log += d))
  let exited = null
  child.on('exit', (code) => (exited = code))
  let up = false
  for (let i = 0; i < 150 && exited === null && !up; i++) {
    try { up = (await fetch(`http://127.0.0.1:${debugPort}/health`)).ok } catch { /* not yet */ }
    if (!up) await sleep(200)
  }
  let state = null
  // give the stack time to reach its final phase (a port held by another program is said after the first look; no repository is said at once)
  for (let i = 0; i < 60 && up && exited === null; i++) {
    await sleep(500)
    try { state = await (await fetch(`http://127.0.0.1:${debugPort}/state`)).json() } catch { state = null }
    const phase = state?.knack?.stack?.phase
    if (phase === 'ready' || phase === 'failed') break
  }
  const phase = state?.knack?.stack?.phase
  const code = state?.knack?.stack?.code ?? state?.knack?.stack?.failure?.code
  check(`[${name}] the app comes up and stays up (debug server answers, no crash)`, up && exited === null, { up, exited, log: log.split('\n').slice(-8) })
  check(`[${name}] ${expect.text}`, expect.ok(phase, code, state), { phase, code, stack: state?.knack?.stack })
  check(`[${name}] the main window exists`, state?.knack?.window?.exists === true, state?.knack?.window)
  const t0 = Date.now()
  if (exited === null) child.kill('SIGTERM')
  for (let i = 0; i < 150 && exited === null; i++) await sleep(100)
  check(`[${name}] it quits by itself on a termination signal with exit code 0`, exited === 0, { exited, ms: Date.now() - t0 })
  if (exited === null) child.kill('SIGKILL')
  if (unreadableData) fs.chmodSync(data, 0o755)
  engine.server.close()
  agent.server.close()
}

await variant('corrupt-files', { corrupt: true, expect: { text: 'a damaged settings, window and wake file read as the defaults and the stack reaches ready', ok: (p) => p === 'ready' } })
await variant('port-held-by-another-program', { engineBusy: true, expect: { text: 'a port another program holds is said plainly (stack failed, port_busy), not a crash or a hang', ok: (p, c) => p === 'failed' && c === 'port_busy' } })
await variant('agent-down-no-repo', { noAgent: true, noRepo: true, expect: { text: 'the agent not answering with nothing to start it from ends on one plain failure (no_repo), the app stays up', ok: (p, c) => p === 'failed' && (c === 'no_repo' || c === 'agent_failed') } })
await variant('no-key-example-data', { expect: { text: 'no key: the app runs on example data and the stack is ready', ok: (p) => p === 'ready' } })
if (fs.existsSync(path.join(desktop, 'dist-app/mac-arm64/Knack.app/Contents/MacOS/Knack'))) {
  await variant('packaged-app-hidden', { packaged: true, expect: { text: 'the packaged Knack.app starts its own main process from its asar, finds its dashboard and repository path in its Resources, attaches to the stand-in services and is ready', ok: (p, c, st) => p === 'ready' && st?.knack?.stack?.dashboard === 'dist' } })
} else console.log('SKIP the packaged app is not built (npm run package)')
fs.rmSync(work, { recursive: true, force: true })
process.exit(failed === 0 ? 0 : 1)
