import { describe, expect, it, vi } from 'vitest'
import { Bus } from '../bus'
import { createDirector, progressLine, unionBox, GREETING, SCAM_LINE, SETTINGS_LINE, type DirectorDeps, type ScamRects } from './director'
import type { LearnerSnapshot, NormBox } from '../../shared/protocol'
import { DEFAULT_SETTINGS } from '../../shared/settings'

const box = (x: number): NormBox => ({ xmin: x, ymin: 100, xmax: x + 50, ymax: 130 })
const RECTS: ScamRects = { urgent: [box(600)], twoHours: [box(700)], url: [box(620)], phone: [box(800)] }

function snapshot(level: 1 | 2 | 3 | 4 = 2): LearnerSnapshot {
  const skill = { level, streakClean: 0, lastSeen: 1, nextReview: 2 }
  return {
    skills: { video_call: skill, spot_scam: { ...skill, lastSeen: null }, bigger_text: { ...skill, lastSeen: null } },
    confidenceLog: [], attempts: [], whatWorks: [], avoidJargon: [],
    lastSession: { at: 1, skillId: 'video_call', summary: 'Found the green Start call button with one hint.' },
  } as LearnerSnapshot
}

function setup(opts: { rects?: ScamRects | null; needsOpen?: boolean } = {}) {
  const opened = { value: false, calls: 0 }
  const bus = new Bus()
  const st = { phase: 'asleep', persona: null as import('../../shared/protocol').PersonaId | null }
  const requests: unknown[] = []
  bus.on('session:request', (r) => {
    requests.push(r)
    st.persona = r.personaId
    st.phase = 'live' // the session connects at once in the test
  })
  const injected: string[] = []
  const captions: string[] = []
  const shown: unknown[] = []
  const dispatch = vi.fn(async () => ({ ok: true }) as never)
  const stopped: string[] = []
  const views: string[] = []
  let t = 0
  const deps: DirectorDeps = {
    bus,
    state: { get: () => st, patch: vi.fn() },
    settings: { get: () => ({ ...DEFAULT_SETTINGS }) },
    services: {
      overlay: { show: (a: unknown[]) => void shown.push(...a), clear: vi.fn(), caption: (_s: string, text: string) => void captions.push(text), chip: vi.fn() },
      live: { inject: (text: string) => void injected.push(text) },
      learner: { snapshot: () => snapshot() },
      capture: { grab: async () => { throw new Error('no capture needed') } },
      grounder: { ground: async () => { throw new Error('no grounder needed') } },
    } as unknown as DirectorDeps['services'],
    dispatch,
    showView: (v) => void views.push(v),
    stopSession: (r) => void stopped.push(r),
    stage: () => (opts.rects === null ? null : {
      scamRects: async () => (opened.value || !opts.needsOpen ? (opts.rects ?? RECTS) : {}),
      rectOf: async () => box(30),
      openThread: async () => { opened.value = true; opened.calls++; return true },
      closeApp: async () => true,
    }),
    log: () => undefined,
    sleep: async (ms) => void (t += ms),
    now: () => t,
  }
  return { opened, bus, st, requests, injected, captions, shown, dispatch, stopped, views, director: createDirector(deps), advance: () => t }
}

describe('demo director', () => {
  it('beat 1 opens the session without an opener and says the exact greeting, captioned too', async () => {
    const h = setup()
    const r = await h.director.run(1)
    expect(r.ok).toBe(true)
    expect(h.requests).toEqual([{ personaId: 'marcus', source: 'wake' }])
    expect(h.injected).toContain(`[RUNNER] Say exactly these words and nothing else: "${GREETING}"`)
    expect(h.captions).toContain(GREETING)
  })

  it('beat 2 starts the static video call lesson through the real dispatcher', async () => {
    const h = setup()
    await h.director.run(2)
    expect(h.dispatch).toHaveBeenCalledWith('start_lesson', { goal: 'video call my granddaughter Lily' }, 'debug')
  })

  it('beat 3 runs the real scam agent from exact span boxes with the exact spoken line and no "safe"', async () => {
    const h = setup()
    const r = await h.director.run(3)
    expect(r.ok).toBe(true)
    await vi.waitFor(() => expect(h.injected.some((t) => t.includes(SCAM_LINE))).toBe(true))
    await vi.waitFor(() => expect(h.shown.some((a) => (a as { kind: string }).kind === 'bubble')).toBe(true))
    const marks = h.shown.filter((a) => (a as { kind: string }).kind === 'highlightText') as { boxes: NormBox[] }[]
    expect(marks).toHaveLength(4)
    expect(marks.map((m) => m.boxes[0])).toContainEqual(box(600))
    expect(h.injected.join(' ')).not.toMatch(/\bsafe\b/i)
    expect(h.injected.every((t) => !t.startsWith('[AGENT_RESULT'))).toBe(true)
  })

  it('opens the Messages thread first when the scam boxes are not on screen yet', async () => {
    const h = setup({ needsOpen: true })
    await h.director.run(3)
    expect(h.opened.calls).toBe(1)
    await vi.waitFor(() => expect(h.injected.some((t) => t.includes(SCAM_LINE))).toBe(true))
  })

  it('falls back to the normal pipeline when the stage or its boxes are unavailable', async () => {
    for (const rects of [null, {} as ScamRects]) {
      const h = setup({ rects })
      await h.director.run(3)
      expect(h.dispatch).toHaveBeenCalledWith('spawn_agent', expect.objectContaining({ kind: 'scam_check' }), 'debug')
      expect(await h.director.intercept('spawn_agent', { kind: 'scam_check' })).toBeUndefined()
    }
  })

  it('beat 4 rings the Settings icon from the stage box and says the exact line', async () => {
    const h = setup()
    await h.director.run(4)
    expect(h.shown.map((a) => (a as { kind: string }).kind)).toEqual(['ring', 'arrow'])
    expect(h.captions).toContain(SETTINGS_LINE)
  })

  it('beat 5 opens Progress and says two truthful sentences from the profile', async () => {
    const h = setup()
    await h.director.run(5)
    expect(h.views).toEqual(['progress'])
    const said = h.captions.at(-1) ?? ''
    expect(said).toBe('Last time you found the green Start call button with one hint. You are at the "Walk with me" level, and I will step back as you do it cleanly.')
    expect(said.split('. ').length).toBe(2)
  })

  it('beat 6 switches to amelia, says goodbye, ends the session and does not reopen it', async () => {
    vi.useFakeTimers()
    try {
      const h = setup()
      await h.director.run(6)
      expect(h.requests).toContainEqual({ personaId: 'amelia', source: 'wake' })
      expect(h.captions).toContain('Goodbye, it was lovely helping you.')
      vi.advanceTimersByTime(6000)
      expect(h.stopped).toEqual(['goodbye'])
      h.bus.emit('session:ended', { reason: 'goodbye' })
      vi.advanceTimersByTime(5000)
      expect(h.requests).toHaveLength(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('reopens the session within 2 s after a drop, but not after the learner pressed Stop', () => {
    vi.useFakeTimers()
    try {
      const h = setup()
      h.st.persona = 'marcus'
      h.bus.emit('session:ended', { reason: 'error' })
      vi.advanceTimersByTime(2000)
      expect(h.requests).toEqual([{ personaId: 'marcus', source: 'wake' }])
      h.bus.emit('session:ended', { reason: 'stop' })
      vi.advanceTimersByTime(6000)
      expect(h.requests).toHaveLength(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('demo_beat is reachable through the dispatcher hook and rejects bad beats', async () => {
    const h = setup()
    expect(await h.director.intercept('demo_beat', { beat: 9 })).toEqual({ error: expect.any(String) })
    expect(await h.director.intercept('demo_beat', { beat: 1 })).toMatchObject({ beat: 1, ok: true })
    expect(await h.director.intercept('point_at', {})).toBeUndefined()
  })

  it('unionBox covers every line box', () => {
    expect(unionBox([box(10), box(40)])).toEqual({ xmin: 10, ymin: 100, xmax: 90, ymax: 130 })
    expect(unionBox([])).toBeNull()
  })

  it('progressLine never invents numbers', () => {
    expect(progressLine(snapshot(3))).toContain('already helping you less')
  })
})
