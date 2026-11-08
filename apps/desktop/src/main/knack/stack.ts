// The services lifecycle: Knack.app starts the stack it needs and stops only what it started.
//
//   1. Look: engine :7700 /health, agent :7710 /health, and the dashboard assets (built dist, or a dev server that answers).
//   2. If everything is up, attach to it and never touch it, whoever started it (the owner's `make demo`, for instance). Quitting Knack leaves it running.
//   3. Otherwise start what is missing, the way `make live` does when the models are live (real models, the isolated data/live-home and data/live-data,
//      seeded once) and the way `make demo` does in example-data mode (mock models, every extension layer on, data/demo-home and data/demo-data). Each service is a child of this app in its own process group, so quitting stops
//      exactly those and their children, and nothing else. scripts/stop.sh and the pid files under data/pids are never used: they could name a stack
//      this app did not start.
//   4. A failure ends in one plain message and a retry; nothing is retried behind the person's back.
//
// Everything effectful is injected (health checks, spawn, files, clock), so the tests run it with fakes and never touch a port or a process.
import path from 'node:path'

export type StackMode = 'live' | 'demo'
export type StackStep = 'checking' | 'preparing' | 'engine' | 'agent' | 'dashboard'
export type FailCode = 'no_repo' | 'uv_missing' | 'prepare_failed' | 'engine_failed' | 'agent_failed' | 'dashboard_missing' | 'dashboard_failed'

export type StackState =
  | { phase: 'idle' }
  | { phase: 'starting'; step: StackStep }
  /** `mock`: what the agent service says about its models (true: example data); null when it did not say. */
  | { phase: 'ready'; started: string[]; dashboard: 'dist' | 'dev-server'; mock: boolean | null }
  | { phase: 'failed'; code: FailCode; message: string; hint?: string }

/** Plain words for each failure (one sentence, no codes). */
export const FAIL_MESSAGES: Record<FailCode, string> = {
  no_repo: 'Knack cannot find its project folder.',
  uv_missing: 'Knack needs the uv tool to start its services.',
  prepare_failed: 'Knack could not prepare its demo data.',
  engine_failed: 'The engine did not start.',
  agent_failed: 'The agent did not start.',
  dashboard_missing: 'The dashboard has not been built yet.',
  dashboard_failed: 'The dashboard did not start.',
}

export interface StackPorts {
  engine: number
  agent: number
  dashboard: number
  /** The first sandbox site port (dev.sh: SANDBOX_PORT_BASE, default 7801). */
  sites: number
}

export interface StackConfig {
  /** The repository (has scripts/dev.sh, services/ and apps/), or null when it cannot be found (packaged without KNACK_REPO). */
  repoRoot: string | null
  ports: StackPorts
  /** The built dashboard (apps/dashboard/dist, or the copy inside the packaged app), or null. */
  distDir: string | null
  /** Development: the vite dev server of apps/dashboard, used when it answers and no built copy is wanted. */
  devUrl: string | null
  /** Prefer a running dev server over the built copy (development only). */
  preferDevServer: boolean
  /** The isolated directories each mode uses, relative to the repo: `make demo` (data/demo-home, data/demo-data) and `make live` (data/live-home, data/live-data). */
  dirs: { demo: { home: string; data: string }; live: { home: string; data: string } }
  /** The mode to start in until setMode says otherwise. */
  mode: StackMode
  /** Start the sandbox calculator sites with the agent (default true). KNACK_SITES=0 turns it off: the sites bind fixed ports (7801 to 7803) that a check or a second checkout may not take. */
  startSites?: boolean
  timeouts: { engineMs: number; agentMs: number; dashboardMs: number; seedMs: number; pollMs: number; stopMs: number }
}

export interface ChildHandle {
  pid: number | null
  /** Resolves with the exit code when the process ends (null for a signal). */
  exited: Promise<number | null>
  /** Signals the whole process group (the child and anything it started). */
  kill(signal: 'SIGTERM' | 'SIGKILL'): void
}

export interface SpawnSpec {
  name: string
  command: string
  args: string[]
  cwd: string
  env: Record<string, string>
}

export interface StackDeps {
  config: StackConfig
  /** GET; `ok` is a 2xx answer within the time limit; `json` the parsed body when there is one. */
  get(url: string, timeoutMs: number): Promise<{ ok: boolean; json?: unknown }>
  spawn(spec: SpawnSpec): ChildHandle
  /** Runs a command to completion (seed, synth). */
  run(spec: SpawnSpec, timeoutMs: number): Promise<{ code: number | null }>
  exists(p: string): boolean
  mkdirp(p: string): void
  /** Creates an empty file (a marker) when it is not there. */
  touch(p: string): void
  findExecutable(name: string): string | null
  env(): Record<string, string>
  dataDirId(dir: string): string | null
  sleep(ms: number): Promise<void>
  now(): number
  log?: (...args: unknown[]) => void
}

export interface Stack {
  state(): StackState
  subscribe(cb: (s: StackState) => void): () => void
  /** Starts (or attaches). One call at a time: a second call while one runs shares it. */
  start(): Promise<StackState>
  /** After a failure: look again and start what is still missing. */
  retry(): Promise<StackState>
  /** Which models the services this object starts use: live (real models from the repo's .env) or demo (example data). */
  mode(): StackMode
  setMode(m: StackMode): void
  /** Stops what this object started and starts again, in the current mode (the Use live models switch). Services it did not start are left alone. */
  restart(): Promise<StackState>
  /** Stops only what this object started: SIGTERM to the group, SIGKILL after the limit. Resolves when they are gone. */
  stop(): Promise<void>
  /** Names of the services this object started and still holds. */
  started(): string[]
  /** The data directory the running stack uses (after attach, from the agent's data_dir_id), or the demo directory when this app started it. */
  dataDir(): string | null
}

/** PATH for children: a Dock-launched app has only /usr/bin:/bin:/usr/sbin:/sbin, and `uv` lives elsewhere. */
export function augmentedPath(current: string | undefined, home: string): string {
  const extra = ['/opt/homebrew/bin', '/usr/local/bin', path.join(home, '.local/bin'), path.join(home, '.cargo/bin'), '/usr/bin', '/bin', '/usr/sbin', '/sbin']
  const seen = new Set<string>()
  return [...(current ?? '').split(':'), ...extra].filter((d) => d && !seen.has(d) && !!seen.add(d)).join(':')
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null

export function createStack(deps: StackDeps): Stack {
  const cfg = deps.config
  const log = deps.log ?? (() => undefined)
  const listeners = new Set<(s: StackState) => void>()
  const children = new Map<string, ChildHandle>()
  let state: StackState = { phase: 'idle' }
  let running: Promise<StackState> | null = null
  let dataDir: string | null = null

  const set = (s: StackState): StackState => {
    state = s
    for (const l of listeners) l(s)
    return s
  }
  const fail = (code: FailCode, hint?: string): StackState => set({ phase: 'failed', code, message: FAIL_MESSAGES[code], ...(hint ? { hint } : {}) })

  const url = (port: number, p = '/health'): string => `http://127.0.0.1:${port}${p}`
  const healthy = async (port: number): Promise<{ ok: boolean; json?: unknown }> => deps.get(url(port), 1500).catch(() => ({ ok: false }))

  let mode: StackMode = cfg.mode

  /** The environment of a child: the ports, and the mode's own home and data directory, exactly as `make live` and `make demo` set them. */
  const modeEnv = (): Record<string, string> => {
    const root = cfg.repoRoot as string
    const env = { ...deps.env() }
    env.PATH = augmentedPath(env.PATH, env.HOME ?? '')
    env.ENGINE_PORT = String(cfg.ports.engine)
    env.AGENT_PORT = String(cfg.ports.agent)
    env.DASHBOARD_PORT = String(cfg.ports.dashboard)
    env.SANDBOX_PORT_BASE = String(cfg.ports.sites)
    const d = cfg.dirs[mode]
    env.UNDERSTUDY_HOME = path.join(root, d.home)
    env.UNDERSTUDY_DATA_DIR = path.join(root, d.data)
    if (mode === 'live') {
      env.UNDERSTUDY_MOCK = '0' // real models; the keys come from the repo's own .env, which the services read themselves
    } else {
      env.UNDERSTUDY_MOCK = '1'
      env.UNDERSTUDY_X = '1'
    }
    return env
  }

  const logFile = (name: string): string => path.join(cfg.repoRoot as string, 'data', 'logs', `knack-${name}.log`)

  const launch = (name: string, command: string, args: string[], cwd: string): ChildHandle => {
    const h = deps.spawn({ name, command, args, cwd, env: modeEnv() })
    children.set(name, h)
    void h.exited.then((code) => {
      log('stack', `${name} ended (${code === null ? 'signal' : code})`)
      if (children.get(name) === h) children.delete(name)
    })
    return h
  }

  /** Waits until the address answers; false when the child ended first or the time ran out. */
  const waitUrl = async (address: string, child: ChildHandle | null, limitMs: number): Promise<boolean> => {
    let ended = false
    void child?.exited.then(() => {
      ended = true
    })
    const t0 = deps.now()
    while (deps.now() - t0 < limitMs) {
      if (ended) return false
      if ((await deps.get(address, 1500).catch(() => ({ ok: false }))).ok) return true
      await deps.sleep(cfg.timeouts.pollMs)
    }
    return false
  }

  const dashboardMode = async (): Promise<'dist' | 'dev-server' | null> => {
    const built = cfg.distDir !== null && deps.exists(path.join(cfg.distDir, 'index.html'))
    const devUp = async (): Promise<boolean> => cfg.devUrl !== null && (await deps.get(cfg.devUrl, 1200).catch(() => ({ ok: false }))).ok
    if (cfg.preferDevServer && (await devUp())) return 'dev-server'
    if (built) return 'dist'
    if (await devUp()) return 'dev-server'
    return null
  }

  async function pickDataDir(agent: unknown): Promise<void> {
    if (!cfg.repoRoot) return
    const id = isObj(agent) && typeof agent.data_dir_id === 'string' ? agent.data_dir_id : null
    const candidates = [path.join(cfg.repoRoot, cfg.dirs[mode].data), path.join(cfg.repoRoot, cfg.dirs[mode === 'live' ? 'demo' : 'live'].data), path.join(cfg.repoRoot, 'data')]
    const match = id ? candidates.find((c) => deps.dataDirId(c) === id) : undefined
    dataDir = match ?? candidates[0] ?? null
  }

  const mockOf = (agentJson: unknown): boolean | null => (isObj(agentJson) && typeof agentJson.mock === 'boolean' ? agentJson.mock : null)

  /** The isolated state for the mode, prepared the way the Makefile does: `make live` seeds once behind a marker, `make demo` seeds without --reset. */
  async function prepare(uv: string, root: string): Promise<boolean> {
    const d = cfg.dirs[mode]
    deps.mkdirp(path.join(root, 'data', 'logs'))
    deps.mkdirp(path.join(root, d.home))
    deps.mkdirp(path.join(root, d.data))
    const seedArgs = ['run', '--package', 'understudy-agent', 'python', '-m', 'understudy_engine.demo', 'seed']
    const run = (name: string, args: string[], env: Record<string, string> = modeEnv()): Promise<{ code: number | null }> => deps.run({ name, command: uv, args, cwd: root, env }, cfg.timeouts.seedMs).catch(() => ({ code: 1 as number | null }))
    // Both modes' isolated data directories hold links to the repository's shared synthetic data (data/synthetic), which `make synth` makes: made here first when it is missing,
    // into the repository's own data directory (so without the mode's UNDERSTUDY_DATA_DIR), exactly where the seed and dev.sh look for it.
    if (!deps.exists(path.join(root, 'data', 'synthetic'))) {
      const env = modeEnv()
      delete env.UNDERSTUDY_DATA_DIR
      delete env.UNDERSTUDY_HOME
      if ((await run('synth', ['run', '--package', 'understudy-engine', 'understudy', 'synth', '--all'], env)).code !== 0) return false
    }
    if (mode === 'live') {
      // The marker says the data directory is the isolated example content, so the seed may reset it; the second marker says it already did.
      deps.touch(path.join(root, d.data, '.understudy-demo-data'))
      if (!deps.exists(path.join(root, d.home, '.seeded'))) {
        if ((await run('seed', [...seedArgs, '--reset'])).code !== 0) return false
        deps.touch(path.join(root, d.home, '.seeded'))
      }
      return true
    }
    return (await run('seed', seedArgs)).code === 0 // the demo story, once. Without --reset a second run changes nothing.
  }

  async function ensure(): Promise<StackState> {
    set({ phase: 'starting', step: 'checking' })
    const [engine, agent, dash] = await Promise.all([healthy(cfg.ports.engine), healthy(cfg.ports.agent), dashboardMode()])
    if (engine.ok && agent.ok && dash) {
      await pickDataDir(agent.json)
      log('stack', 'everything is already running: attaching, and leaving it running on quit')
      return set({ phase: 'ready', started: [...children.keys()], dashboard: dash, mock: mockOf(agent.json) })
    }

    const needPython = !engine.ok || !agent.ok
    if (!cfg.repoRoot) {
      // Packaged without a repository next to it: the dashboard can still come from the bundled copy, but there is no stack to start.
      return fail(needPython ? 'no_repo' : 'dashboard_missing')
    }
    const root = cfg.repoRoot
    let uv: string | null = null
    if (needPython) {
      uv = deps.findExecutable('uv')
      if (!uv) return fail('uv_missing')
      set({ phase: 'starting', step: 'preparing' })
      if (!(await prepare(uv, root))) return fail('prepare_failed', 'The reason is in data/logs.')
    }

    if (!engine.ok) {
      set({ phase: 'starting', step: 'engine' })
      const c = launch('engine', uv as string, ['run', '--package', 'understudy-agent', 'understudy', 'serve'], root)
      if (!(await waitUrl(url(cfg.ports.engine), c, cfg.timeouts.engineMs))) return fail('engine_failed', `See ${path.relative(root, logFile('engine'))}.`)
    }

    if (!agent.ok) {
      set({ phase: 'starting', step: 'agent' })
      // The sandbox calculator sites the agent works on in the demo (dev.sh starts them too); they are not waited for.
      if (cfg.startSites !== false && deps.exists(path.join(root, 'services/agent/understudy_agent/sandbox_sites/__main__.py')) && !(await healthy(cfg.ports.sites)).ok) {
        launch('sites', uv as string, ['run', '--package', 'understudy-agent', 'python', '-m', 'understudy_agent.sandbox_sites'], root)
      }
      const c = launch('agent', uv as string, ['run', '--package', 'understudy-agent', 'python', '-m', 'understudy_agent.server'], root)
      if (!(await waitUrl(url(cfg.ports.agent), c, cfg.timeouts.agentMs))) return fail('agent_failed', `See ${path.relative(root, logFile('agent'))}.`)
    }

    let finalDash = dash
    if (!finalDash) {
      // No built copy and no dev server answering: start the dev server of apps/dashboard (development checkouts only).
      set({ phase: 'starting', step: 'dashboard' })
      const npm = cfg.devUrl ? deps.findExecutable('npm') : null
      if (!cfg.devUrl || !npm || !deps.exists(path.join(root, 'apps/dashboard/package.json'))) return fail('dashboard_missing')
      const c = launch('dashboard', npm, ['run', 'dev', '--', '--host', '127.0.0.1', '--port', String(cfg.ports.dashboard)], path.join(root, 'apps/dashboard'))
      if (!(await waitUrl(cfg.devUrl, c, cfg.timeouts.dashboardMs))) return fail('dashboard_failed', `See ${path.relative(root, logFile('dashboard'))}.`)
      finalDash = 'dev-server'
    }

    const answer = await healthy(cfg.ports.agent)
    if (children.has('engine') || children.has('agent') || !engine.ok || !agent.ok) dataDir = path.join(root, cfg.dirs[mode].data) // we started them: the mode's own directory
    else await pickDataDir(answer.json)
    return set({ phase: 'ready', started: [...children.keys()], dashboard: finalDash, mock: mockOf(answer.json) ?? (children.has('agent') ? mode === 'demo' : null) })
  }

  const start = (): Promise<StackState> => {
    if (state.phase === 'ready') return Promise.resolve(state)
    running ??= ensure()
      .catch((err: unknown) => fail('engine_failed', err instanceof Error ? err.message.slice(0, 120) : undefined))
      .finally(() => {
        running = null
      })
    return running
  }

  const api: Stack = {
    state: () => state,
    subscribe(cb) {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    start,
    mode: () => mode,
    setMode(m) {
      mode = m
    },
    async restart() {
      if (running) await running.catch(() => undefined)
      await api.stop()
      state = { phase: 'idle' }
      return start()
    },
    retry() {
      if (running) return running
      if (state.phase === 'ready') return Promise.resolve(state)
      state = { phase: 'idle' }
      return start()
    },
    async stop() {
      const mine = [...children.entries()]
      children.clear()
      for (const [name, h] of mine) {
        log('stack', `stopping ${name}`)
        try {
          h.kill('SIGTERM')
        } catch {
          /* already gone */
        }
      }
      await Promise.all(
        mine.map(async ([name, h]) => {
          const gone = await Promise.race([h.exited.then(() => true), deps.sleep(cfg.timeouts.stopMs).then(() => false)])
          if (!gone) {
            log('stack', `${name} did not stop in time: forcing it`)
            try {
              h.kill('SIGKILL')
            } catch {
              /* already gone */
            }
          }
        }),
      )
    },
    started: () => [...children.keys()],
    dataDir: () => dataDir,
  }
  return api
}
