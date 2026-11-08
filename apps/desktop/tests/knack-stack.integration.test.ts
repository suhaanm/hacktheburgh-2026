// The services lifecycle against the REAL services: Knack starts the engine and the agent itself with `uv run`, in example-data mode, waits for their health, and stops exactly what
// it started. Skipped unless KNACK_STACK_INTEGRATION=1, because it needs `uv`, takes a few minutes the first time (it creates the repository's .venv and generates the demo data) and
// starts two Python processes:
//
//   cd apps/desktop && KNACK_STACK_INTEGRATION=1 npx vitest run tests/knack-stack.integration.test.ts
//
// It asks the system for FREE ports (another checkout, another agent or the owner's own run may hold any fixed number) and uses the repository's own data/demo-home and data/demo-data
// (ignored by version control); it never touches 7700, 7710, 5173 or the sandbox sites on 7801 to 7803 (the sandbox step is left out here: those ports belong to whoever runs the demo,
// and the sites do not take a port from the environment).
import fs from 'node:fs'
import net from 'node:net'
import os from 'node:os'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { createStack } from '../src/main/knack/stack'
import { dataDirId, loopbackGet, realStackDeps } from '../src/main/knack/stack-real'
import type { StackConfig } from '../src/main/knack/stack'

const ON = process.env.KNACK_STACK_INTEGRATION === '1'
const repo = path.resolve(__dirname, '../../..')

/** A port nobody holds right now: the system hands one out when asked for port 0. */
function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address() as net.AddressInfo
      server.close(() => resolve(port))
    })
  })
}

describe.skipIf(!ON)('the services lifecycle with the real services (example data)', () => {
  it(
    'starts the engine and the agent, reports ready, then stops only those and leaves nothing listening',
    async () => {
      const ports = { engine: await freePort(), agent: await freePort(), dashboard: await freePort(), sites: await freePort() }
      const dist = fs.mkdtempSync(path.join(os.tmpdir(), 'knack-dist-'))
      fs.writeFileSync(path.join(dist, 'index.html'), '<!doctype html><title>x</title>')
      const config: StackConfig = {
        repoRoot: repo,
        ports,
        distDir: dist,
        devUrl: null,
        preferDevServer: false,
        dirs: { demo: { home: 'data/demo-home', data: 'data/demo-data' }, live: { home: 'data/live-home', data: 'data/live-data' } },
        mode: 'demo',
        // The sandbox sites bind 7801 to 7803 whatever the environment says, and those ports are not ours: this test never starts them.
        startSites: false,
        timeouts: { engineMs: 240_000, agentMs: 240_000, dashboardMs: 5000, seedMs: 480_000, pollMs: 500, stopMs: 8000 },
      }
      const base = realStackDeps(config)
      const stack = createStack(base)
      const states: string[] = []
      stack.subscribe((s) => states.push(s.phase === 'starting' ? s.step : s.phase))
      try {
        const s = await stack.start()
        expect(s, JSON.stringify(s)).toMatchObject({ phase: 'ready', dashboard: 'dist' })
        expect(stack.started().sort()).toEqual(['agent', 'engine'])
        expect(states).toContain('preparing')
        expect(states.at(-1)).toBe('ready')

        const agent = await loopbackGet(`http://127.0.0.1:${ports.agent}/health`, 3000)
        const engine = await loopbackGet(`http://127.0.0.1:${ports.engine}/health`, 3000)
        expect(engine.ok).toBe(true)
        expect(agent.ok).toBe(true)
        const health = agent.json as { mock?: boolean; data_dir_id?: string }
        expect(health.mock).toBe(true) // example-data mode: mock models
        const demoData = path.join(repo, 'data/demo-data')
        expect(health.data_dir_id).toBe(dataDirId(demoData)) // the agent runs on the demo data directory this app chose
        expect(stack.dataDir()).toBe(demoData)
        expect(s.phase === 'ready' && s.mock).toBe(true)
        expect(fs.existsSync(path.join(demoData, '.token'))).toBe(true) // the per-boot token the proxy adds
        expect(fs.existsSync(path.join(repo, 'data/logs/knack-engine.log'))).toBe(true)
        expect(fs.existsSync(path.join(repo, 'data/logs/knack-agent.log'))).toBe(true)

        // Starting again while it is up attaches to what is there and starts nothing more.
        const again = createStack(base)
        const attached = await again.start()
        expect(attached).toMatchObject({ phase: 'ready', started: [] })
        await again.stop() // holds nothing: the first stack's services are left running
        expect((await loopbackGet(`http://127.0.0.1:${ports.engine}/health`, 3000)).ok).toBe(true)
      } finally {
        await stack.stop()
      }
      // Stopped: nothing listens on the two private ports any more.
      for (const port of [ports.engine, ports.agent]) expect((await loopbackGet(`http://127.0.0.1:${port}/health`, 1500)).ok, `port ${port}`).toBe(false)
      expect(stack.started()).toEqual([])
    },
    900_000,
  )
})
