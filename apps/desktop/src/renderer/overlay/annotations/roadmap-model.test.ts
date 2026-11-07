import { describe, expect, it } from 'vitest'
import { IDLE_SHOWTIME_STATE, type ShowtimeState } from '../../../shared/showtime'
import { BADGE_TEXT, roadmapModel } from './roadmap-model'

const chapters = [
  { id: 'a', n: 1, title: 'One', caption: 'first', status: 'current' as const, durationMs: 10_000 },
  { id: 'b', n: 2, title: 'Two', caption: 'second', status: 'pending' as const, durationMs: 10_000 },
  { id: 'c', n: 3, title: 'Three', caption: 'third', status: 'unavailable' as const, durationMs: 10_000, reason: 'off' },
]
const running = (over: Partial<ShowtimeState> = {}): ShowtimeState => ({
  ...IDLE_SHOWTIME_STATE,
  running: true,
  chapters,
  chapterIndex: 0,
  chapterDurationMs: 10_000,
  chapterElapsedMs: 2_000,
  since: 1_000,
  ...over,
})

describe('roadmap model', () => {
  it('is hidden when idle and when the tour has handed over', () => {
    expect(roadmapModel(IDLE_SHOWTIME_STATE, 0).visible).toBe(false)
    const m = roadmapModel({ ...IDLE_SHOWTIME_STATE, handover: true }, 0)
    expect(m.visible).toBe(false)
    expect(m.badge).toBeNull()
    expect(m.handover).toBe(true)
  })

  it('shows the scripted badge by default and hides it with badge=false or live mode', () => {
    expect(roadmapModel(running(), 1_000).badge).toBe(BADGE_TEXT)
    expect(roadmapModel(running({ badge: false }), 1_000).badge).toBeNull()
    expect(roadmapModel(running({ mode: 'live' }), 1_000).badge).toBeNull()
  })

  it('lists every chapter with its status and names the current one', () => {
    const m = roadmapModel(running(), 1_000)
    expect(m.items.map((i) => i.status)).toEqual(['current', 'pending', 'unavailable'])
    expect(m.current).toEqual({ n: 1, title: 'One', caption: 'first' })
  })

  it('interpolates progress while running and freezes it while paused', () => {
    expect(roadmapModel(running(), 1_000).progress).toBeCloseTo(0.2)
    expect(roadmapModel(running(), 4_000).progress).toBeCloseTo(0.5)
    expect(roadmapModel(running({ paused: true, since: null }), 9_000).progress).toBeCloseTo(0.2)
    expect(roadmapModel(running(), 60_000).progress).toBe(1)
  })
})
