// The scene state machine: runs chapters as timed beats, with pause, next, previous, stop and graceful skipping of
// chapters whose dependency is not available. Time comes from an injectable clock so every path is unit-testable,
// and beat times are the scripted ones (not measured), so a run is fully deterministic.
import type { ShowtimeChapterInfo, ShowtimeMode, ShowtimeState } from '../../shared/showtime'
import type { Action, Beat, Chapter } from './types'

export interface Clock {
  now(): number
  setTimeout(fn: () => void, ms: number): unknown
  clearTimeout(handle: unknown): void
}

export const realClock: Clock = {
  now: () => Date.now(),
  setTimeout: (fn, ms) => setTimeout(fn, ms),
  clearTimeout: (h) => clearTimeout(h as NodeJS.Timeout),
}

export type Availability = { ok: true } | { ok: false; reason: string }
export type FinishReason = 'complete' | 'stopped'

export interface MachineDeps {
  chapters: Chapter[]
  exec(action: Action, info: { chapterIndex: number; chapterId: string }): Promise<void> | void
  probe?(chapter: Chapter): Promise<Availability> | Availability
  onState?(state: ShowtimeState): void
  onFinish?(reason: FinishReason): void
  onError?(err: unknown, action: Action): void
  clock?: Clock
  mode?: ShowtimeMode
  full?: boolean
  badge?: boolean
  // A stuck action (hung stage page) must never freeze the tour.
  actionTimeoutMs?: number
}

export interface Machine {
  start(): Promise<void>
  stop(): void
  pause(): void
  resume(): void
  togglePause(): void
  next(): void
  prev(): void
  state(): ShowtimeState
}

export function createMachine(deps: MachineDeps): Machine {
  const clock = deps.clock ?? realClock
  const chapters = deps.chapters
  const timeoutMs = deps.actionTimeoutMs ?? 4000
  const status: ShowtimeChapterInfo['status'][] = chapters.map(() => 'pending')
  const reasons: (string | undefined)[] = chapters.map(() => undefined)

  let running = false
  let paused = false
  let handover = false
  let index = -1
  let elapsed = 0 // inside the current chapter, at `since`
  let since: number | null = null
  let beatIdx = 0
  let beats: Beat[] = []
  let timer: unknown = null
  let timerTargetAt = 0 // chapter-relative time the pending timer fires at
  let generation = 0
  let queue: Promise<void> = Promise.resolve()

  const available = (i: number): boolean => status[i] !== 'unavailable'
  const availableChapters = (): number[] => chapters.map((_, i) => i).filter(available)
  const totalMs = (): number => availableChapters().reduce((sum, i) => sum + chapters[i].durationMs, 0)

  function snapshot(): ShowtimeState {
    const live = since !== null ? Math.min(chapters[index]?.durationMs ?? 0, elapsed + (clock.now() - since)) : elapsed
    const before = availableChapters().filter((i) => i < index).reduce((s, i) => s + chapters[i].durationMs, 0)
    return {
      running,
      paused,
      mode: deps.mode ?? 'scripted',
      full: deps.full ?? false,
      badge: deps.badge ?? true,
      chapterIndex: running || handover ? index : -1,
      chapters: chapters.map((c, i) => ({
        id: c.id,
        n: c.n,
        title: c.title,
        caption: c.caption,
        status: status[i],
        durationMs: c.durationMs,
        ...(reasons[i] ? { reason: reasons[i] } : {}),
      })),
      chapterDurationMs: chapters[index]?.durationMs ?? 0,
      chapterElapsedMs: elapsed,
      since,
      totalMs: totalMs(),
      elapsedTotalMs: index >= 0 ? before + live : 0,
      handover,
    }
  }
  const emit = (): void => deps.onState?.(snapshot())

  function enqueue(action: Action, gen: number): void {
    queue = queue.then(async () => {
      if (gen !== generation) return
      const info = { chapterIndex: index, chapterId: chapters[index]?.id ?? '' }
      let handle: unknown
      try {
        await Promise.race([
          Promise.resolve(deps.exec(action, info)),
          new Promise<void>((resolve) => {
            handle = clock.setTimeout(resolve, timeoutMs)
          }),
        ])
      } catch (err) {
        deps.onError?.(err, action)
      } finally {
        if (handle !== undefined) clock.clearTimeout(handle)
      }
    })
  }

  function clearTimer(): void {
    if (timer !== null) clock.clearTimeout(timer)
    timer = null
  }

  function schedule(): void {
    clearTimer()
    if (!running || paused) return
    const beat = beats[beatIdx]
    timerTargetAt = beat ? beat.at : chapters[index].durationMs
    since = clock.now()
    timer = clock.setTimeout(fire, Math.max(0, timerTargetAt - elapsed))
  }

  function fire(): void {
    timer = null
    elapsed = timerTargetAt
    since = clock.now()
    const gen = generation
    const beat = beats[beatIdx]
    if (beat) {
      // Every beat due at this instant fires together, in order.
      while (beats[beatIdx] && beats[beatIdx].at <= elapsed) {
        enqueue(beats[beatIdx].action, gen)
        beatIdx++
      }
      emit()
      schedule()
      return
    }
    advanceFrom(index)
  }

  function nextAvailable(from: number): number {
    for (let i = from + 1; i < chapters.length; i++) if (available(i)) return i
    return -1
  }
  function prevAvailable(from: number): number {
    for (let i = from - 1; i >= 0; i--) if (available(i)) return i
    return -1
  }

  function advanceFrom(i: number): void {
    const n = nextAvailable(i)
    if (n < 0) finish('complete')
    else enter(n)
  }

  function enter(i: number): void {
    clearTimer()
    generation++
    queue = Promise.resolve()
    index = i
    elapsed = 0
    since = null
    paused = false
    handover = false
    status.forEach((s, k) => {
      if (s === 'unavailable') return
      status[k] = k < i ? 'done' : k === i ? 'current' : 'pending'
    })
    const chapter = chapters[i]
    beats = [...chapter.beats].sort((a, b) => a.at - b.at)
    beatIdx = 0
    enqueue({ type: 'baseline', persona: chapter.persona }, generation)
    schedule()
    emit()
  }

  function finish(reason: FinishReason): void {
    clearTimer()
    generation++
    running = false
    paused = false
    since = null
    handover = reason === 'complete'
    if (reason === 'complete') status.forEach((s, k) => (status[k] = s === 'unavailable' ? s : 'done'))
    emit()
    deps.onFinish?.(reason)
  }

  return {
    async start() {
      if (running) return
      for (let i = 0; i < chapters.length; i++) {
        status[i] = 'pending'
        reasons[i] = undefined
        if (!chapters[i].requires.length || !deps.probe) continue
        let result: Availability
        try {
          result = await deps.probe(chapters[i])
        } catch (err) {
          result = { ok: false, reason: err instanceof Error ? err.message : String(err) }
        }
        if (!result.ok) {
          status[i] = 'unavailable'
          reasons[i] = result.reason
        }
      }
      running = true
      handover = false
      const first = nextAvailable(-1)
      if (first < 0) {
        finish('complete')
        return
      }
      enter(first)
    },
    stop() {
      if (!running && !handover) return
      if (!running) {
        // Esc during the live hand-over: nothing is playing, but the owner still wants the stage closed.
        handover = false
        emit()
        deps.onFinish?.('stopped')
        return
      }
      finish('stopped')
    },
    pause() {
      if (!running || paused) return
      if (since !== null) elapsed = Math.min(chapters[index].durationMs, Math.max(elapsed, elapsed + (clock.now() - since)))
      // The pending beat has not fired: freeze at the elapsed time, never past the beat it was waiting for.
      elapsed = Math.min(elapsed, timerTargetAt)
      clearTimer()
      paused = true
      since = null
      emit()
    },
    resume() {
      if (!running || !paused) return
      paused = false
      schedule()
      emit()
    },
    togglePause() {
      if (paused) this.resume()
      else this.pause()
    },
    next() {
      if (!running) return
      advanceFrom(index)
    },
    prev() {
      if (!running) return
      const p = prevAvailable(index)
      enter(p < 0 ? index : p)
    },
    state: snapshot,
  }
}
