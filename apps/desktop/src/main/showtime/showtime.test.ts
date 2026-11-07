import { describe, expect, it } from 'vitest'
import { buildChapters } from './chapters'
import { FakeClock } from './fake-clock'
import { createMachine, type MachineDeps } from './machine'
import { SCRIPT_LINES, resolveText } from './script'
import type { Action } from './types'
import type { ShowtimeState } from '../../shared/showtime'

function harness(over: Partial<MachineDeps> & { full?: boolean } = {}) {
  const clock = new FakeClock()
  const log: { at: number; chapter: string; action: Action }[] = []
  const states: ShowtimeState[] = []
  const finishes: string[] = []
  const chapters = buildChapters({ full: over.full ?? false })
  const machine = createMachine({
    chapters,
    clock,
    exec: (action, info) => {
      log.push({ at: clock.now(), chapter: info.chapterId, action })
    },
    onState: (s) => states.push(s),
    onFinish: (r) => finishes.push(r),
    ...over,
  })
  return { clock, log, states, finishes, chapters, machine }
}

const total = (chapters: { durationMs: number }[]): number => chapters.reduce((s, c) => s + c.durationMs, 0)

describe('showtime script', () => {
  it('every narration line referenced by a chapter exists, fits its slot, and never overlaps another', () => {
    for (const full of [false, true]) {
      for (const c of buildChapters({ full })) {
        const says = c.beats.filter((b) => b.action.type === 'say').sort((a, b) => a.at - b.at)
        let freeAt = 0
        for (const b of says) {
          const l = SCRIPT_LINES.get((b.action as { line: string }).line)
          expect(l, `${c.id}: unknown line`).toBeTruthy()
          expect(b.at, `${c.id}: ${l!.id} starts before the previous clip ends`).toBeGreaterThanOrEqual(freeAt)
          freeAt = b.at + l!.durationMs
          expect(freeAt, `${c.id}: ${l!.id} runs past the chapter`).toBeLessThanOrEqual(c.durationMs)
        }
      }
    }
  })

  it('each slot is long enough for the words (about 3 words per second; the render script checks the real clip)', () => {
    for (const l of SCRIPT_LINES.values()) {
      const words = resolveText(l).split(/\s+/).length
      expect(l.durationMs, `${l.id}: ${words} words in ${l.durationMs} ms`).toBeGreaterThanOrEqual(Math.round((words / 3) * 1000))
    }
  })

  it('the core cut fits 3:00 with at least 8 s of margin; the full tour is the extended one', () => {
    const core = total(buildChapters({ full: false }))
    const full = total(buildChapters({ full: true }))
    expect(core).toBeLessThanOrEqual(172_000)
    expect(core).toBeGreaterThan(120_000)
    expect(full).toBeGreaterThan(core + 40_000)
  })

  it('the narrated names follow the persona config (no hard-coded name in the script text)', () => {
    for (const l of SCRIPT_LINES.values()) expect(/marcus|amelia/i.test(l.text)).toBe(false)
  })
})

describe('showtime machine', () => {
  it('runs every chapter in order with a baseline first, then ends in the live hand-over', async () => {
    const h = harness()
    await h.machine.start()
    await h.clock.advance(total(h.chapters) + 1000)
    expect(h.finishes).toEqual(['complete'])
    const seen = h.log.filter((l) => l.action.type === 'baseline').map((l) => l.chapter)
    expect(seen).toEqual(h.chapters.map((c) => c.id))
    const last = h.machine.state()
    expect(last.running).toBe(false)
    expect(last.handover).toBe(true)
    expect(last.chapters.every((c) => c.status === 'done')).toBe(true)
    // Chapter boundaries are exactly the scripted durations.
    let t = 0
    for (const c of h.chapters) {
      const base = h.log.find((l) => l.action.type === 'baseline' && l.chapter === c.id)!
      expect(base.at).toBe(t)
      t += c.durationMs
    }
  })

  it('pause freezes beats and resume continues from where it stopped', async () => {
    const h = harness()
    await h.machine.start()
    await h.clock.advance(1000)
    const before = h.log.length
    h.machine.pause()
    expect(h.machine.state().paused).toBe(true)
    await h.clock.advance(60_000)
    expect(h.log.length).toBe(before)
    h.machine.resume()
    await h.clock.advance(h.chapters[0].durationMs)
    expect(h.log.some((l) => l.chapter === h.chapters[1].id)).toBe(true)
    expect(h.log.filter((l) => l.chapter === h.chapters[0].id && l.action.type === 'say').length).toBe(1)
  })

  it('next skips ahead, previous goes back, and an old chapter does not leak actions', async () => {
    const h = harness()
    await h.machine.start()
    await h.clock.advance(500)
    h.machine.next()
    await h.clock.advance(100)
    expect(h.machine.state().chapterIndex).toBe(1)
    h.machine.prev()
    await h.clock.advance(100)
    expect(h.machine.state().chapterIndex).toBe(0)
    h.machine.prev() // first chapter: restarts it
    expect(h.machine.state().chapterIndex).toBe(0)
    await h.clock.advance(1)
    const baselines = h.log.filter((l) => l.action.type === 'baseline').length
    expect(baselines).toBe(4)
    await h.clock.advance(h.chapters[0].durationMs)
    // After skipping away from chapter 1 mid-way, none of its late beats fired twice.
    expect(h.log.filter((l) => l.chapter === h.chapters[0].id && l.action.type === 'say' && (l.action as { line: string }).line === 'c1-hello').length).toBeLessThanOrEqual(2)
  })

  it('next on the last chapter hands over; previous never goes before the first', async () => {
    const h = harness()
    await h.machine.start()
    for (let i = 0; i < h.chapters.length - 1; i++) h.machine.next()
    expect(h.machine.state().chapterIndex).toBe(h.chapters.length - 1)
    h.machine.next()
    expect(h.finishes).toEqual(['complete'])
    expect(h.machine.state().handover).toBe(true)
  })

  it('stop is immediate: no further action runs and the finish reason is "stopped"', async () => {
    const h = harness()
    await h.machine.start()
    await h.clock.advance(3000)
    const n = h.log.length
    h.machine.stop()
    await h.clock.advance(120_000)
    expect(h.log.length).toBe(n)
    expect(h.finishes).toEqual(['stopped'])
    expect(h.machine.state().running).toBe(false)
    expect(h.clock.pending).toBe(0)
  })

  it('a chapter whose dependency is missing is marked unavailable and skipped, in both directions', async () => {
    const h = harness({ probe: (c) => (c.requires.includes('agency') ? { ok: false, reason: 'agency not integrated' } : { ok: true }) })
    await h.machine.start()
    const s = h.machine.state()
    const agency = s.chapters.find((c) => c.id === 'do-it-for-you')!
    expect(agency.status).toBe('unavailable')
    expect(agency.reason).toBe('agency not integrated')
    expect(s.totalMs).toBe(total(h.chapters) - h.chapters.find((c) => c.id === 'do-it-for-you')!.durationMs)
    await h.clock.advance(total(h.chapters))
    expect(h.log.some((l) => l.chapter === 'do-it-for-you')).toBe(false)
    expect(h.log.some((l) => l.chapter === 'your-files')).toBe(true)
    expect(h.finishes).toEqual(['complete'])
    expect(h.machine.state().chapters.find((c) => c.id === 'do-it-for-you')!.status).toBe('unavailable')
  })

  it('skipping with next/prev also steps over an unavailable chapter', async () => {
    const h = harness({ probe: (c) => (c.requires.includes('agency') ? { ok: false, reason: 'off' } : { ok: true }) })
    await h.machine.start()
    const ids = h.chapters.map((c) => c.id)
    const i6 = ids.indexOf('teach-anything')
    for (let i = 0; i < i6; i++) h.machine.next()
    h.machine.next()
    expect(h.chapters[h.machine.state().chapterIndex].id).toBe('your-files')
    h.machine.prev()
    expect(h.chapters[h.machine.state().chapterIndex].id).toBe('teach-anything')
  })

  it('if every dependent chapter is unavailable the rest still plays; if all are, it ends at once', async () => {
    const h = harness({ probe: () => ({ ok: false, reason: 'nothing available' }) })
    await h.machine.start()
    expect(h.machine.state().chapters.filter((c) => c.status === 'unavailable').map((c) => c.id)).toEqual(['do-it-for-you', 'your-files'])
    const empty = createMachine({ chapters: [], exec: () => undefined, clock: new FakeClock() })
    await empty.start()
    expect(empty.state().running).toBe(false)
  })

  it('a failing or hanging action never stops the tour', async () => {
    const errors: unknown[] = []
    const h = harness({
      exec: (action) => {
        if (action.type === 'stage.go') throw new Error('stage window is gone')
        if (action.type === 'say') return new Promise<void>(() => undefined)
      },
      onError: (e) => errors.push(e),
    })
    await h.machine.start()
    await h.clock.advance(total(h.chapters) + 60_000)
    expect(errors.length).toBeGreaterThan(0)
    expect(h.finishes).toEqual(['complete'])
  })

  it('the state carries enough to draw a progress bar (elapsed, since, totals)', async () => {
    const h = harness()
    await h.machine.start()
    await h.clock.advance(2000)
    const s = h.machine.state()
    expect(s.running).toBe(true)
    expect(s.chapterDurationMs).toBe(h.chapters[0].durationMs)
    expect(s.since).not.toBeNull()
    expect(s.elapsedTotalMs).toBeGreaterThanOrEqual(1900)
    expect(s.totalMs).toBe(total(h.chapters))
  })
})
