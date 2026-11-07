import { describe, expect, it, vi } from 'vitest'
import { EMPTY_HUD_STATE, HUD_CARD_PRIORITY, pickCard, type HudActivity, type HudNotice, type HudState } from '../shared/hud'
import { cornerBounds, createHudModel, hudBounds } from './hud-model'
import type { KillState } from './kill-switch'

function setup(corner = true) {
  let k: KillState = { killed: false, at: null, source: null, engine: null, agent: null }
  const ls = new Set<(s: KillState) => void>()
  const kill = {
    trigger: vi.fn(async () => {
      k = { killed: true, at: 1, source: 'hud', engine: true, agent: true }
      ls.forEach((l) => l(k))
      return { source: 'hud' as const, at: 1, localMs: 1, engine: true, agent: true }
    }),
    clear: vi.fn(async () => {
      k = { killed: false, at: null, source: null, engine: null, agent: null }
      ls.forEach((l) => l(k))
    }),
    state: () => k,
    subscribe: (cb: (s: KillState) => void) => (ls.add(cb), () => ls.delete(cb)),
  }
  const pushed: HudState[] = []
  const model = createHudModel({ kill, endpoints: { dashboard: 'http://127.0.0.1:5173' }, openExternal: () => undefined, onProposalChoice: () => undefined, push: (s) => void pushed.push(s), corner })
  const sink = { review: vi.fn(), later: vi.fn(), open: vi.fn(), voiceEnd: vi.fn() }
  model.setCorner(sink)
  return { model, kill, pushed, sink }
}

const working: HudActivity = { phase: 'working', label: 'Starting', step: null, of: null, leaving: false }
const approval = { id: 'a_1', title: 'A run is waiting for you', body: 'It needs your approval to go on.', source: 'your run' }
const notice = (urgent: boolean): HudNotice => ({ id: 'i_1', title: 'T', body: 'B', source: 'S', actions: [], urgent })
const proposal = { id: 'p1', title: 'P', what: 'W', howOften: 'often', hoursSaved: null, horizonWeeks: null, touches: [], never: [] }

describe('the corner column in the HUD model', () => {
  it('is in charge only when asked (the old HUD is unchanged otherwise)', () => {
    expect(setup(true).model.state().corner).toBe(true)
    expect(setup(false).model.state().corner).toBe(false)
    expect(EMPTY_HUD_STATE.corner).toBe(false)
  })

  it('sits bottom-right of the work area, 16 px in, where the old HUD sat bottom-left', () => {
    const wa = { x: 0, y: 25, width: 1440, height: 875 }
    expect(cornerBounds(wa, { width: 300, height: 38 })).toEqual({ x: 1440 - 300 - 16, y: 25 + 875 - 38 - 16, width: 300, height: 38 })
    expect(hudBounds(wa, { width: 300, height: 38 }).x).toBe(14)
    // a second display keeps its own origin
    expect(cornerBounds({ x: 1440, y: 0, width: 1920, height: 1055 }, { width: 340, height: 200 }).x).toBe(1440 + 1920 - 340 - 16)
  })

  it('holds one pill: a change is pushed once, the same activity is not pushed again', () => {
    const { model, pushed } = setup()
    model.setActivity(working)
    model.setActivity({ ...working })
    model.setActivity({ ...working, label: 'Working on it' })
    model.setActivity(null)
    model.setActivity(null)
    expect(pushed).toHaveLength(3)
    expect(model.state().activity).toBeNull()
  })

  it('an approval card appears, goes with Review (to the shell, once) and with Later, and a stale click does nothing', () => {
    const { model, sink } = setup()
    model.setApproval(approval)
    model.setApproval(approval)
    expect(model.state().approval?.id).toBe('a_1')
    expect(model.handle({ type: 'review', id: 'a_1' })).toBe(true)
    expect(sink.review).toHaveBeenCalledWith('a_1')
    expect(model.state().approval).toBeNull()
    expect(model.handle({ type: 'review', id: 'a_1' })).toBe(false)
    model.setApproval(approval)
    expect(model.handle({ type: 'later', id: 'a_1' })).toBe(true)
    expect(sink.later).toHaveBeenCalledWith('a_1')
    expect(model.handle({ type: 'later', id: 'nope' })).toBe(false)
  })

  it('Open on the error pill and End on the voice pill reach the shell', () => {
    const { model, sink } = setup()
    expect(model.handle({ type: 'pill_open' })).toBe(true)
    expect(model.handle({ type: 'voice_end' })).toBe(true)
    expect(sink.open).toHaveBeenCalledTimes(1)
    expect(sink.voiceEnd).toHaveBeenCalledTimes(1)
  })

  it('no approval card is accepted while everything is stopped; the Stopped card is the only card', async () => {
    const { model } = setup()
    await model.handle({ type: 'kill' })
    await Promise.resolve()
    model.setApproval(approval)
    expect(model.state().approval).toBeNull()
    expect(pickCard(model.state())).toEqual({ kind: 'stopped' })
  })

  it('malformed corner actions are ignored', () => {
    const { model } = setup()
    for (const bad of [{ type: 'review' }, { type: 'review', id: '' }, { type: 'later', id: 5 }, { type: 'pill_open', extra: 1 }]) {
      const ok = model.handle(bad)
      expect(typeof ok).toBe('boolean')
    }
    expect(model.handle({ type: 'review', id: '' })).toBe(false)
  })

  it('knows why cards wait, and pushes only a real change', () => {
    const { model, pushed } = setup()
    model.setHold({ secure: true })
    model.setHold({ secure: true })
    model.setHold({ share: true, ask: true })
    model.setHold({ secure: false, share: false, ask: false })
    expect(pushed).toHaveLength(3)
    expect(model.state().hold).toEqual({ secure: false, share: false, ask: false })
  })
})

describe('which card the corner draws', () => {
  const base = (over: Partial<HudState> = {}): HudState => ({ ...EMPTY_HUD_STATE, corner: true, ...over })
  it('priority: stopped, safety, approval, time, digest', () => {
    expect(HUD_CARD_PRIORITY).toEqual(['stopped', 'safety', 'approval', 'time', 'digest'])
    const all = base({ kill: { killed: true, engine: null, agent: null }, notice: notice(true), approval, proposal })
    expect(pickCard(all)?.kind).toBe('stopped')
    expect(pickCard({ ...all, kill: { killed: false, engine: null, agent: null } })?.kind).toBe('safety')
    expect(pickCard({ ...all, kill: { killed: false, engine: null, agent: null }, notice: notice(false) })?.kind).toBe('approval')
    expect(pickCard(base({ notice: notice(false), proposal }))?.kind).toBe('time')
    expect(pickCard(base({ proposal }))?.kind).toBe('digest')
    expect(pickCard(base())).toBeNull()
  })
  it('only Stopped and safety show while a password field, a screen share or the Ask bar holds the others', () => {
    for (const hold of [{ secure: true, share: false, ask: false }, { secure: false, share: true, ask: false }, { secure: false, share: false, ask: true }]) {
      expect(pickCard(base({ approval, hold }))).toBeNull()
      expect(pickCard(base({ notice: notice(false), hold }))).toBeNull()
      expect(pickCard(base({ proposal, hold }))).toBeNull()
      expect(pickCard(base({ notice: notice(true), hold }))?.kind).toBe('safety')
      expect(pickCard(base({ kill: { killed: true, engine: null, agent: null }, hold }))?.kind).toBe('stopped')
    }
  })
})
