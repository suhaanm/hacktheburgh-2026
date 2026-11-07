// data/KILL: the file every Python actuator and safety pipeline polls (MacActuator, mac_check, SafetyPipeline.is_killed, the supervisor's
// watchdog). The in-process flag (kill-flag.ts) only stops THIS app; a separate process with no service running (a standalone
// `mac_check --real`) can only see this file. So the kill switch writes it first, synchronously, before anything that could wait.
// Path rule, as services/agent/understudy_agent/security/paths.py: UNDERSTUDY_DATA_DIR if set, else <repo>/data.
import fs from 'node:fs'
import path from 'node:path'

function repoRoot(from: string, env: Record<string, string | undefined>, exists: (p: string) => boolean): string {
  const fixed = (env.UNDERSTUDY_REPO_ROOT ?? '').trim()
  if (fixed) return path.resolve(fixed)
  let dir = path.resolve(from)
  for (let i = 0; i < 12; i++) {
    if (exists(path.join(dir, 'packages', 'schema', 'sensitive_fields.json'))) return dir
    const parent = path.dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  return path.resolve(from, '../../../..') // apps/desktop/{src,out}/main -> the repository
}

export function killFilePath(env: Record<string, string | undefined> = process.env, from: string = __dirname, exists: (p: string) => boolean = fs.existsSync): string {
  const data = (env.UNDERSTUDY_DATA_DIR ?? '').trim()
  return path.join(data ? path.resolve(data.replace(/^~(?=$|\/)/, process.env.HOME ?? '~')) : path.join(repoRoot(from, env, exists), 'data'), 'KILL')
}

/** The shared data directory (UNDERSTUDY_DATA_DIR, else <repo>/data), as every other part of Understudy resolves it. */
export function dataDirPath(env: Record<string, string | undefined> = process.env, from: string = __dirname, exists: (p: string) => boolean = fs.existsSync): string {
  return path.dirname(killFilePath(env, from, exists))
}

/** data/.token: the secret the release routes want in X-Understudy-Token (0600, rotates every boot). Read per request. Null when absent. */
export function readServiceToken(env: Record<string, string | undefined> = process.env, from: string = __dirname): string | null {
  try {
    const t = fs.readFileSync(path.join(dataDirPath(env, from), '.token'), 'utf8').trim()
    return t.length > 0 ? t : null
  } catch {
    return null
  }
}

export interface KillFile {
  /** Synchronous: the file exists when this returns true. Written to a temp name and renamed, so a reader never sees half a file. */
  write(source: string, at: number): boolean
  remove(): boolean
  path(): string
}

export function createKillFile(opts: { env?: Record<string, string | undefined>; from?: string } = {}): KillFile {
  const env = (): Record<string, string | undefined> => opts.env ?? process.env
  const where = (): string => killFilePath(env(), opts.from ?? __dirname)
  // A test run that did not point UNDERSTUDY_DATA_DIR somewhere private must never touch the shared <repo>/data/KILL: the Python
  // services of every other track poll that file, and a stray write from a unit test would stop their runs.
  const sharedInTest = (): boolean => (env().VITEST ?? '') !== '' && (env().UNDERSTUDY_DATA_DIR ?? '').trim() === ''
  return {
    path: where,
    write(source, at) {
      if (sharedInTest()) return false
      const target = where()
      try {
        fs.mkdirSync(path.dirname(target), { recursive: true })
        const tmp = `${target}.${process.pid}.tmp`
        fs.writeFileSync(tmp, JSON.stringify({ source, at: new Date(at).toISOString(), by: 'desktop' }), { mode: 0o600 })
        fs.renameSync(tmp, target)
        return fs.existsSync(target)
      } catch {
        return false
      }
    },
    remove() {
      if (sharedInTest()) return true
      try {
        fs.rmSync(where(), { force: true })
        return !fs.existsSync(where())
      } catch {
        return false
      }
    },
  }
}

/** Does data/KILL exist right now? (A unit test with no private data directory never looks at the shared file.) */
export function killFileExists(env: Record<string, string | undefined> = process.env, from: string = __dirname): boolean {
  if ((env.VITEST ?? '') !== '' && (env.UNDERSTUDY_DATA_DIR ?? '').trim() === '') return false
  try {
    return fs.existsSync(killFilePath(env, from))
  } catch {
    return false
  }
}
