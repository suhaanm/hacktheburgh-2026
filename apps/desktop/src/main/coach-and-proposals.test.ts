import { afterEach, describe, expect, it, vi } from 'vitest'
import type { HudProposal } from '../shared/hud'
import type { ChipFade, HelpLevel } from '../shared/protocol'
import { chipFromEngine, createChipDriver, fadeForLevel, levelFromEngine } from './coach-chip'
import { createCoachPoller } from './coach-poller'
import { createEngineClient, type EngineClient } from './engine/client'
import { parseCoachState } from './engine/coach-state'
import { closeFakeServers, fakeServer } from './engine/fake-engine.test-util'
import { createProposalScheduler, dayOf, DEFAULT_RULES, emptyMemory, isNaturalBreak, toHudProposal, type BreakSignals, type ProposalMemory } from './proposals'

afterEach(closeFakeServers)

const ID = { person: 'p_9f3a1c20', role: 'benefits-processor' }
const noTimers = { setTimer: () => 1, clearTimer: () => undefined }

describe('coach chip fade (driven by the level engine)', () => {
  it('help recedes with the level: full, full, small, dot, and gone after two clean runs at the top', () => {
    expect([1, 2, 3, 4].map((l) => fadeForLevel(l as HelpLevel, 0))).toEqual(['full', 'full', 'small', 'dot'])
    expect(fadeForLevel(4, 1)).toBe('dot')
    expect(fadeForLevel(4, 2)).toBe('gone')
    expect(fadeForLevel(3, 9)).toBe('small') // a streak only matters at the top rung
  })

  it('reads the engine hint tolerantly', () => {
    expect(chipFromEngine('dot')).toBe('dot')
    expect(chipFromEngine('huge')).toBeNull()
    expect(levelFromEngine('L3')).toBe(3)
    expect(levelFromEngine(2)).toBe(2)
    expect(levelFromEngine('L9')).toBeNull()
    expect(levelFromEngine(undefined)).toBeNull()
  })

  function driverSetup(local: { level: HelpLevel; streakClean: number }, killed = () => false) {
    let t = 0
    const sent: Array<[ChipFade, HelpLevel, string]> = []
    const driver = createChipDriver({ overlay: { coach: (f, l, label) => void sent.push([f, l, label]) }, local: () => local, killed, now: () => t, engineFreshMs: 10_000, keepAliveMs: 60_000 })
    return { driver, sent, local, advance: (ms: number) => (t += ms) }
  }

  it('sends the chip only when it changes (plus a slow keep-alive), and a returning worker sees it come back', () => {
    const local = { level: 3 as HelpLevel, streakClean: 0 }
    const { driver, sent, advance } = driverSetup(local)
    driver.refresh()
    driver.refresh()
    expect(sent).toEqual([['small', 3, 'Nudge me']])
    local.level = 4
    driver.refresh()
    local.streakClean = 2
    driver.refresh()
    expect(sent.map((s) => s[0])).toEqual(['small', 'dot', 'gone'])
    driver.refresh()
    expect(sent).toHaveLength(3) // gone is sent once
    local.level = 2 // decay after an absence lowered the level
    local.streakClean = 0
    driver.refresh()
    expect(sent.at(-1)).toEqual(['full', 2, 'Walk with me'])
    advance(61_000)
    driver.refresh()
    expect(sent).toHaveLength(5) // keep-alive resend
  })

  it('the engine hint wins while fresh, then the local level engine takes over; stopped means gone', () => {
    const local = { level: 2 as HelpLevel, streakClean: 0 }
    let killed = false
    const { driver, sent, advance } = driverSetup(local, () => killed)
    driver.setEngineHint({ fade: 'dot', level: 4 })
    expect(driver.refresh()).toBe('dot')
    advance(11_000)
    expect(driver.refresh()).toBe('full') // the hint went stale
    driver.setEngineHint({ fade: null, level: 3 })
    expect(driver.refresh()).toBe('small') // level from the engine, fade from the rule
    killed = true
    expect(driver.refresh()).toBe('gone')
    expect(sent.map((s) => s[0])).toEqual(['dot', 'full', 'small', 'gone'])
  })
})

describe('coach state parsing', () => {
  it('reads the contract fields and the optional ring target; ignores junk', () => {
    const s = parseCoachState({ task: { id: 't_204', name: 'Benefits check', step: 2, steps_total: 5 }, level: 'L3', chip: 'small', message: 'Have you checked the cliff edge?', why: 'x', mastery: {}, target: { label_hash: 'h:abcd1234' }, target_label: '  Check   this ' })
    expect(s).toEqual({ task: { id: 't_204', name: 'Benefits check', step: 2, stepsTotal: 5 }, level: 3, chip: 'small', message: 'Have you checked the cliff edge?', target: { label_hash: 'h:abcd1234' }, targetLabel: 'Check this' })
    expect(parseCoachState({ data: { level: 'L1', chip: 'full', message: 'Hi' } })).toMatchObject({ task: null, level: 1, target: null })
    expect(parseCoachState({ target: { role: 'button' } })?.target).toBeNull()
    expect(parseCoachState('nope')).toBeNull()
  })
})

describe('coach poller against a fake engine over HTTP', () => {
  const state = (over: Record<string, unknown> = {}) => ({ task: { id: 't_1', name: 'Case', step: 1, steps_total: 4 }, level: 'L2', chip: 'full', message: 'Look here', why: '', mastery: {}, target: { role: 'button', name: 'Calculate' }, ...over })

  async function setup(initial: unknown) {
    let body = initial
    const engine = await fakeServer((p) => (p.startsWith('/coach/state') ? { status: 200, body } : { status: 404 }))
    const client: EngineClient = createEngineClient({ endpoints: { engine: engine.url, agent: engine.url }, identity: ID, ...noTimers })
    const ring = { point: vi.fn(), clear: vi.fn(), followed: vi.fn(), current: vi.fn(() => ({}) as never) }
    const hints: unknown[] = []
    let fade: ChipFade = 'full'
    const chip = { setEngineHint: (h: unknown) => void hints.push(h), refresh: () => fade }
    let killed = false
    const poller = createCoachPoller({ engine: client, chip, ring, killed: () => killed, immediate: false, ...noTimers })
    return { engine, poller, ring, hints, set: (b: unknown) => (body = b), kill: () => (killed = true), setFade: (f: ChipFade) => (fade = f) }
  }

  it('asks for the coach state of this person, passes the chip hint on and rings the named element with the step number', async () => {
    const { engine, poller, ring, hints } = await setup(state({ target_label: 'Cliff edge' }))
    await poller.tick()
    expect(engine.requests.some((r) => r.path === '/coach/state?person=p_9f3a1c20')).toBe(true)
    expect(hints.at(-1)).toEqual({ fade: 'full', level: 2 })
    expect(ring.point).toHaveBeenCalledWith({ role: 'button', name: 'Calculate' }, { label: 'Cliff edge', step: 1 })
  })

  it('a step going up while the ring is shown means the step was followed; the next target gets a ring', async () => {
    const { poller, ring, set } = await setup(state())
    await poller.tick()
    set(state({ task: { id: 't_1', name: 'Case', step: 2, steps_total: 4 }, target: { label_hash: 'h:abcd1234' } }))
    await poller.tick()
    expect(ring.followed).toHaveBeenCalledTimes(1)
    expect(ring.point).toHaveBeenLastCalledWith({ label_hash: 'h:abcd1234' }, { step: 2 })
  })

  it('a finished task, a missing target, a gone chip or the kill switch remove the ring', async () => {
    const a = await setup(state())
    await a.poller.tick()
    a.set(state({ task: null, target: undefined }))
    await a.poller.tick()
    expect(a.ring.clear).toHaveBeenCalledWith('ended')

    const b = await setup(state())
    await b.poller.tick()
    b.setFade('gone') // the chip has faded away: no more pointing
    await b.poller.tick()
    expect(b.ring.clear).toHaveBeenCalledWith('user')

    const c = await setup(state())
    c.kill()
    await c.poller.tick()
    expect(c.ring.point).not.toHaveBeenCalled()
  })

  it('an engine that is down leaves the ring and chip to their own timers and never throws', async () => {
    const { engine, poller, ring, hints } = await setup(state())
    await engine.close()
    await poller.tick()
    expect(hints.at(-1)).toBeNull()
    expect(ring.point).not.toHaveBeenCalled()
  })
})

// ---------- proposals ----------
const quiet: BreakSignals = { idleSeconds: () => 0, lessonActive: () => false, confirmPending: () => false, killed: () => false, locked: () => false, task: () => null, lastEpisodeEndAt: () => null }
const sig = (over: Partial<BreakSignals>): BreakSignals => ({ ...quiet, ...over })

describe('natural breaks', () => {
  const now = 1_000_000

  it('is a break after a pause, or right after an episode when it is quiet; never mid-lesson, locked, stopped or while a prompt is open', () => {
    expect(isNaturalBreak(sig({ idleSeconds: () => 5 }), now)).toBe(false)
    expect(isNaturalBreak(sig({ idleSeconds: () => 15 }), now)).toBe(true)
    expect(isNaturalBreak(sig({ idleSeconds: () => 4, lastEpisodeEndAt: () => now - 30_000 }), now)).toBe(true)
    expect(isNaturalBreak(sig({ idleSeconds: () => 4, lastEpisodeEndAt: () => now - 200_000 }), now)).toBe(false)
    for (const over of [{ lessonActive: () => true }, { locked: () => true }, { killed: () => true }, { confirmPending: () => true }]) {
      expect(isNaturalBreak(sig({ idleSeconds: () => 600, ...over }), now), JSON.stringify(Object.keys(over))).toBe(false)
    }
  })

  it('while the engine says a task is in progress it takes a long pause, and after the last step the usual rules apply', () => {
    expect(isNaturalBreak(sig({ idleSeconds: () => 30, task: () => ({ step: 2, stepsTotal: 5 }) }), now)).toBe(false)
    expect(isNaturalBreak(sig({ idleSeconds: () => DEFAULT_RULES.midTaskIdleS, task: () => ({ step: 2, stepsTotal: 5 }) }), now)).toBe(true)
    expect(isNaturalBreak(sig({ idleSeconds: () => 20, task: () => ({ step: 5, stepsTotal: 5 }) }), now)).toBe(true)
  })
})

describe('proposal scheduler against a fake engine over HTTP', () => {
  const routine = (id: string, hours: number, status = 'proposed') => ({ id, title: `Routine ${id}`, status, minutes_per_week: 60, value: { hours_saved: [hours, hours + 1] }, touches: ['case note'], never: ['submit'], proposal: { what: `What ${id}`, how_often: 'about 14 times in 3 weeks' } })

  async function setup(routines: unknown[], over: { signals?: Partial<BreakSignals>; maxPerDay?: number; minGapMs?: number; store?: { m: ProposalMemory | null } } = {}) {
    let t = new Date('2026-11-07T10:00:00').getTime()
    const engine = await fakeServer((p) => (p === '/routines' ? { status: 200, body: routines } : p.includes('/consent') ? { status: 200, body: {} } : { status: 404 }))
    const client = createEngineClient({ endpoints: { engine: engine.url, agent: engine.url }, identity: ID, ...noTimers })
    let proposal: HudProposal | null = null
    const hud = { setProposal: (p: HudProposal | null) => void (proposal = p), state: () => ({ proposal }) }
    const store = over.store ? { load: () => over.store!.m, save: (m: ProposalMemory) => void (over.store!.m = m) } : undefined
    const sched = createProposalScheduler({ engine: client, hud, signals: sig({ idleSeconds: () => 60, ...over.signals }), now: () => t, maxPerDay: over.maxPerDay, minGapMs: over.minGapMs ?? 20 * 60_000, store, ...noTimers })
    return { engine, sched, hud, advance: (ms: number) => (t += ms), get proposal() { return proposal }, now: () => t }
  }

  it('shows the best proposal (most hours) at a break, once, with the card the HUD expects', async () => {
    const s = await setup([routine('small', 1), routine('big', 4), routine('declined', 9, 'declined')])
    expect(await s.sched.tick()).toBe('shown')
    expect(s.proposal).toEqual({ id: 'big', title: 'Routine big', what: 'What big', howOften: 'about 14 times in 3 weeks', hoursSaved: [4, 5], touches: ['case note'], never: ['submit'] })
    expect(await s.sched.tick()).toBe('showing')
    expect(toHudProposal({ id: 'x', title: 'T', status: 'proposed', minutesPerWeek: null, hoursSaved: null, episodes: null, touches: [], never: [], what: '', howOften: '' }).what).toBe('T')
  })

  it('never mid-task: no toast without a break, then it appears when the break comes', async () => {
    let idle = 2
    const s = await setup([routine('r1', 3)], { signals: { idleSeconds: () => idle } })
    expect(await s.sched.tick()).toBe('not_a_break')
    expect(s.proposal).toBeNull()
    idle = 40
    expect(await s.sched.tick()).toBe('shown')
  })

  it('Not now snoozes the routine and tells the engine; Never for this stops it for good and tells the engine; Look at it stops the toasts', async () => {
    const s = await setup([routine('a', 5), routine('b', 4), routine('c', 3)], { minGapMs: 0, maxPerDay: 10 })
    await s.sched.tick()
    s.sched.choice('a', 'not_now')
    await new Promise((r) => setTimeout(r, 30))
    expect(s.engine.requests).toContainEqual({ method: 'POST', path: '/routines/a/consent', body: { mode: 'not_now', irreversible_unattended: [], typed_confirm: '' } })
    s.advance(60_000)
    await s.sched.tick() // next candidate is b (a is snoozed)
    expect(s.proposal?.id).toBe('b')
    s.sched.choice('b', 'never')
    await new Promise((r) => setTimeout(r, 30))
    expect(s.engine.requests.some((r) => r.path === '/routines/b/consent' && (r.body as { mode: string }).mode === 'never')).toBe(true)
    s.advance(60_000)
    await s.sched.tick()
    expect(s.proposal?.id).toBe('c')
    s.sched.choice('c', 'look')
    s.advance(5 * 3_600_000)
    expect(await s.sched.tick()).toBe('shown') // a is back after the snooze; b and c never again
    expect(s.proposal?.id).toBe('a')
    expect(s.engine.requests.filter((r) => r.path.endsWith('/consent') && r.path.includes('/c/')).length).toBe(0) // Look at it sends no consent
  })

  it('keeps to a daily budget and a gap, and starts again tomorrow', async () => {
    const s = await setup([routine('a', 5), routine('b', 4), routine('c', 3), routine('d', 2)], { maxPerDay: 2, minGapMs: 10 * 60_000 })
    await s.sched.tick()
    s.sched.choice('a', 'not_now')
    expect(await s.sched.tick()).toBe('budget') // too soon after the last toast
    s.advance(11 * 60_000)
    expect(await s.sched.tick()).toBe('shown')
    s.sched.choice('b', 'not_now')
    s.advance(30 * 60_000)
    expect(await s.sched.tick()).toBe('budget') // two today already
    s.advance(24 * 3_600_000)
    expect(await s.sched.tick()).toBe('shown')
    expect(s.sched.memory().day).toBe(dayOf(s.now()))
  })

  it('a toast nobody answers leaves, comes back later, and after two ignores waits a day', async () => {
    let fire: (() => void) | null = null
    let t = new Date('2026-11-07T10:00:00').getTime()
    const engine = await fakeServer((p) => (p === '/routines' ? { status: 200, body: [routine('r', 3)] } : { status: 404 }))
    const client = createEngineClient({ endpoints: { engine: engine.url, agent: engine.url }, identity: ID, ...noTimers })
    let proposal: HudProposal | null = null
    const sched = createProposalScheduler({
      engine: client,
      hud: { setProposal: (p) => void (proposal = p), state: () => ({ proposal }) },
      signals: sig({ idleSeconds: () => 60 }),
      now: () => t,
      minGapMs: 0,
      maxPerDay: 10,
      setTimer: (fn, ms) => (ms === 45_000 ? ((fire = fn), 1) : 1),
      clearTimer: () => undefined,
    })
    expect(await sched.tick()).toBe('shown')
    fire!()
    expect(proposal).toBeNull() // it left on its own
    t += 3600_000
    expect(await sched.tick()).toBe('none') // too soon to offer it again
    t += 2 * 3600_000
    expect(await sched.tick()).toBe('shown')
    fire!()
    t += 5 * 3600_000
    expect(await sched.tick()).toBe('none') // ignored twice: a day's rest
    t += 25 * 3600_000
    expect(await sched.tick()).not.toBe('none')
  })

  it('the HUD refusing (everything is stopped) is not counted as shown, and an engine that is down shows nothing', async () => {
    const s = await setup([routine('r', 3)])
    s.hud.setProposal = () => undefined // stopped HUD
    expect(await s.sched.tick()).toBe('waiting')
    const down = await setup([routine('r', 3)])
    await down.engine.close()
    expect(await down.sched.tick()).toBe('none')
  })

  it('remembers across restarts: what was offered and declined is not offered again', async () => {
    const store = { m: null as ProposalMemory | null }
    const first = await setup([routine('r', 3)], { store })
    await first.sched.tick()
    first.sched.choice('r', 'never')
    expect(store.m?.routines.r?.state).toBe('never')
    const second = await setup([routine('r', 3)], { store })
    expect(await second.sched.tick()).toBe('none')
    expect(emptyMemory('2026-11-07').shownToday).toBe(0)
  })
})
