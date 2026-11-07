import { describe, expect, it } from 'vitest'
import { applyModeEnv, applyStackEnv, portsFromEnv, resolveRepoRoot, resolveStackConfig, type ConfigInput } from './stack-config'

const REPO = '/work/knack'
const repoFiles = [`${REPO}/scripts/dev.sh`, `${REPO}/services/agent`, `${REPO}/apps/dashboard`]
const input = (over: Partial<ConfigInput> & { files?: string[] } = {}): ConfigInput => {
  const files = new Set(over.files ?? repoFiles)
  return { env: {}, appPath: `${REPO}/apps/desktop`, isPackaged: false, exists: (p) => files.has(p), readFile: () => { throw new Error('none') }, ...over }
}

describe('finding the repository', () => {
  it('uses KNACK_REPO when it holds the project', () => {
    expect(resolveRepoRoot(input({ env: { KNACK_REPO: REPO }, appPath: '/Applications/Knack.app/Contents/Resources/app.asar' }))).toBe(REPO)
  })
  it('ignores KNACK_REPO that does not hold the project, and keeps looking', () => {
    expect(resolveRepoRoot(input({ env: { KNACK_REPO: '/nowhere' } }))).toBe(REPO)
  })
  it('reads knack-config.json next to the packaged resources (a local build remembers where it was built)', () => {
    const r = resolveRepoRoot(input({ appPath: '/Applications/Knack.app/Contents/Resources/app.asar', resourcesPath: '/Applications/Knack.app/Contents/Resources', readFile: () => JSON.stringify({ repo: REPO }) }))
    expect(r).toBe(REPO)
  })
  it('walks up from the app folder when running from source', () => {
    expect(resolveRepoRoot(input())).toBe(REPO)
  })
  it('is null when the app is packaged and nothing says where the project is', () => {
    expect(resolveRepoRoot(input({ appPath: '/Applications/Knack.app/Contents/Resources/app.asar', resourcesPath: '/Applications/Knack.app/Contents/Resources' }))).toBeNull()
  })
})

describe('ports', () => {
  it('reads the service URLs first, then the dev.sh port variables, then the defaults', () => {
    expect(portsFromEnv({})).toEqual({ engine: 7700, agent: 7710, dashboard: 5173, sites: 7801 })
    expect(portsFromEnv({ ENGINE_PORT: '17700', AGENT_PORT: '17710', DASHBOARD_PORT: '15173', SANDBOX_PORT_BASE: '17801' })).toEqual({ engine: 17700, agent: 17710, dashboard: 15173, sites: 17801 })
    expect(portsFromEnv({ UNDERSTUDY_ENGINE_URL: 'http://127.0.0.1:18800', ENGINE_PORT: '17700' }).engine).toBe(18800)
    expect(portsFromEnv({ ENGINE_PORT: 'abc', AGENT_PORT: '99999' })).toMatchObject({ engine: 7700, agent: 7710 })
  })
  it('makes this app agree with the stack: loopback URLs and the data directory, without overriding what is set', () => {
    const env: Record<string, string | undefined> = { UNDERSTUDY_AGENT_URL: 'http://127.0.0.1:9999' }
    applyStackEnv(env, { engine: 17700, agent: 17710, dashboard: 15173, sites: 17801 }, '/work/knack/data/demo-data')
    expect(env).toEqual({ UNDERSTUDY_ENGINE_URL: 'http://127.0.0.1:17700', UNDERSTUDY_AGENT_URL: 'http://127.0.0.1:9999', UNDERSTUDY_DASHBOARD_URL: 'http://127.0.0.1:15173', UNDERSTUDY_DATA_DIR: '/work/knack/data/demo-data' })
  })
})

describe('the stack configuration', () => {
  it('in development prefers a running dev server, falls back to apps/dashboard/dist, and is in demo mode', () => {
    const c = resolveStackConfig(input({ files: [...repoFiles, `${REPO}/apps/dashboard/dist/index.html`] }))
    expect(c).toMatchObject({ repoRoot: REPO, distDir: `${REPO}/apps/dashboard/dist`, devUrl: 'http://127.0.0.1:5173', preferDevServer: true, mode: 'demo' })
    expect(c.dirs).toEqual({ demo: { home: 'data/demo-home', data: 'data/demo-data' }, live: { home: 'data/live-home', data: 'data/live-data' } })
  })
  it('KNACK_DASHBOARD=dist makes development serve the built copy', () => {
    expect(resolveStackConfig(input({ env: { KNACK_DASHBOARD: 'dist' } })).preferDevServer).toBe(false)
  })
  it("gives this app's own process the mode's environment, so its model port, kill file and token reads agree with the services", () => {
    const cfg = resolveStackConfig(input())
    const live: Record<string, string | undefined> = {}
    applyModeEnv(live, cfg, 'live')
    expect(live).toEqual({ UNDERSTUDY_MOCK: '0', UNDERSTUDY_HOME: `${REPO}/data/live-home`, UNDERSTUDY_DATA_DIR: `${REPO}/data/live-data` })
    const demo: Record<string, string | undefined> = {}
    applyModeEnv(demo, cfg, 'demo')
    expect(demo).toEqual({ UNDERSTUDY_MOCK: '1', UNDERSTUDY_X: '1', UNDERSTUDY_HOME: `${REPO}/data/demo-home`, UNDERSTUDY_DATA_DIR: `${REPO}/data/demo-data` })
    const none: Record<string, string | undefined> = {}
    applyModeEnv(none, { ...cfg, repoRoot: null }, 'demo')
    expect(none.UNDERSTUDY_DATA_DIR).toBeUndefined()
  })
  it('packaged: serves the bundled dashboard, never looks for a dev server', () => {
    const res = '/Applications/Knack.app/Contents/Resources'
    const c = resolveStackConfig(input({ isPackaged: true, appPath: `${res}/app.asar`, resourcesPath: res, env: { KNACK_REPO: REPO }, files: [...repoFiles, `${res}/dashboard/index.html`] }))
    expect(c).toMatchObject({ distDir: `${res}/dashboard`, devUrl: null, preferDevServer: false, repoRoot: REPO })
  })
})
