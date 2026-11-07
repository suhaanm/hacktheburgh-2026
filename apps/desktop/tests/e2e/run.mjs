// `npm run e2e`: builds, launches the app ONCE under the electron lock, waits for /health, runs the e2e scenarios, always kills the app.
// Flags: --mode mock|real (default mock; real = no ALONGSIDE_MOCK, uses whatever services.ts wires + the key in .env)
//        --visible (show windows; needed for real screen capture / accuracy runs) --no-build --stage (also serve apps/demo-stage)
//        --accuracy (run the real-screen accuracy harness instead; writes docs/QA_ACCURACY.md; needs --mode real --visible)
//        --with-accuracy (run the scenarios, then the accuracy harness in the same app launch)
//        --record | --replay [hybrid] (save / serve Gemini HTTP responses in .userdata-replay)
//        --grep <pattern> | --files a,b (vitest file filters)
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import net from 'node:net'
import { fileURLToPath } from 'node:url'

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const argv = process.argv.slice(2)
const flag = (name) => argv.includes(`--${name}`)
const opt = (name, fallback) => {
  const i = argv.indexOf(`--${name}`)
  return i >= 0 && argv[i + 1] ? argv[i + 1] : fallback
}

const mode = opt('mode', 'mock')
const freePort = () =>
  new Promise((resolve, reject) => {
    const srv = net.createServer()
    srv.listen(0, '127.0.0.1', () => {
      const { port } = srv.address()
      srv.close(() => resolve(port))
    })
    srv.on('error', reject)
  })
// Other roles run their own instances on 7777-7790; pick free ports unless told otherwise.
const debugPort = Number(opt('debug-port', process.env.E2E_DEBUG_PORT || (await freePort())))
const devPort = Number(opt('dev-port', process.env.E2E_DEV_PORT || (await freePort())))
const stagePort = Number(process.env.STAGE_PORT || 5180)
const visible = flag('visible')
const userData = fs.mkdtempSync(path.join(os.tmpdir(), 'alongside-e2e-'))
const appLog = path.join(userData, 'app.log')

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const portOpen = (port) =>
  new Promise((resolve) => {
    const sock = net.connect({ port, host: '127.0.0.1' }, () => {
      sock.destroy()
      resolve(true)
    })
    sock.on('error', () => resolve(false))
  })

function run(cmd, args, env = {}) {
  return new Promise((resolve) => {
    const child = spawn(cmd, args, { cwd: repo, stdio: 'inherit', env: { ...process.env, ...env } })
    child.on('exit', (code) => resolve(code ?? 1))
  })
}

async function waitHealth(app, ms) {
  const deadline = Date.now() + ms
  while (Date.now() < deadline) {
    if (app.exitCode !== null) return false
    try {
      const res = await fetch(`http://127.0.0.1:${debugPort}/health`)
      if (res.ok) return true
    } catch {}
    await sleep(300)
  }
  return false
}

let app = null
let stageProc = null
function killAll() {
  for (const proc of [app]) {
    if (proc && proc.exitCode === null) proc.kill('SIGTERM')
  }
}
process.on('SIGINT', () => {
  killAll()
  process.exit(130)
})
process.on('SIGTERM', () => {
  killAll()
  process.exit(143)
})

let exitCode = 1
try {
  if (!flag('no-build')) {
    const code = await run('npm', ['run', 'build'])
    if (code !== 0) throw new Error('build failed')
  }
  if (await portOpen(debugPort)) throw new Error(`port ${debugPort} is already in use (is another instance running?)`)

  if (!(await portOpen(stagePort))) {
    // Left running on purpose: other roles use the same static server and a kill here would break their runs.
    stageProc = spawn('node', ['scripts/stage-server.mjs'], { cwd: repo, stdio: 'ignore', detached: true, env: { ...process.env, STAGE_PORT: String(stagePort) } })
    stageProc.unref()
    for (let i = 0; i < 20 && !(await portOpen(stagePort)); i++) await sleep(150)
  }

  const env = {
    ...process.env,
    ALONGSIDE_USERDATA: userData,
    ALONGSIDE_DEBUG: '1', // the debug HTTP server is opt-in (unauthenticated); tests need it
    ALONGSIDE_DEBUG_PORT: String(debugPort),
    ALONGSIDE_DEV_PORT: String(devPort),
    ALONGSIDE_DEV_STAGE: '1',
    ALONGSIDE_LOCK_WAIT: process.env.ALONGSIDE_LOCK_WAIT || '240',
    ALONGSIDE_LOCK_MAX_SECONDS: process.env.ALONGSIDE_LOCK_MAX_SECONDS || '420',
    STAGE_PORT: String(stagePort),
    ALONGSIDE_ACTUATOR_DRYRUN: '1', // tests must never click, type or open real things
  }
  // Venue-Wi-Fi backup: --record saves every Gemini HTTP response; --replay[=hybrid] serves them offline (see src/main/dev/replay).
  if (flag('record') || flag('replay')) env.ALONGSIDE_REPLAY_DIR = path.join(repo, '.userdata-replay')
  if (flag('record')) env.ALONGSIDE_RECORD = '1'
  if (flag('replay')) env.ALONGSIDE_REPLAY = opt('replay', '1') === 'hybrid' ? 'hybrid' : '1'
  if (mode === 'mock') env.ALONGSIDE_MOCK = '1'
  else delete env.ALONGSIDE_MOCK
  if (!visible) env.ALONGSIDE_HEADLESS = '1'
  else delete env.ALONGSIDE_HEADLESS

  const out = fs.openSync(appLog, 'a')
  app = spawn('scripts/electron-lock.sh', ['QA', 'node_modules/.bin/electron', '.'], { cwd: repo, stdio: ['ignore', out, out], env })
  console.log(`[e2e] mode=${mode} visible=${visible} debug=:${debugPort} dev=:${devPort} log=${appLog}`)

  if (!(await waitHealth(app, 300_000))) {
    console.error('[e2e] app did not become healthy; last log lines:')
    console.error(fs.readFileSync(appLog, 'utf8').split('\n').slice(-25).join('\n'))
    throw new Error('app not healthy (lock held by another role?)')
  }
  // The dev hooks come up a tick after /health.
  for (let i = 0; i < 40; i++) {
    try {
      if ((await fetch(`http://127.0.0.1:${devPort}/dev/health`)).ok) break
    } catch {}
    await sleep(150)
  }

  const vitestArgs = ['run', '--config', flag('accuracy') ? 'tests/e2e/vitest.acc.config.ts' : 'tests/e2e/vitest.e2e.config.ts', '--reporter', 'verbose']
  // The privacy/spend check reads the request log, so it must run after everything else that talks to Gemini.
  const privacyFile = '08-privacy-spend'
  const requested = opt('files', '').split(',').filter(Boolean)
  const privacyLast = !flag('accuracy') && (requested.length === 0 || requested.some((f) => f.includes(privacyFile)))
  const first = requested.filter((f) => !f.includes(privacyFile))
  const skipFirstPass = requested.length > 0 && first.length === 0
  if (first.length) vitestArgs.push(...first)
  else if (!flag('accuracy')) vitestArgs.push('--exclude', `tests/e2e/${privacyFile}.e2e.ts`)
  const grep = opt('grep', '')
  if (grep) vitestArgs.push('-t', grep)
  const testEnv = {
    E2E_MODE: mode,
    E2E_DEBUG_URL: `http://127.0.0.1:${debugPort}`,
    E2E_DEV_URL: `http://127.0.0.1:${devPort}`,
    E2E_STAGE_URL: `http://127.0.0.1:${stagePort}/`,
    E2E_USERDATA: userData,
    E2E_APP_LOG: appLog,
    E2E_VISIBLE: visible ? '1' : '0',
    VITE_CONFIG_NATIVE_IGNORE_WARNING: 'true',
  }
  exitCode = skipFirstPass ? 0 : await run('node_modules/.bin/vitest', vitestArgs, testEnv)
  if (privacyLast) {
    const code = await run('node_modules/.bin/vitest', ['run', '--config', 'tests/e2e/vitest.e2e.config.ts', '--reporter', 'verbose', `tests/e2e/${privacyFile}.e2e.ts`], testEnv)
    exitCode = exitCode || code
  }
  if (flag('with-accuracy')) {
    // Same app launch (one lock slot): the accuracy harness runs after the scenarios.
    const accCode = await run('node_modules/.bin/vitest', ['run', '--config', 'tests/e2e/vitest.acc.config.ts', '--reporter', 'verbose'], testEnv)
    exitCode = exitCode || accCode
  }
} catch (err) {
  console.error('[e2e] fatal:', err instanceof Error ? err.message : err)
} finally {
  killAll()
  await sleep(1500)
  console.log(`[e2e] app log kept at ${appLog}`)
}
process.exit(exitCode)
