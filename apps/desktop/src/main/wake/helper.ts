// The supervisor of the Hey Knack listener: starts it as a child process, reads its closed JSON lines, restarts it after a transient failure
// (with a growing pause and a cap), and never restarts it after a failure the worker has to fix. `stop()` ends the child, which releases the
// microphone. Everything that touches the world is injected (`spawn`, timers), so the tests run with a fake child and no process.
//
// Never: log or keep a line's text, pass the child any argument that is not ours, give it a pipe for stderr (it is ignored), start it when
// the binary is absent (the app then runs without it and says so in one plain line).
import { FINAL_CODES, createLineSplitter, parseHelperLine, type HelperErrorCode } from './helper-protocol'

export interface ChildLike {
  readonly pid?: number
  stdout: { on(event: 'data', cb: (chunk: Buffer | string) => void): unknown }
  stdin?: { end(): unknown } | null
  on(event: 'exit', cb: (code: number | null, signal: string | null) => void): unknown
  on(event: 'error', cb: (err: Error) => void): unknown
  kill(signal?: NodeJS.Signals): boolean
}

export type SpawnFn = (file: string, args: readonly string[]) => ChildLike

export type HelperState = 'stopped' | 'starting' | 'listening' | 'backoff' | 'blocked'
export type BlockedCode = HelperErrorCode | 'binary_missing' | 'protocol' | 'crash_loop' | 'spawn_failed'
export interface HelperStatus {
  state: HelperState
  /** Why it is blocked (state 'blocked'), or the last transient failure (state 'backoff'). */
  code: BlockedCode | null
}

export interface HelperDeps {
  /** Absolute path of the built helper, or null when there is none for this platform. */
  binaryPath: string | null
  exists: (file: string) => boolean
  spawn: SpawnFn
  args?: readonly string[]
  onHeard: () => void
  onStatus?: (s: HelperStatus) => void
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (h: unknown) => void
  now?: () => number
  /** Pauses before each restart; the last one repeats. */
  backoffMs?: readonly number[]
  /** More than this many unexpected exits inside `crashWindowMs` ends the restarts (a crash loop). */
  maxCrashes?: number
  crashWindowMs?: number
  killAfterMs?: number
}

export interface HelperSupervisor {
  start(): void
  /** Ends the child (the microphone is released) and cancels any pending restart. */
  stop(): void
  status(): HelperStatus
  /** Clears a 'blocked' state so the next start() tries again (the worker fixed the permission). */
  unblock(): void
}

export function createHelperSupervisor(d: HelperDeps): HelperSupervisor {
  const setT = d.setTimer ?? ((fn, ms) => setTimeout(fn, ms))
  const clearT = d.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>))
  const now = d.now ?? Date.now
  const backoff = d.backoffMs ?? [1000, 2000, 4000, 8000, 15000, 30000]
  const maxCrashes = d.maxCrashes ?? 5
  const crashWindow = d.crashWindowMs ?? 10 * 60_000
  const killAfter = d.killAfterMs ?? 1500

  let status: HelperStatus = { state: 'stopped', code: null }
  let child: ChildLike | null = null
  let wanted = false
  let restartTimer: unknown = null
  let attempt = 0
  let crashes: number[] = []
  let generation = 0

  const set = (s: HelperStatus): void => {
    if (s.state === status.state && s.code === status.code) return
    status = s
    d.onStatus?.(s)
  }

  const killChild = (c: ChildLike): void => {
    try {
      c.stdin?.end()
    } catch {
      /* already closed */
    }
    try {
      c.kill('SIGTERM')
    } catch {
      /* already gone */
    }
    const t = setT(() => {
      try {
        c.kill('SIGKILL')
      } catch {
        /* already gone */
      }
    }, killAfter)
    c.on('exit', () => clearT(t))
  }

  const block = (code: BlockedCode): void => {
    wanted = false
    if (child) {
      const c = child
      child = null
      generation += 1
      killChild(c)
    }
    set({ state: 'blocked', code })
  }

  function spawnNow(): void {
    restartTimer = null
    if (!wanted || child) return
    if (!d.binaryPath || !d.exists(d.binaryPath)) return block('binary_missing')
    const gen = ++generation
    let c: ChildLike
    try {
      c = d.spawn(d.binaryPath, d.args ?? [])
    } catch {
      return block('spawn_failed')
    }
    child = c
    set({ state: 'starting', code: null })
    const splitter = createLineSplitter()
    c.stdout.on('data', (chunk) => {
      if (gen !== generation) return
      const { lines, overflow } = splitter.push(typeof chunk === 'string' ? chunk : chunk.toString('utf8'))
      if (overflow) return block('protocol')
      for (const line of lines) {
        const p = parseHelperLine(line)
        if (!p.ok) return block('protocol') // a line that is not one of ours: stop the helper, keep nothing
        const e = p.event
        if (e.event === 'ready') {
          attempt = 0
          set({ state: 'listening', code: null })
        } else if (e.event === 'heard') {
          if (status.state === 'listening') d.onHeard()
        } else if (FINAL_CODES.has(e.code)) {
          return block(e.code)
        } else {
          set({ state: 'backoff', code: e.code })
        }
      }
    })
    c.on('error', () => {
      if (gen === generation && child === c) {
        child = null
        generation += 1
        block('spawn_failed')
      }
    })
    c.on('exit', () => {
      if (gen !== generation || child !== c) return // we asked for it, or a newer child replaced it
      child = null
      if (!wanted) return
      const t = now()
      crashes = crashes.filter((x) => t - x < crashWindow)
      crashes.push(t)
      if (crashes.length > maxCrashes) return block('crash_loop')
      const lastCode = status.state === 'backoff' ? status.code : 'internal'
      set({ state: 'backoff', code: lastCode })
      const wait = backoff[Math.min(attempt, backoff.length - 1)]
      attempt += 1
      restartTimer = setT(spawnNow, wait)
    })
  }

  return {
    start() {
      if (wanted || status.state === 'blocked') return
      wanted = true
      spawnNow()
    },
    stop() {
      wanted = false
      if (restartTimer !== null) clearT(restartTimer)
      restartTimer = null
      if (child) {
        const c = child
        child = null
        generation += 1
        killChild(c)
      }
      if (status.state !== 'blocked') set({ state: 'stopped', code: null })
    },
    status: () => status,
    unblock() {
      if (status.state === 'blocked') {
        attempt = 0
        crashes = []
        set({ state: 'stopped', code: null })
      }
    },
  }
}
