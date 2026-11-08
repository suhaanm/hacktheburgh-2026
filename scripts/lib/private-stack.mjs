// Throwaway services for the demo tools (scripts/link-audit.mjs, apps/desktop/scripts/demo-worker.mjs).
//
// Everything started here lives in a temporary directory, listens on a free port and is stopped by the caller's cleanup. It never uses the
// owner's ports (7700 engine, 7710 agent, 5173 dashboard) and never reads or writes the checkout's data/ directory (the one thing it reads is
// a COPY of data/synthetic/learners, as scripts/rehearse-coach.mjs does). An engine that gets POST /kill forwards it to AGENT_PORT, which by
// default is the live agent on 7710: so the throwaway engine gets AGENT_PORT=1, and this module refuses to start one when the environment
// points at 7710.
import { spawn } from 'node:child_process'
import { createServer } from 'node:net'
import { cpSync, existsSync, mkdirSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

export async function until(cond, ms, label, every = 100) {
  const t0 = Date.now()
  for (;;) {
    const v = await cond()
    if (v) return v
    if (Date.now() - t0 > ms) throw new Error(`timed out waiting for ${label}`)
    await sleep(every)
  }
}

export const freePort = () =>
  new Promise((res, rej) => {
    const s = createServer()
    s.once('error', rej)
    s.listen(0, '127.0.0.1', () => {
      const p = s.address().port
      s.close(() => res(p))
    })
  })

export async function getJson(url, init = {}, timeoutMs = 20000) {
  const ac = new AbortController()
  const timer = setTimeout(() => ac.abort(), timeoutMs)
  try {
    const r = await fetch(url, { ...init, signal: ac.signal })
    const text = await r.text()
    let body = null
    try {
      body = JSON.parse(text)
    } catch {
      /* not JSON */
    }
    return { status: r.status, headers: r.headers, body, bytes: text.length, text }
  } finally {
    clearTimeout(timer)
  }
}

export const postJson = (url, body) => getJson(url, { method: 'POST', headers: { 'content-type': 'application/json', 'x-understudy-actor': 'worker' }, body: JSON.stringify(body) })

/** The checkout this script sits in (the folder with pyproject.toml above it). */
export function repoRootFrom(metaUrl) {
  let d = dirname(fileURLToPath(metaUrl))
  for (let i = 0; i < 6; i++) {
    if (existsSync(join(d, 'pyproject.toml')) && existsSync(join(d, 'services'))) return d
    d = resolve(d, '..')
  }
  throw new Error('could not find the repository root (pyproject.toml) above this script')
}

/** The python of the repo's uv environment (`uv sync` makes it). KNACK_PYTHON overrides. */
export function pythonOf(repo) {
  const p = process.env.KNACK_PYTHON || join(repo, '.venv/bin/python')
  if (!existsSync(p)) throw new Error(`no python at ${p}: run \`uv sync --all-packages\` first (or set KNACK_PYTHON)`)
  return p
}

export function extensionDist(repo, override) {
  const d = resolve(override || process.env.KNACK_EXTENSION_DIST || join(repo, 'extension/dist'))
  if (!existsSync(join(d, 'manifest.json'))) throw new Error(`the extension is not built at ${d} (cd extension && npm run build)`)
  return d
}

/** A tracked child process: its output tail is kept for the error message, never printed while it works. */
export class Procs {
  constructor() {
    this.children = new Map()
  }
  start(name, cmd, args, opts = {}) {
    const p = spawn(cmd, args, { stdio: ['pipe', 'pipe', 'pipe'], ...opts })
    p.logTail = ''
    const keep = (d) => (p.logTail = (p.logTail + d).slice(-4000))
    p.stdout.on('data', keep)
    p.stderr.on('data', keep)
    this.children.set(name, p)
    return p
  }
  alive(p) {
    return p.exitCode === null && p.signalCode === null
  }
  async stop(name, signal = 'SIGTERM') {
    const p = this.children.get(name)
    if (!p || !this.alive(p)) return
    p.kill(signal)
    await Promise.race([new Promise((r) => p.once('exit', r)), sleep(6000)])
    if (this.alive(p)) {
      p.kill('SIGKILL')
      await Promise.race([new Promise((r) => p.once('exit', r)), sleep(2000)])
    }
  }
  async stopAll() {
    for (const n of [...this.children.keys()].reverse()) await this.stop(n)
  }
  left() {
    return [...this.children].filter(([, p]) => this.alive(p)).map(([n]) => n)
  }
}

/** Refuse to start anything that could reach the live agent. */
export function refuseLiveAgent() {
  if (process.env.AGENT_PORT === '7710' || process.env.UNDERSTUDY_AGENT_URL?.includes(':7710')) {
    throw new Error('refusing to run: AGENT_PORT / UNDERSTUDY_AGENT_URL point at the live agent service (7710)')
  }
}

/**
 * A throwaway engine (mock mode, its own home and data directory) on a free port. `learners: true` puts a COPY of the learners' synthetic
 * data in its data directory (the coach needs it). `onboard` runs the worker's onboarding so capture consent is on (the extension asks).
 * Returns { engine, port, home, data, root, onboarded }; the caller stops it through `procs.stop('engine')` and removes `root`.
 */
export async function startPrivateEngine({ repo, procs, person = 'p_learn01', role = 'benefits-processor', learners = false, onboard = true, tmp }) {
  refuseLiveAgent()
  const root = mkdtempSync(join(tmp ?? process.env.KNACK_TMP ?? tmpdir(), 'knack-private-'))
  const home = join(root, 'home')
  const data = join(root, 'data')
  mkdirSync(home)
  mkdirSync(join(data, 'synthetic'), { recursive: true })
  if (learners) {
    const src = join(repo, 'data/synthetic/learners')
    if (!existsSync(src)) throw new Error('data/synthetic/learners is missing (uv run understudy synth --all)')
    cpSync(src, join(data, 'synthetic/learners'), { recursive: true })
  }
  const port = await freePort()
  const engine = `http://127.0.0.1:${port}`
  const bin = join(repo, '.venv/bin/understudy')
  if (!existsSync(bin)) throw new Error(`no ${bin}: run \`uv sync --all-packages\` first`)
  procs.start('engine', bin, ['serve', '--port', String(port)], {
    cwd: root,
    env: { PATH: process.env.PATH, HOME: process.env.HOME, UNDERSTUDY_HOME: home, UNDERSTUDY_DATA_DIR: data, UNDERSTUDY_MOCK: '1', ENGINE_PORT: String(port), AGENT_PORT: '1' },
  })
  await until(() => getJson(`${engine}/health`, {}, 2000).then((r) => r.status === 200).catch(() => false), 90_000, 'the throwaway engine', 300)
  let onboarded = null
  if (onboard) {
    const r = await postJson(`${engine}/onboarding`, { role, answers: { capture: true }, person })
    onboarded = r.status
  }
  return { engine, port, home, data, root, onboarded, person }
}

/** The three calculator sites and the case-note page on free ports, in one throwaway process (SandboxCluster, ephemeral). */
export async function startPrivateSites({ repo, procs }) {
  const code = [
    'import json, time',
    'from understudy_agent.sandbox_sites.runner import SandboxCluster',
    'c = SandboxCluster(ephemeral=True).start()',
    'print("PORTS " + json.dumps(c.ports), flush=True)',
    'time.sleep(86400)',
  ].join('\n')
  const p = procs.start('sites', pythonOf(repo), ['-I', '-c', code], { cwd: tmpdir() })
  await until(() => /PORTS \{/.test(p.logTail) || p.exitCode !== null, 30_000, 'the private sandbox sites', 200)
  const m = /PORTS (\{.*\})/.exec(p.logTail)
  if (!m) throw new Error(`the private sandbox sites did not start: ${p.logTail.trim().slice(-300)}`)
  const ports = JSON.parse(m[1])
  return { ports, urls: { a: `http://127.0.0.1:${ports.a}`, b: `http://127.0.0.1:${ports.b}`, c: `http://127.0.0.1:${ports.c}` } }
}

export function removeTree(dir) {
  try {
    rmSync(dir, { recursive: true, force: true })
  } catch {
    /* best effort: it is a temp directory */
  }
}
