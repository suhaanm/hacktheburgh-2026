// Models off only because the model service could not be reached at start: keep trying, lightly, and bring the app back by itself.
//
// The mode (live models or models off) is decided once, when the app starts, because the services, the data folders and the model port are all built for it. A Mac
// that is busy at launch (a load average several times its cores) can fail the first checks, and that used to cost the whole session. Now, when the decision ended in
// `boot_check_failed` while the worker's switch is on and a key is there, this watcher runs the same check again every 20 seconds for as long as the app runs, and
// when the service answers it reopens the app once, when nothing is running, and says so in one calm line. Everything it reaches is injected, so the tests use fakes:
// it opens no network connection, window or process of its own.
import { boundedBootCheck } from './model-mode'

export const RECOVERY_INTERVAL_MS = 20_000
export const RECOVERY_CHECK_LIMIT_MS = 12_000
/** After an automatic reopening, no second one for this long (a service that passes here and fails at start must not make the app restart in a loop). */
export const RECOVERY_MIN_GAP_MS = 15 * 60_000
/** The one calm line, said just before the app reopens. */
export const RECOVERED_LINE = 'The model service answered. Knack is reopening to switch the models on.'
/** The marker the reopened app carries (in its arguments), so it knows it was reopened by this and when. */
export const RECOVERED_ARG = '--knack-recovered='

export interface RecoveryTimers {
  set(fn: () => void, ms: number): unknown
  clear(handle: unknown): void
}
const realTimers: RecoveryTimers = { set: (fn, ms) => setTimeout(fn, ms), clear: (h) => clearTimeout(h as ReturnType<typeof setTimeout>) }

export interface ModelRecoveryDeps {
  /** One attempt of the models boot check (the same check the start used). */
  check: () => Promise<boolean>
  /** The worker's switch is still on and a key is still there; read at every look, since both can change while the app runs. */
  wanted: () => boolean
  /** Nothing is running that a reopening would cut: no task, no run, no voice conversation. */
  idle: () => boolean
  /** Reopen the app (the shell's relaunch: the environment is put back first, the services stop with it). */
  relaunch: () => void
  /** The one calm line (a notification). */
  say: (line: string) => void
  log: (...args: unknown[]) => void
  now?: () => number
  /** When this process was itself opened by a recovery (from RECOVERED_ARG), else null. */
  recoveredAtMs?: number | null
  intervalMs?: number
  limitMs?: number
  timers?: RecoveryTimers
  wait?: (ms: number) => Promise<void>
}

export type RecoveryPhase = 'idle' | 'watching' | 'waiting_for_idle' | 'reopening' | 'stopped'

export interface ModelRecovery {
  start(): void
  stop(): void
  phase(): RecoveryPhase
  /** How many checks have run (a test and diagnostics number; no content). */
  looks(): number
}

/** The reopening time from the arguments of this process (`--knack-recovered=<epoch ms>`), or null. */
export function recoveredAtFromArgs(argv: readonly string[]): number | null {
  const a = argv.find((x) => x.startsWith(RECOVERED_ARG))
  if (!a) return null
  const n = Number(a.slice(RECOVERED_ARG.length))
  return Number.isFinite(n) && n > 0 ? n : null
}

/** The arguments for the reopened app: this process's own, with the marker set to `now`. */
export function relaunchArgs(argv: readonly string[], now: number): string[] {
  return [...argv.filter((x) => !x.startsWith(RECOVERED_ARG)), `${RECOVERED_ARG}${Math.trunc(now)}`]
}

export function createModelRecovery(d: ModelRecoveryDeps): ModelRecovery {
  const timers = d.timers ?? realTimers
  const now = d.now ?? Date.now
  const interval = d.intervalMs ?? RECOVERY_INTERVAL_MS
  const limit = d.limitMs ?? RECOVERY_CHECK_LIMIT_MS
  let phase: RecoveryPhase = 'idle'
  let handle: unknown = null
  let looks = 0
  let busy = false
  // Read again after an await: stop() may have run meanwhile (the narrowing of `phase` must not outlive the wait).
  const current = (): RecoveryPhase => phase

  // A reopening this recent made this process: the watcher still looks, but does not reopen again until the gap has passed.
  const mayReopen = (): boolean => d.recoveredAtMs == null || now() - d.recoveredAtMs >= RECOVERY_MIN_GAP_MS

  const schedule = (): void => {
    if (phase === 'stopped' || phase === 'reopening') return
    handle = timers.set(() => void tick(), interval)
  }

  async function tick(): Promise<void> {
    handle = null
    if (phase === 'stopped' || phase === 'reopening' || busy) return
    if (!d.wanted()) {
      phase = 'watching'
      return schedule()
    }
    busy = true
    let ok = false
    try {
      looks += 1
      ok = await boundedBootCheck(d.check, limit, d.wait)
    } finally {
      busy = false
    }
    if (current() === 'stopped') return
    if (!ok || !d.wanted()) {
      phase = 'watching'
      return schedule()
    }
    // The service answers. Reopen only when nothing is running and the last automatic reopening is not recent; otherwise look again at the next turn (the check is light).
    if (!d.idle() || !mayReopen()) {
      phase = 'waiting_for_idle'
      return schedule()
    }
    phase = 'reopening'
    d.log('knack', 'the model service answers: reopening to switch the models on')
    try {
      d.say(RECOVERED_LINE)
    } catch {
      /* a line that cannot be shown must not stop the recovery */
    }
    d.relaunch()
  }

  return {
    start() {
      if (phase !== 'idle') return
      phase = 'watching'
      schedule()
    },
    stop() {
      phase = 'stopped'
      if (handle !== null) timers.clear(handle)
      handle = null
    },
    phase: () => phase,
    looks: () => looks,
  }
}

/** The environment keys the app changes for the mode it chose (the model port, the data folders, the service addresses); a reopened app must start from what the launch gave it. */
export const MODE_ENV_KEYS: readonly string[] = ['UNDERSTUDY_MOCK', 'UNDERSTUDY_X', 'UNDERSTUDY_HOME', 'UNDERSTUDY_DATA_DIR', 'UNDERSTUDY_ENGINE_URL', 'UNDERSTUDY_AGENT_URL', 'UNDERSTUDY_DASHBOARD_URL', 'KNACK_MODELS_REASON']

export function snapshotEnv(env: Record<string, string | undefined>, keys: readonly string[] = MODE_ENV_KEYS): Record<string, string | undefined> {
  return Object.fromEntries(keys.map((k) => [k, env[k]]))
}

/** Puts the snapshot back, deleting a key the launch did not have. */
export function restoreEnv(env: Record<string, string | undefined>, snap: Record<string, string | undefined>): void {
  for (const [k, v] of Object.entries(snap)) {
    if (v === undefined) delete env[k]
    else env[k] = v
  }
}
