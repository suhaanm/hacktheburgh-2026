// Shared fakes for the awareness tests: manual timers, a recording sink, scripted probes and ports. Nothing here touches the machine.
import type { ConsoleProbe, FrontmostSource, ScreenShareProbe } from './probes'
import type { ConsoleState } from './probes'
import type { GlancePort, GlancePortRequest, GlancePortResponse, SecureInputState, Timers } from './types'
import type { PowerLike } from './index'
import type { PostFn } from './events'

export interface ManualTimers extends Timers {
  active(): number
  intervals(): number[]
  /** Advance the fake clock by ms and fire every interval due in that span, in order. */
  advance(ms: number): void
  clock(): number
  created(): number
}

export function manualTimers(): ManualTimers {
  let now = 0
  let nextId = 1
  let created = 0
  const timers = new Map<number, { fn: () => void; every: number; due: number }>()
  return {
    setInterval(fn, ms) {
      const id = nextId++
      created++
      timers.set(id, { fn, every: ms, due: now + ms })
      return id
    },
    clearInterval(h) {
      timers.delete(h as number)
    },
    active: () => timers.size,
    intervals: () => [...timers.values()].map((t) => t.every),
    created: () => created,
    clock: () => now,
    advance(ms) {
      const end = now + ms
      for (;;) {
        let next: { id: number; t: { fn: () => void; every: number; due: number } } | null = null
        for (const [id, t] of timers) if (t.due <= end && (next === null || t.due < next.t.due)) next = { id, t }
        if (!next) break
        now = next.t.due
        next.t.due += next.t.every
        next.t.fn()
      }
      now = end
    },
  }
}

export function fakeFrontmost(initial: string | null): FrontmostSource & { set(b: string | null): void; reads(): number } {
  let b = initial
  let n = 0
  return {
    async read() {
      n++
      return b
    },
    set(v) {
      b = v
    },
    reads: () => n,
  }
}

export function fakeConsole(initial: ConsoleState = { secureInput: 'off', locked: false }): ConsoleProbe & { set(c: Partial<ConsoleState>): void; reads(): number } {
  let c = initial
  let n = 0
  return {
    async read() {
      n++
      return c
    },
    set(v) {
      c = { ...c, ...v }
    },
    reads: () => n,
  }
}

export function fakeShare(v: boolean | null = false): ScreenShareProbe {
  return { read: async () => v }
}

export function fakePower(opts: { idle?: number; thermal?: 'unknown' | 'nominal' | 'fair' | 'serious' | 'critical' } = {}): PowerLike & { idle: number; fire(e: 'lock-screen' | 'unlock-screen' | 'suspend' | 'resume'): void } {
  const listeners = new Map<string, Set<() => void>>()
  const p = {
    idle: opts.idle ?? 0,
    getSystemIdleTime() {
      return p.idle
    },
    getCurrentThermalState: () => opts.thermal ?? 'nominal',
    on(e: string, l: () => void) {
      if (!listeners.has(e)) listeners.set(e, new Set())
      listeners.get(e)!.add(l)
    },
    removeListener(e: string, l: () => void) {
      listeners.get(e)?.delete(l)
    },
    fire(e: 'lock-screen' | 'unlock-screen' | 'suspend' | 'resume') {
      for (const l of listeners.get(e) ?? []) l()
    },
  }
  return p as never
}

export const GOOD_ANSWER = { app_kind: 'spreadsheet', task_phase: 'entering', blocker: 'cannot_find_control', confidence: 0.82, box_2d: [100, 200, 180, 400] }

export function scriptedPort(responses: Array<GlancePortResponse | Error> = [{ ok: true, result: GOOD_ANSWER, model: 'test-model', latency_ms: 321, cost_usd_est: 0.0004 }]): GlancePort & { calls: GlancePortRequest[] } {
  const calls: GlancePortRequest[] = []
  return {
    calls,
    async glance(req) {
      // keep a COPY of what matters; the frame buffer itself is zeroed by the caller after the call
      calls.push({ ...req, frame: { ...req.frame, jpeg: Buffer.from(req.frame.jpeg) } })
      const r = responses[Math.min(calls.length - 1, responses.length - 1)]
      if (r instanceof Error) throw r
      return r
    },
  }
}

export function recordingPost(status = 200): PostFn & { posts: Array<{ url: string; body: unknown }> } {
  const posts: Array<{ url: string; body: unknown }> = []
  const fn = (async (url: string, body: unknown) => {
    posts.push({ url, body })
    return { status }
  }) as PostFn & { posts: typeof posts }
  fn.posts = posts
  return fn
}

export const secure = (s: SecureInputState): Partial<ConsoleState> => ({ secureInput: s })
