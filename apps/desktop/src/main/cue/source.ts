// Where decisions come from and where feedback goes. `CueEnginePort` is the one seam: the real one speaks to the engine over loopback, the
// fake plays fixtures, so the whole of Cue runs, is tested and is screenshotted without an engine.
import { sanitizeFeedback, type CueFeedbackEvent } from './feedback'
import type { CueProactivity } from './guards'

export interface PollOptions {
  // The worker pressed for help (or said yes to an offer): the engine may answer even where it would stay quiet.
  asked?: boolean
  // The worker used voice or asked for it: only then may the answer carry a whisper.
  voiceOk?: boolean
  proactivity?: CueProactivity
  // What only the desktop can know (the engine cannot see the frontmost app, secure input, a lock or a call): the frontmost app is on the
  // denylist or secure input is on (never bypassed, not even when asked), and the worker is not at the screen.
  denied?: boolean
  away?: boolean
  // Input rhythm from awareness, when it has a better one than the engine's own last-input time.
  quietS?: number
  typing?: boolean
}

export interface CueEnginePort {
  /** The engine's current decision, raw (parsed by parseCueDecision); null when it did not answer. Never throws. */
  next(o?: PollOptions): Promise<unknown | null>
  /** One feedback event. Best effort: never throws. */
  feedback(e: CueFeedbackEvent): Promise<void>
}

/** Plays decisions in order, then answers with nothing (null: the engine did not say anything new). Records feedback. */
export function createFakeEngine(script: readonly unknown[] = []): CueEnginePort & { queue: unknown[]; sent: CueFeedbackEvent[]; polls: PollOptions[]; push(raw: unknown): void } {
  const queue = [...script]
  const sent: CueFeedbackEvent[] = []
  const polls: PollOptions[] = []
  return {
    queue,
    sent,
    polls,
    push: (raw) => void queue.push(raw),
    async next(o) {
      polls.push(o ?? {})
      return queue.length > 0 ? queue.shift() : null
    },
    async feedback(e) {
      sent.push(e)
    },
  }
}

export interface HttpPortOptions {
  // The engine's base URL; only loopback is ever used.
  baseUrl: string
  // The person the decisions are for (the engine's own id for them), or null when not known yet.
  person: () => string | null
  fetchImpl?: typeof fetch
  timeoutMs?: number
  log?: (scope: string, ...args: unknown[]) => void
}

const isLoopback = (url: string): boolean => {
  try {
    const u = new URL(url)
    return u.protocol === 'http:' && ['127.0.0.1', 'localhost', '[::1]', '::1'].includes(u.hostname)
  } catch {
    return false
  }
}

/** The real port: GET /cue/next and POST /cue/feedback on the engine, loopback only. Paths are assumptions to confirm with CUE-ENGINE. */
export function createHttpEngine(o: HttpPortOptions): CueEnginePort {
  const doFetch = o.fetchImpl ?? fetch
  const timeoutMs = o.timeoutMs ?? 2_000
  const log = o.log ?? (() => undefined)
  const withTimeout = async <T>(run: (signal: AbortSignal) => Promise<T>): Promise<T> => {
    const ctl = new AbortController()
    const t = setTimeout(() => ctl.abort(), timeoutMs)
    try {
      return await run(ctl.signal)
    } finally {
      clearTimeout(t)
    }
  }
  return {
    async next(opts = {}) {
      if (!isLoopback(o.baseUrl)) return null
      const q = new URLSearchParams()
      const person = o.person()
      if (person) q.set('person', person)
      q.set('voice_ok', opts.voiceOk ? '1' : '0')
      if (opts.asked) q.set('asked', '1')
      if (opts.proactivity) q.set('proactivity', opts.proactivity)
      if (opts.denied) q.set('denied', '1')
      if (opts.away) q.set('away', '1')
      if (typeof opts.quietS === 'number' && Number.isFinite(opts.quietS)) q.set('quiet_s', String(Math.round(Math.min(86_400, Math.max(0, opts.quietS)) * 10) / 10))
      if (opts.typing) q.set('typing', '1')
      try {
        return await withTimeout(async (signal) => {
          const res = await doFetch(`${o.baseUrl}/cue/next?${q}`, { signal })
          return res.ok ? ((await res.json()) as unknown) : null
        })
      } catch (err) {
        log('cue', `poll failed: ${err instanceof Error ? err.name : 'error'}`)
        return null
      }
    },
    async feedback(e) {
      const clean = sanitizeFeedback(e)
      if (!clean || !isLoopback(o.baseUrl)) return
      try {
        await withTimeout(async (signal) => {
          await doFetch(`${o.baseUrl}/cue/feedback`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ ...clean, person: o.person() ?? undefined }), signal })
        })
      } catch (err) {
        log('cue', `feedback failed: ${err instanceof Error ? err.name : 'error'}`)
      }
    },
  }
}
