// Where things are, for the services lifecycle (stack.ts): the repository, the ports, the built dashboard. Pure: the file system is injected.
//
// The repository comes from, in order: KNACK_REPO, a `knack-config.json` that the local build writes next to the app's resources (so a Knack.app built on
// this laptop finds the project it was built from), then the folders above the app (running from source: apps/desktop is two levels down).
import path from 'node:path'
import type { StackConfig, StackMode } from './stack'

export interface ConfigInput {
  env: Record<string, string | undefined>
  /** app.getAppPath(): apps/desktop in development; inside the asar when packaged. */
  appPath: string
  /** process.resourcesPath when packaged. */
  resourcesPath?: string
  isPackaged: boolean
  exists: (p: string) => boolean
  readFile: (p: string) => string
}

const isRepo = (dir: string, exists: (p: string) => boolean): boolean => exists(path.join(dir, 'scripts', 'dev.sh')) && exists(path.join(dir, 'services', 'agent')) && exists(path.join(dir, 'apps', 'dashboard'))

export function resolveRepoRoot(i: ConfigInput): string | null {
  const fromEnv = (i.env.KNACK_REPO ?? '').trim() || (i.env.UNDERSTUDY_REPO_ROOT ?? '').trim()
  if (fromEnv && isRepo(path.resolve(fromEnv), i.exists)) return path.resolve(fromEnv)
  if (i.resourcesPath) {
    try {
      const cfg = JSON.parse(i.readFile(path.join(i.resourcesPath, 'knack-config.json'))) as { repo?: unknown }
      if (typeof cfg.repo === 'string' && isRepo(path.resolve(cfg.repo), i.exists)) return path.resolve(cfg.repo)
    } catch {
      /* no config file: not a local build */
    }
  }
  let dir = path.resolve(i.appPath)
  for (let k = 0; k < 6; k++) {
    if (isRepo(dir, i.exists)) return dir
    const parent = path.dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  return null
}

const portOf = (url: string | undefined): number | null => {
  try {
    const p = Number(new URL(url ?? '').port)
    return Number.isInteger(p) && p > 0 && p < 65536 ? p : null
  } catch {
    return null
  }
}
const num = (v: string | undefined): number | null => {
  const n = Number(v)
  return Number.isInteger(n) && n > 0 && n < 65536 ? n : null
}

/** Ports the way dev.sh and the desktop clients read them: UNDERSTUDY_*_URL, then ENGINE_PORT / AGENT_PORT / DASHBOARD_PORT, then 7700 / 7710 / 5173. */
export function portsFromEnv(env: Record<string, string | undefined>): StackConfig['ports'] {
  return {
    engine: portOf(env.UNDERSTUDY_ENGINE_URL) ?? num(env.ENGINE_PORT) ?? 7700,
    agent: portOf(env.UNDERSTUDY_AGENT_URL) ?? num(env.AGENT_PORT) ?? 7710,
    dashboard: portOf(env.UNDERSTUDY_DASHBOARD_URL) ?? num(env.DASHBOARD_PORT) ?? 5173,
    sites: num(env.SANDBOX_PORT_BASE) ?? 7801,
  }
}

/** The environment of this app itself, so its own clients and the kill file agree with the stack it attaches to (loopback URLs only). */
export function applyStackEnv(env: Record<string, string | undefined>, ports: StackConfig['ports'], dataDir: string | null): void {
  env.UNDERSTUDY_ENGINE_URL ??= `http://127.0.0.1:${ports.engine}`
  env.UNDERSTUDY_AGENT_URL ??= `http://127.0.0.1:${ports.agent}`
  env.UNDERSTUDY_DASHBOARD_URL ??= `http://127.0.0.1:${ports.dashboard}`
  if (dataDir) env.UNDERSTUDY_DATA_DIR = dataDir
}

/** The desktop process's own environment for the mode the stack will run in, so its model port, kill file and token reads agree with the services (make live / make demo). */
export function applyModeEnv(env: Record<string, string | undefined>, cfg: Pick<StackConfig, 'repoRoot' | 'dirs'>, mode: StackMode): void {
  env.UNDERSTUDY_MOCK = mode === 'live' ? '0' : '1'
  if (mode === 'demo') env.UNDERSTUDY_X = '1'
  if (cfg.repoRoot) {
    env.UNDERSTUDY_HOME = path.join(cfg.repoRoot, cfg.dirs[mode].home)
    env.UNDERSTUDY_DATA_DIR = path.join(cfg.repoRoot, cfg.dirs[mode].data)
  }
}

export function resolveStackConfig(i: ConfigInput): StackConfig {
  const repoRoot = resolveRepoRoot(i)
  const ports = portsFromEnv(i.env)
  // The built dashboard: bundled in the packaged app (resources/dashboard), else the repository's apps/dashboard/dist.
  const bundled = i.resourcesPath ? path.join(i.resourcesPath, 'dashboard') : null
  const inRepo = repoRoot ? path.join(repoRoot, 'apps', 'dashboard', 'dist') : null
  const distDir = [bundled, inRepo].find((d): d is string => d !== null && i.exists(path.join(d, 'index.html'))) ?? inRepo
  return {
    repoRoot,
    ports,
    distDir,
    devUrl: i.isPackaged ? null : `http://127.0.0.1:${ports.dashboard}`,
    preferDevServer: !i.isPackaged && (i.env.KNACK_DASHBOARD ?? '') !== 'dist',
    dirs: { demo: { home: 'data/demo-home', data: 'data/demo-data' }, live: { home: 'data/live-home', data: 'data/live-data' } },
    mode: 'demo',
    timeouts: { engineMs: 90_000, agentMs: 90_000, dashboardMs: 45_000, seedMs: 120_000, pollMs: 400, stopMs: 4000 },
  }
}
