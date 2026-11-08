import { describe, expect, it } from 'vitest'
import { FAIL_MESSAGES, augmentedPath, createStack, type ChildHandle, type SpawnSpec, type StackConfig, type StackState } from './stack'

const REPO = '/work/knack'
const PORTS = { engine: 17700, agent: 17710, dashboard: 15173, sites: 17801 }

interface World {
  up: Set<number>
  files: Set<string>
  agentDataId: string | null
  agentMock: boolean | null
  uv: string | null
  npm: string | null
  seedCode: number
  synthCode: number
  /** Ports that come up this many fake ms after their service is spawned; absent: the child exits at once (code 1). */
  comesUp: Record<string, number | null>
  /** Ports where some other program already listens. */
  busy: Set<number>
  /** The folders Knack writes to cannot be written (a read-only home). */
  readOnly: boolean
}

function rig(over: Partial<World> = {}, cfgOver: Partial<StackConfig> = {}) {
  const w: World = { up: new Set(), files: new Set([`${REPO}/apps/dashboard/dist/index.html`, `${REPO}/apps/dashboard/package.json`, `${REPO}/services/agent/understudy_agent/sandbox_sites/__main__.py`]), agentDataId: null, agentMock: null, uv: '/opt/homebrew/bin/uv', npm: '/opt/homebrew/bin/npm', seedCode: 0, synthCode: 0, comesUp: { engine: 300, agent: 300, sites: 100, dashboard: 300 }, busy: new Set(), readOnly: false, ...over }
  let clock = 0
  const events: { at: number; fn: () => void }[] = []
  const flush = () => {
    for (const e of events.filter((x) => x.at <= clock).sort((a, b) => a.at - b.at)) {
      events.splice(events.indexOf(e), 1)
      e.fn()
    }
  }
  const spawned: { spec: SpawnSpec; signals: string[]; handle: ChildHandle; exit: (code: number | null) => void }[] = []
  const runs: { spec: SpawnSpec; timeoutMs: number }[] = []
  const states: StackState[] = []
  const portOf = (name: string): number | null => ({ engine: PORTS.engine, agent: PORTS.agent, sites: PORTS.sites, dashboard: PORTS.dashboard })[name] ?? null
  let stubborn = new Set<string>()

  const config: StackConfig = {
    repoRoot: REPO,
    ports: PORTS,
    distDir: `${REPO}/apps/dashboard/dist`,
    devUrl: `http://127.0.0.1:${PORTS.dashboard}`,
    preferDevServer: false,
    dirs: { demo: { home: 'data/demo-home', data: 'data/demo-data' }, live: { home: 'data/live-home', data: 'data/live-data' } },
    mode: 'demo',
    timeouts: { engineMs: 5000, agentMs: 5000, dashboardMs: 3000, seedMs: 60_000, pollMs: 100, stopMs: 1000 },
    ...cfgOver,
  }
  const stack = createStack({
    config,
    get: async (url) => {
      const u = new URL(url)
      const port = Number(u.port)
      if (!w.up.has(port)) return { ok: false }
      return { ok: true, json: port === PORTS.agent ? { ok: true, data_dir_id: w.agentDataId, ...(w.agentMock !== null ? { mock: w.agentMock } : {}) } : { ok: true } }
    },
    spawn: (spec) => {
      let exit: (c: number | null) => void = () => undefined
      const exited = new Promise<number | null>((r) => (exit = r))
      const signals: string[] = []
      const handle: ChildHandle = {
        pid: 1000 + spawned.length,
        exited,
        kill: (sig) => {
          signals.push(sig)
          if (sig === 'SIGKILL' || !stubborn.has(spec.name)) exit(null)
        },
      }
      spawned.push({ spec, signals, handle, exit })
      const delay = w.comesUp[spec.name]
      const port = portOf(spec.name)
      if (delay === null || delay === undefined) exit(1)
      else if (port !== null) events.push({ at: clock + delay, fn: () => void w.up.add(port) })
      return handle
    },
    run: async (spec, timeoutMs) => {
      runs.push({ spec, timeoutMs })
      return { code: spec.name === 'seed' ? w.seedCode : w.synthCode }
    },
    portBusy: async (port) => w.busy.has(port),
    exists: (p) => w.files.has(p),
    mkdirp: (p) => {
      if (w.readOnly) throw new Error(`EROFS: read-only file system, mkdir '${p}'`)
      w.files.add(p)
    },
    touch: (p) => void w.files.add(p),
    findExecutable: (name) => (name === 'uv' ? w.uv : name === 'npm' ? w.npm : null),
    env: () => ({ HOME: '/Users/x', PATH: '/usr/bin:/bin', SECRET_THING: 'kept-out-of-nothing' }),
    dataDirId: (dir) => `id:${dir}`,
    sleep: async (ms) => {
      clock += ms
      flush()
    },
    now: () => clock,
  })
  stack.subscribe((s) => states.push(s))
  return { stack, w, spawned, runs, states, stubborn: (n: string) => (stubborn = new Set([n])) }
}

describe('attaching to a stack that is already running', () => {
  it('starts nothing, and quitting leaves it alone', async () => {
    const r = rig({ up: new Set([PORTS.engine, PORTS.agent]), agentDataId: `id:${REPO}/data` })
    const s = await r.stack.start()
    expect(s).toEqual({ phase: 'ready', started: [], dashboard: 'dist', mock: null })
    expect(r.spawned).toHaveLength(0)
    expect(r.runs).toHaveLength(0)
    expect(r.stack.dataDir()).toBe(`${REPO}/data`) // the agent says it is on the repo's own data directory, so the token and the kill file go there
    await r.stack.stop()
    expect(r.spawned).toHaveLength(0)
  })
  it('falls back to the demo directory when the agent does not say which data directory it uses', async () => {
    const r = rig({ up: new Set([PORTS.engine, PORTS.agent]) })
    await r.stack.start()
    expect(r.stack.dataDir()).toBe(`${REPO}/data/demo-data`)
  })
  it('works without a repository when the services and the bundled dashboard are all there', async () => {
    const r = rig({ up: new Set([PORTS.engine, PORTS.agent]) }, { repoRoot: null })
    expect((await r.stack.start()).phase).toBe('ready')
  })
})

describe('starting the stack the way `make demo` does', () => {
  it('seeds the demo, starts engine, sites and agent in demo mode, and reports ready', async () => {
    const r = rig()
    const s = await r.stack.start()
    expect(s).toEqual({ phase: 'ready', started: ['engine', 'sites', 'agent'], dashboard: 'dist', mock: true })
    expect(r.states.map((x) => (x.phase === 'starting' ? x.step : x.phase))).toEqual(['checking', 'preparing', 'engine', 'agent', 'ready'])
    expect(r.runs.map((x) => x.spec.name)).toEqual(['synth', 'seed']) // the shared synthetic data first (make synth), then the demo story (make demo)
    expect(r.runs[1]!.spec.args).toEqual(['run', '--package', 'understudy-agent', 'python', '-m', 'understudy_engine.demo', 'seed']) // no --reset: a second launch changes nothing
    // The shared synthetic data goes into the repository's own data directory: the synth step has neither the mode's data directory nor its home.
    expect(r.runs[0]!.spec.args).toEqual(['run', '--package', 'understudy-engine', 'understudy', 'synth', '--all'])
    expect(r.runs[0]!.spec.env.UNDERSTUDY_DATA_DIR).toBeUndefined()
    expect(r.runs[0]!.spec.env.UNDERSTUDY_HOME).toBeUndefined()
    expect(r.spawned.map((x) => x.spec.name)).toEqual(['engine', 'sites', 'agent'])
    const engine = r.spawned[0]!.spec
    expect(engine.command).toBe('/opt/homebrew/bin/uv')
    expect(engine.args).toEqual(['run', '--package', 'understudy-agent', 'understudy', 'serve'])
    expect(engine.cwd).toBe(REPO)
    expect(engine.env).toMatchObject({ UNDERSTUDY_MOCK: '1', UNDERSTUDY_X: '1', UNDERSTUDY_HOME: `${REPO}/data/demo-home`, UNDERSTUDY_DATA_DIR: `${REPO}/data/demo-data`, ENGINE_PORT: '17700', AGENT_PORT: '17710' })
    expect(engine.env.PATH?.split(':')).toContain('/opt/homebrew/bin') // a Dock-launched app needs this to find uv
    expect(r.spawned[2]!.spec.args).toEqual(['run', '--package', 'understudy-agent', 'python', '-m', 'understudy_agent.server'])
    expect(r.stack.dataDir()).toBe(`${REPO}/data/demo-data`)
  })

  it('skips the synthetic data step when it is already there, and the sites when they already answer', async () => {
    const r = rig({ files: new Set([`${REPO}/apps/dashboard/dist/index.html`, `${REPO}/data/synthetic`, `${REPO}/services/agent/understudy_agent/sandbox_sites/__main__.py`]), up: new Set([PORTS.sites]) })
    await r.stack.start()
    expect(r.runs.map((x) => x.spec.name)).toEqual(['seed'])
    expect(r.spawned.map((x) => x.spec.name)).toEqual(['engine', 'agent'])
  })

  it('does not start the sandbox sites when the configuration says so (they bind fixed ports a check or a second checkout may not take)', async () => {
    const r = rig({}, { startSites: false })
    const s = await r.stack.start()
    expect(r.spawned.map((x) => x.spec.name)).toEqual(['engine', 'agent'])
    expect(s).toMatchObject({ phase: 'ready', started: ['engine', 'agent'] })
  })

  it('starts only the service that is missing, never a second copy of one that answers', async () => {
    const r = rig({ up: new Set([PORTS.engine]) })
    await r.stack.start()
    expect(r.spawned.map((x) => x.spec.name)).toEqual(['sites', 'agent'])
    expect(r.stack.started()).toEqual(['sites', 'agent'])
  })

  it('starts live the way `make live` does: real models, the isolated live home and data, seeded once behind a marker', async () => {
    const r = rig({}, { mode: 'live' })
    const s = await r.stack.start()
    expect(s).toMatchObject({ phase: 'ready', mock: false })
    expect(r.runs.map((x) => [x.spec.name, x.spec.args.at(-1)])).toEqual([['synth', '--all'], ['seed', '--reset']]) // the shared synthetic data first when it is missing, then the one reset-seed behind its marker
    expect(r.w.files.has(`${REPO}/data/live-data/.understudy-demo-data`)).toBe(true) // the marker that lets the seed reset the isolated data
    expect(r.w.files.has(`${REPO}/data/live-home/.seeded`)).toBe(true)
    const env = r.spawned[0]!.spec.env
    expect(env).toMatchObject({ UNDERSTUDY_MOCK: '0', UNDERSTUDY_HOME: `${REPO}/data/live-home`, UNDERSTUDY_DATA_DIR: `${REPO}/data/live-data` })
    expect(env.UNDERSTUDY_X).toBeUndefined() // the layers come from the product defaults, not from this app
    expect(r.stack.dataDir()).toBe(`${REPO}/data/live-data`)
    expect(r.stack.mode()).toBe('live')
  })

  it('does not seed live data a second time', async () => {
    const r = rig({ files: new Set([`${REPO}/apps/dashboard/dist/index.html`, `${REPO}/data/synthetic`, `${REPO}/data/live-home/.seeded`]) }, { mode: 'live' })
    await r.stack.start()
    expect(r.runs).toHaveLength(0)
  })

  it('reports what the agent service says about its models when it attaches', async () => {
    const live = rig({ up: new Set([PORTS.engine, PORTS.agent]), agentMock: false })
    expect(await live.stack.start()).toMatchObject({ mock: false })
    const mock = rig({ up: new Set([PORTS.engine, PORTS.agent]), agentMock: true })
    expect(await mock.stack.start()).toMatchObject({ mock: true })
  })

  it('switches models by stopping what it started and starting again in the other mode; what it did not start is left alone', async () => {
    const r = rig()
    await r.stack.start()
    expect(r.stack.mode()).toBe('demo')
    r.w.up.clear() // the services go down with their processes
    r.stack.setMode('live')
    const s = await r.stack.restart()
    expect(s).toMatchObject({ phase: 'ready', mock: false })
    expect(r.spawned.slice(0, 3).every((x) => x.signals.includes('SIGTERM'))).toBe(true)
    expect(r.spawned.slice(3).map((x) => x.spec.env.UNDERSTUDY_MOCK)).toEqual(['0', '0', '0'])
    const attached = rig({ up: new Set([PORTS.engine, PORTS.agent]), agentMock: true })
    await attached.stack.start()
    attached.stack.setMode('live')
    await attached.stack.restart()
    expect(attached.spawned).toHaveLength(0) // not ours: never stopped, never replaced
  })

  it('shares one start between concurrent callers', async () => {
    const r = rig()
    const [a, b] = await Promise.all([r.stack.start(), r.stack.start()])
    expect(a).toBe(b)
    expect(r.spawned.filter((x) => x.spec.name === 'engine')).toHaveLength(1)
  })

  it('starts the dashboard dev server only when there is no built copy and nothing answers', async () => {
    const noDist = new Set([`${REPO}/apps/dashboard/package.json`])
    const r = rig({ files: noDist, up: new Set([PORTS.engine, PORTS.agent]) })
    const s = await r.stack.start()
    expect(s).toMatchObject({ phase: 'ready', dashboard: 'dev-server' })
    expect(r.spawned[0]!.spec.args).toEqual(['run', 'dev', '--', '--host', '127.0.0.1', '--port', '15173'])
    expect(r.spawned[0]!.spec.cwd).toBe(`${REPO}/apps/dashboard`)
  })

  it('prefers a dev server that answers over the built copy only when asked to (development)', async () => {
    const dev = rig({ up: new Set([PORTS.engine, PORTS.agent, PORTS.dashboard]) }, { preferDevServer: true })
    expect(await dev.stack.start()).toMatchObject({ dashboard: 'dev-server' })
    const prod = rig({ up: new Set([PORTS.engine, PORTS.agent, PORTS.dashboard]) })
    expect(await prod.stack.start()).toMatchObject({ dashboard: 'dist' })
  })
})

describe('stopping', () => {
  it('stops only what it started: SIGTERM to each group, SIGKILL to one that ignores it', async () => {
    const r = rig()
    r.stubborn('agent')
    await r.stack.start()
    await r.stack.stop()
    expect(r.spawned.map((x) => [x.spec.name, x.signals])).toEqual([
      ['engine', ['SIGTERM']],
      ['sites', ['SIGTERM']],
      ['agent', ['SIGTERM', 'SIGKILL']],
    ])
    expect(r.stack.started()).toEqual([])
  })
})

describe('failures end in one plain message and a retry', () => {
  it('says plainly when uv cannot be found, and starts once it can', async () => {
    const r = rig({ uv: null })
    const s = await r.stack.start()
    expect(s).toEqual({ phase: 'failed', code: 'uv_missing', message: FAIL_MESSAGES.uv_missing })
    expect(r.spawned).toHaveLength(0)
    r.w.uv = '/opt/homebrew/bin/uv'
    expect((await r.stack.retry()).phase).toBe('ready')
  })

  it('fails when the engine ends at once, naming the log, then recovers on retry without starting the engine twice', async () => {
    const r = rig({ comesUp: { engine: null, agent: 300, sites: 100 } })
    const s = await r.stack.start()
    expect(s).toMatchObject({ phase: 'failed', code: 'engine_failed', message: 'The engine did not start.', hint: 'See data/logs/knack-engine.log.' })
    r.w.comesUp.engine = 300
    expect((await r.stack.retry()).phase).toBe('ready')
    expect(r.spawned.filter((x) => x.spec.name === 'engine')).toHaveLength(2) // the first one had ended; the retry started a new one
  })

  it('gives up on a service that never answers', async () => {
    const r = rig({ comesUp: { engine: 999_999, agent: 300, sites: 100 } })
    expect(await r.stack.start()).toMatchObject({ phase: 'failed', code: 'engine_failed' })
  })

  it('fails with the agent message when only the agent never answers', async () => {
    const r = rig({ comesUp: { engine: 300, agent: 999_999, sites: 100 } })
    expect(await r.stack.start()).toMatchObject({ phase: 'failed', code: 'agent_failed', message: 'The agent did not start.' })
  })

  it('fails when the demo data cannot be prepared', async () => {
    expect(await rig({ seedCode: 1 }).stack.start()).toMatchObject({ phase: 'failed', code: 'prepare_failed' })
    expect(await rig({ synthCode: 1 }).stack.start()).toMatchObject({ phase: 'failed', code: 'prepare_failed' })
  })

  it('says it cannot find the project folder when nothing is running and there is no repository', async () => {
    expect(await rig({}, { repoRoot: null }).stack.start()).toMatchObject({ phase: 'failed', code: 'no_repo', message: 'Knack cannot find its project folder.' })
  })

  it('says the dashboard is not built when there is no copy, no dev server and no way to start one', async () => {
    const r = rig({ files: new Set(), up: new Set([PORTS.engine, PORTS.agent]) }, { devUrl: null })
    expect(await r.stack.start()).toMatchObject({ phase: 'failed', code: 'dashboard_missing' })
  })

  it('every failure message is one short plain sentence', () => {
    for (const m of Object.values(FAIL_MESSAGES)) expect(m).toMatch(/^[A-Z][^.]{8,60}\.$/)
  })
})

describe('the child PATH', () => {
  it('adds the usual tool directories once, keeping what was there first', () => {
    expect(augmentedPath('/usr/bin:/bin', '/Users/x').split(':')).toEqual(['/usr/bin', '/bin', '/opt/homebrew/bin', '/usr/local/bin', '/Users/x/.local/bin', '/Users/x/.cargo/bin', '/usr/sbin', '/sbin'])
    expect(augmentedPath(undefined, '/Users/x').startsWith('/opt/homebrew/bin')).toBe(true)
  })
})


const settle = async (): Promise<void> => {
  for (let i = 0; i < 20; i++) await new Promise((r) => setTimeout(r, 0))
}

describe('a service this app started stops by itself', () => {
  it('is started again, a little later each time, and the stack stays ready', async () => {
    const r = rig()
    await r.stack.start()
    expect(r.spawned.map((x) => x.spec.name)).toEqual(['engine', 'sites', 'agent'])
    r.w.up.delete(PORTS.engine) // the engine crashed
    r.spawned[0]!.exit(139)
    await settle()
    expect(r.spawned.filter((x) => x.spec.name === 'engine')).toHaveLength(2)
    expect(r.spawned.at(-1)!.spec.args).toEqual(['run', '--package', 'understudy-agent', 'understudy', 'serve'])
    expect(r.stack.state().phase).toBe('ready')
    expect(r.stack.started()).toContain('engine')
  })
  it('after three stops in ten minutes it gives up and says so in one plain line', async () => {
    const r = rig()
    await r.stack.start()
    for (let i = 0; i < 4; i++) {
      r.w.up.delete(PORTS.engine)
      const engines = r.spawned.filter((x) => x.spec.name === 'engine')
      engines.at(-1)!.exit(1)
      await settle()
    }
    const s = r.stack.state()
    expect(s.phase).toBe('failed')
    if (s.phase === 'failed') {
      expect(s.code).toBe('engine_failed')
      expect(s.hint).toContain('would not start again')
      expect(s.hint).not.toMatch(/Error|EACCES|\/Users/)
    }
    expect(r.spawned.filter((x) => x.spec.name === 'engine')).toHaveLength(4) // the first and three more
  })
  it('a service stopped on purpose (quit, the models switch) is never started again', async () => {
    const r = rig()
    await r.stack.start()
    await r.stack.stop()
    await settle()
    expect(r.spawned.filter((x) => x.spec.name === 'engine')).toHaveLength(1)
    expect(r.stack.started()).toEqual([])
  })
  it('a service that was already running (not started by this app) is never supervised or started', async () => {
    const r = rig({ up: new Set([PORTS.engine, PORTS.agent]), agentDataId: `id:${REPO}/data` })
    await r.stack.start()
    r.w.up.delete(PORTS.engine)
    await settle()
    expect(r.spawned).toHaveLength(0)
  })
})

describe('a port that something else holds', () => {
  it('is said at once and plainly, before anything is started', async () => {
    const r = rig({ busy: new Set([PORTS.engine]) })
    const s = await r.stack.start()
    expect(s).toMatchObject({ phase: 'failed', code: 'port_busy', message: FAIL_MESSAGES.port_busy })
    expect(r.spawned).toHaveLength(0)
    if (s.phase === 'failed') expect(s.hint).toContain('ENGINE_PORT')
  })
  it('a port held by our own running service is attached to, not an error', async () => {
    const r = rig({ up: new Set([PORTS.engine, PORTS.agent]), busy: new Set([PORTS.engine, PORTS.agent]), agentDataId: `id:${REPO}/data` })
    expect((await r.stack.start()).phase).toBe('ready')
  })
})

describe('a home that cannot be written', () => {
  it('says that Knack cannot write to its data folder, in words, without the system message or any path', async () => {
    const r = rig({ readOnly: true })
    const s = await r.stack.start()
    expect(s).toMatchObject({ phase: 'failed', code: 'prepare_failed', hint: 'Knack cannot write to its data folder.' })
    expect(JSON.stringify(s)).not.toMatch(/EROFS|read-only file system|\/work\/knack/)
    expect(r.spawned).toHaveLength(0)
  })
})
