import { describe, expect, it } from 'vitest'
import type { AttemptRecord, LearnerSnapshot } from '../../../shared/protocol'
import { DAY_MS } from '../levels'
import { buildProgress } from '../progress'

const NOW = Date.UTC(2026, 9, 31, 14, 0, 0)
const fresh = { level: 1 as const, streakClean: 0, lastSeen: null, nextReview: null }

function snap(over: Partial<LearnerSnapshot> = {}): LearnerSnapshot {
  return { skills: { video_call: fresh, spot_scam: fresh, bigger_text: fresh }, confidenceLog: [], attempts: [], whatWorks: [], avoidJargon: [], ...over }
}

function att(over: Partial<AttemptRecord>): AttemptRecord {
  return {
    id: 'a', skillId: 'video_call', lessonId: 'l', startedAt: NOW - 60_000, endedAt: NOW, levelAtStart: 2, levelAtEnd: 2, completed: true,
    hintsUsed: 0, errors: 0, stalls: 0, safetyFlag: false, anxietyPhrase: false, teachBackScore: 1, confidence: 4, clean: true, ...over,
  }
}

describe('buildProgress', () => {
  it('an empty profile is calm and suggests something new', () => {
    const p = buildProgress(snap(), { now: NOW })
    expect(p.skills.map((s) => s.mode)).toEqual(['not_started', 'not_started', 'not_started'])
    expect(p.canDoNow).toEqual([])
    expect(p.hintsPerTask).toEqual([])
    expect(p.overall).toMatchObject({ attempts: 0, trend: 'not_enough_data', headline: 'Nothing practised yet.' })
    expect(p.nextSuggested).toEqual({ skillId: 'video_call', reason: 'Something new to try.' })
    expect(p.confidence).toEqual({ points: [], first: null, latest: null })
  })

  it('reports how often the assistant did things for the learner, only when it did', () => {
    expect(buildProgress(snap(), { now: NOW }).doneForMe).toBeUndefined()
    const p = buildProgress(snap({ doneForMe: { 'open:www.ageuk.org.uk': 2, 'task:find the opening times': 1 } }), { now: NOW })
    expect(p.doneForMe).toEqual({ total: 3, text: 'Done for you: 3 times. Ask to be shown and you will need this less.' })
    expect(buildProgress(snap({ doneForMe: { x: 1 } }), { now: NOW }).doneForMe?.text).toMatch(/^Done for you: 1 time\./)
  })

  it('one attempt asks for one more before comparing', () => {
    const p = buildProgress(snap({ attempts: [att({ hintsUsed: 3 })] }), { now: NOW })
    expect(p.overall.headline).toBe('Your first practice needed 3 hints. Do one more and we can compare.')
    expect(p.overall.trend).toBe('not_enough_data')
  })

  it('shows hints going down per skill and overall (the anti-dependency chart)', () => {
    const attempts = [
      att({ id: '1', endedAt: NOW - 2 * DAY_MS, hintsUsed: 4, levelAtStart: 1, clean: true }),
      att({ id: '2', endedAt: NOW - DAY_MS, hintsUsed: 1, levelAtStart: 2 }),
      att({ id: '3', endedAt: NOW, hintsUsed: 0, levelAtStart: 3 }),
      att({ id: '4', skillId: 'spot_scam', endedAt: NOW - 100, hintsUsed: 2 }),
    ]
    const p = buildProgress(
      snap({
        attempts: [...attempts].reverse(), // order must not matter
        skills: { video_call: { level: 4, streakClean: 0, lastSeen: NOW, nextReview: NOW + DAY_MS }, spot_scam: { level: 2, streakClean: 0, lastSeen: NOW, nextReview: NOW + DAY_MS }, bigger_text: fresh },
      }),
      { now: NOW },
    )
    const vc = p.hintsPerTask.find((s) => s.skillId === 'video_call')!
    expect(vc.series.map((x) => [x.attempt, x.hints, x.level])).toEqual([[1, 4, 1], [2, 1, 2], [3, 0, 3]])
    expect(p.hintsPerTask.map((s) => s.skillId)).toEqual(['video_call', 'spot_scam'])
    expect(p.overall).toMatchObject({ attempts: 4, firstAttemptHints: 4, latestAttemptHints: 0, trend: 'down' })
    expect(p.overall.headline).toBe('You needed 4 hints on your first task and 0 hints on your latest.')
    expect(JSON.parse(JSON.stringify(p))).toEqual(p) // serialisable
  })

  it('flat and up trends are worded kindly', () => {
    const flat = buildProgress(snap({ attempts: [att({ id: '1', endedAt: NOW - 5, hintsUsed: 1 }), att({ id: '2', hintsUsed: 1 })] }), { now: NOW })
    expect(flat.overall).toMatchObject({ trend: 'flat', headline: 'You needed 1 hint on your first task and on your latest.' })
    const up = buildProgress(snap({ attempts: [att({ id: '1', endedAt: NOW - 5, hintsUsed: 0 }), att({ id: '2', hintsUsed: 2 })] }), { now: NOW })
    expect(up.overall.trend).toBe('up')
    expect(up.overall.headline).toContain('harder tasks need more help')
  })

  it('"things you can do now" needs a completed attempt and reflects the level', () => {
    const p = buildProgress(
      snap({
        attempts: [att({ id: '1', skillId: 'video_call', endedAt: NOW - 50 }), att({ id: '2', skillId: 'spot_scam', completed: false, clean: false }), att({ id: '3', skillId: 'bigger_text', endedAt: NOW - 70 })],
        skills: {
          video_call: { level: 3, streakClean: 0, lastSeen: NOW, nextReview: NOW + DAY_MS },
          spot_scam: { level: 1, streakClean: 0, lastSeen: NOW, nextReview: NOW + DAY_MS },
          bigger_text: { level: 4, streakClean: 2, lastSeen: NOW, nextReview: NOW + DAY_MS },
        },
      }),
      { now: NOW },
    )
    expect(p.canDoNow.map((c) => [c.skillId, c.mode, c.text])).toEqual([
      ['video_call', 'mostly_alone', 'Start a video call with someone you know'],
      ['bigger_text', 'on_my_own', 'Make the writing on the screen bigger'],
    ])
    expect(p.skills.find((s) => s.skillId === 'bigger_text')?.mastered).toBe(true)
    expect(p.skills.find((s) => s.skillId === 'spot_scam')?.mode).toBe('with_help')
  })

  it('the generic custom skill appears only once used, and is never the suggested next lesson', () => {
    expect(buildProgress(snap(), { now: NOW }).skills.map((s) => s.skillId)).toEqual(['video_call', 'spot_scam', 'bigger_text'])
    const p = buildProgress(
      snap({
        skills: { video_call: fresh, spot_scam: fresh, bigger_text: fresh, custom: { level: 1, streakClean: 0, lastSeen: NOW, nextReview: NOW - 5 } },
        attempts: [att({ id: 'c1', skillId: 'custom', hintsUsed: 1 })],
      }),
      { now: NOW },
    )
    expect(p.skills.map((s) => s.skillId)).toEqual(['video_call', 'spot_scam', 'bigger_text', 'custom'])
    expect(p.skills[3]).toMatchObject({ name: 'Something new', reviewDue: true })
    expect(p.canDoNow.map((c) => c.skillId)).toEqual(['custom'])
    expect(p.hintsPerTask.map((s) => s.skillId)).toEqual(['custom'])
    expect(p.nextSuggested?.skillId).not.toBe('custom')
  })

  it('confidence trend is ordered; the most overdue review is suggested first', () => {
    const p = buildProgress(
      snap({
        confidenceLog: [{ at: NOW, skillId: 'video_call', rating: 5 }, { at: NOW - DAY_MS, skillId: 'video_call', rating: 2 }],
        skills: {
          video_call: { level: 2, streakClean: 0, lastSeen: NOW - DAY_MS, nextReview: NOW - 10 },
          spot_scam: { level: 2, streakClean: 0, lastSeen: NOW - DAY_MS, nextReview: NOW - 1000 },
          bigger_text: { level: 2, streakClean: 0, lastSeen: NOW - DAY_MS, nextReview: NOW + 1000 },
        },
      }),
      { now: NOW },
    )
    expect(p.confidence).toMatchObject({ first: 2, latest: 5 })
    expect(p.skills.filter((s) => s.reviewDue).map((s) => s.skillId)).toEqual(['video_call', 'spot_scam'])
    expect(p.nextSuggested).toEqual({ skillId: 'spot_scam', reason: 'A quick refresher is due.' })
  })

  it('with everything tried and nothing due it suggests the weakest skill; all mastered suggests nothing', () => {
    const tried = (level: 1 | 2 | 3 | 4, streak = 0) => ({ level, streakClean: streak, lastSeen: NOW, nextReview: NOW + DAY_MS })
    const weak = buildProgress(snap({ skills: { video_call: tried(3), spot_scam: tried(2), bigger_text: tried(4) } }), { now: NOW })
    expect(weak.nextSuggested).toEqual({ skillId: 'spot_scam', reason: 'The one with the most room to grow.' })
    const done = buildProgress(snap({ skills: { video_call: tried(4, 2), spot_scam: tried(4, 2), bigger_text: tried(4, 2) } }), { now: NOW, demoMode: false })
    expect(done.nextSuggested).toBeNull()
  })
})
