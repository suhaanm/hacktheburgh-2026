import { afterEach, describe, expect, it, vi } from 'vitest'
import type { HudProposal } from '../shared/hud'
import type { ChipFade, HelpLevel } from '../shared/protocol'
import { chipFromEngine, createChipDriver, fadeForLevel, levelFromEngine } from './coach-chip'
import { createCoachBrain, outcomeFor } from './coach-brain'
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

  it('what the coach is acting at (GET /coach/next) wins over the state hint while fresh, then the state hint takes over again', () => {
    const { driver, advance } = driverSetup({ level: 2 as HelpLevel, streakClean: 0 })
    driver.setEngineHint({ fade: 'gone', level: 4 }) // /coach/state: this learner is done...
    driver.setDecisionHint({ fade: 'full', level: 1 }) // ...but study mode has the coach acting at L1
    expect(driver.refresh()).toBe('full')
    expect(driver.current()).toEqual({ fade: 'full', level: 1 })
    advance(11_000)
    driver.setEngineHint({ fade: 'gone', level: 4 })
    expect(driver.refresh()).toBe('gone') // the decision hint went stale
  })
})

describe('coach state parsing', () => {
  it('reads the contract fields; ignores junk', () => {
    const s = parseCoachState({ task: { id: 't_204', name: 'Benefits check', step: 2, steps_total: 5 }, level: 'L3', chip: 'small', message: 'Have you checked the cliff edge?', why: 'x', mastery: {} })
    expect(s).toEqual({ task: { id: 't_204', name: 'Benefits check', step: 2, stepsTotal: 5 }, level: 3, chip: 'small', message: 'Have you checked the cliff edge?' })
    expect(parseCoachState({ data: { level: 'L1', chip: 'full', message: 'Hi' } })).toMatchObject({ task: null, level: 1 })
    expect(parseCoachState('nope')).toBeNull()
  })
})

describe('coach state poller against a fake engine over HTTP', () => {
  const state = (over: Record<string, unknown> = {}) => ({ task: { id: 't_1', name: 'Case', step: 1, steps_total: 4 }, level: 'L2', chip: 'full', message: 'Look here', why: '', mastery: {}, ...over })

  async function setup(initial: unknown) {
    const body = initial
    const engine = await fakeServer((p) => (p.startsWith('/coach/state') ? { status: 200, body } : { status: 404 }))
    const client: EngineClient = createEngineClient({ endpoints: { engine: engine.url, agent: engine.url }, identity: ID, ...noTimers })
    const hints: unknown[] = []
    const tasks: unknown[] = []
    const poller = createCoachPoller({ engine: client, chip: { setEngineHint: (h: unknown) => void hints.push(h), refresh: () => 'full' as ChipFade }, onTask: (t) => void tasks.push(t), immediate: false, ...noTimers })
    return { engine, poller, hints, tasks }
  }

  it('asks for the coach state of this person, passes the chip hint and the task on', async () => {
    const { engine, poller, hints, tasks } = await setup(state())
    await poller.tick()
    expect(engine.requests.some((r) => r.path === '/coach/state?person=p_9f3a1c20')).toBe(true)
    expect(hints.at(-1)).toEqual({ fade: 'full', level: 2 })
    expect(tasks.at(-1)).toEqual({ id: 't_1', name: 'Case', step: 1, stepsTotal: 4 })
    expect(poller.lastState()?.level).toBe(2)
  })

  it('an engine that is down clears the hint and never throws', async () => {
    const { engine, poller, hints } = await setup(state())
    await engine.close()
    await poller.tick()
    expect(hints.at(-1)).toBeNull()
    expect(poller.lastState()).toBeNull()
  })
})

describe('coach next parsing', () => {
  const next = (over: Record<string, unknown> = {}) => ({ meta: { origin: 'real' }, data: { action: 'annotate', message: 'Check the cliff edge before you copy.', why: 'You skipped it last time.', target: { zone: 'calc_result', label_hint: 'Result', role_hint: 'status' }, level: 'L2', decision_id: 'd_0001', ...over } })

  it('reads the decision, the zone target with its hints, the level and the decision id', async () => {
    const { parseCoachNext } = await import('./engine/coach-next')
    expect(parseCoachNext(next())).toEqual({ action: 'annotate', message: 'Check the cliff edge before you copy.', why: 'You skipped it last time.', target: { zone: 'calc_result', label_hint: 'Result', role_hint: 'status' }, level: 2, chip: null, decisionId: 'd_0001', reasons: [], step: null, missed: [] })
    expect(parseCoachNext(next({ reason_codes: ['already_prompted', 'on_track', 'Bad Code!', 7], step: 'cliff_a', missed: ['cliff_a', 'no good'], chip: 'small' }))).toMatchObject({ reasons: ['already_prompted', 'on_track'], step: 'cliff_a', missed: ['cliff_a'], chip: 'small' })
    expect(parseCoachNext(next({ target: null }))).toMatchObject({ target: null })
    expect(parseCoachNext(next({ target: { zone: 'Bad Zone' } }))).toMatchObject({ target: null })
    expect(parseCoachNext(next({ target: { label_hash: 'h:abcd1234' } }))).toMatchObject({ target: null }) // only zones are rung from here
    expect(parseCoachNext(next({ decision_id: 'bad id!' }))).toMatchObject({ decisionId: null })
  })

  it('an action it does not know is silence, never something to act on', async () => {
    const { parseCoachNext } = await import('./engine/coach-next')
    expect(parseCoachNext(next({ action: 'delete_everything' }))?.action).toBe('silent')
    expect(parseCoachNext({ data: {} })?.action).toBe('silent')
    expect(parseCoachNext(null)).toBeNull()
    expect(parseCoachNext({ action: 'takeover_offer', target: { zone: 'a_b' } })?.action).toBe('takeover_offer')
  })
})

describe('coach brain: rings by zone, and the worker\'s response goes to /coach/feedback', () => {
  const task = (step: number, id = 't_1') => ({ id, name: 'Case', step, stepsTotal: 8 })
  const decision = (over: Record<string, unknown> = {}) => ({ meta: {}, data: { action: 'annotate', message: 'Check the result first.', why: 'w', target: { zone: 'calc_result' }, level: 'L2', decision_id: 'd_1', ...over } })
  // What the engine says on the polls after it spoke: silent, no decision id, and `already_prompted` while the issue is still open.
  const quietAfter = (reasons: string[]) => ({ meta: {}, data: { action: 'silent', message: '', why: '', target: null, level: 'L1', decision_id: null, reason_codes: reasons } })

  async function setup(initial: unknown, initialTask: ReturnType<typeof task> | null = task(2)) {
    let body = initial
    let events: unknown[] = []
    const engine = await fakeServer((p) => (p.startsWith('/coach/next') ? { status: 200, body } : p.startsWith('/events') ? { status: 200, body: { events } } : p === '/coach/feedback' ? { status: 200, body: { recorded: true } } : { status: 404 }))
    const client: EngineClient = createEngineClient({ endpoints: { engine: engine.url, agent: engine.url }, identity: ID, ...noTimers })
    let current: ReturnType<typeof task> | null = initialTask
    let killed = false
    const ringCalls: Array<[string, unknown?]> = []
    const said: string[] = []
    let ringActive = false
    const ring = {
      point: (t: unknown, o: unknown) => void (ringCalls.push(['point', { t, o }]), (ringActive = true)),
      clear: (how?: string) => void (ringCalls.push(['clear', how]), (ringActive = false)),
      followed: () => void (ringCalls.push(['followed']), (ringActive = false)),
      current: () => (ringActive ? ({} as never) : null),
    }
    const brain = createCoachBrain({ engine: client, state: () => (current ? { task: current, level: 2, chip: 'full', message: '' } : null), ring, say: (t) => void said.push(t), killed: () => killed, immediate: false, ...noTimers })
    return { engine, brain, ringCalls, said, ended: () => void (ringActive = false), events: (e: unknown[]) => (events = e), set: (b: unknown) => (body = b), setTask: (t: typeof current) => (current = t), kill: () => (killed = true) }
  }
  const feedbacks = (e: Awaited<ReturnType<typeof setup>>['engine']) => e.requests.filter((r) => r.path === '/coach/feedback').map((r) => r.body)

  it('while a task is active, asks /coach/next for this person and rings the ZONE with the nudge text and the decision id (no step badge: the engine task step is not the coach step)', async () => {
    const s = await setup(decision())
    await s.brain.tick()
    expect(s.engine.requests.some((r) => r.path === '/coach/next?person=p_9f3a1c20')).toBe(true)
    expect(s.ringCalls).toEqual([['point', { t: { zone: 'calc_result' }, o: { message: 'Check the result first.', ref: 'd_1' } }]])
    await s.brain.tick() // the same decision again: nothing new
    expect(s.ringCalls).toHaveLength(1)
    expect(s.brain.lastActiveDecisionAt()).not.toBeNull()
    expect(s.brain.status()).toMatchObject({ ringDecision: 'd_1', lastDecision: { action: 'annotate', decisionId: 'd_1', zone: 'calc_result' } })
  })

  it('does not ask at all when no task is in progress, and removes the ring when the task ends', async () => {
    const s = await setup(decision(), null)
    await s.brain.tick()
    expect(s.engine.requests.filter((r) => r.path.startsWith('/coach/next'))).toHaveLength(0)
    s.setTask(task(2))
    await s.brain.tick()
    s.setTask(null)
    await s.brain.tick()
    expect(s.ringCalls.at(-1)).toEqual(['clear', 'ended'])
  })

  it('silent and takeover_offer draw nothing (the desktop never acts on an offer)', async () => {
    for (const d of [{ action: 'silent', target: null }, { action: 'takeover_offer', target: { zone: 'calc_go' } }]) {
      const s = await setup(decision(d))
      await s.brain.tick()
      expect(s.ringCalls.filter((c) => c[0] === 'point'), JSON.stringify(d)).toHaveLength(0)
      expect(s.said).toEqual([])
    }
  })

  it('a nudge with nothing to point at is said once, as text (lighter help), and never draws a ring', async () => {
    const s = await setup(decision({ action: 'nudge', target: null, message: 'Is any figure close to a limit?', decision_id: 'd_7' }))
    await s.brain.tick()
    await s.brain.tick()
    expect(s.said).toEqual(['Is any figure close to a limit?'])
    expect(s.ringCalls).toEqual([])
    s.set(decision({ action: 'nudge', target: null, message: 'Another question?', decision_id: 'd_8' }))
    await s.brain.tick()
    expect(s.said).toEqual(['Is any figure close to a limit?', 'Another question?'])
  })

  it('a new decision moves the ring', async () => {
    const s = await setup(decision())
    await s.brain.tick()
    s.set(decision({ decision_id: 'd_2', target: { zone: 'calc_note' }, message: 'Now the note.' }))
    await s.brain.tick()
    expect(s.ringCalls.filter((c) => c[0] === 'point')).toHaveLength(2)
  })

  it('the engine speaks once: silent polls (already_prompted, or nothing at all) keep the ring; reason codes are never read as "followed"', async () => {
    const s = await setup(decision())
    await s.brain.tick()
    for (const reasons of [['already_prompted', 'on_track'], ['on_track'], []]) {
      s.set(quietAfter(reasons))
      await s.brain.tick()
      await s.brain.watch()
    }
    expect(s.ringCalls).toHaveLength(1) // still up: no clear, no followed
    expect(s.brain.status().ringDecision).toBe('d_1')
  })

  it('followed means the worker used the element the ring is on: their own event on that zone, after the ring came up', async () => {
    const s = await setup(decision({ target: { zone: 'cliff_button' } }))
    await s.brain.tick()
    const asked = () => s.engine.requests.filter((r) => r.path.startsWith('/events')).map((r) => new URL(`http://x${r.path}`).searchParams)
    s.events([]) // nothing yet
    await s.brain.watch()
    expect(s.ringCalls).toHaveLength(1)
    s.events([{ type: 'click', t: new Date(Date.now() - 60_000).toISOString(), meta: { zone: 'cliff_button' } }]) // before the ring: not a response to it
    await s.brain.watch()
    s.events([{ type: 'click', t: new Date().toISOString(), meta: { zone: 'calc_result' } }, { type: 'scroll', t: new Date().toISOString(), meta: { zone: 'cliff_button' } }]) // another zone, or not an interaction
    await s.brain.watch()
    expect(s.ringCalls).toHaveLength(1)
    s.events([{ type: 'click', t: new Date(Date.now() + 50).toISOString(), meta: { zone: 'cliff_button' } }])
    await s.brain.watch()
    expect(s.ringCalls.at(-1)).toEqual(['followed'])
    expect(s.brain.status().ringDecision).toBeNull()
    const q = asked().at(-1)
    expect(q?.get('partition')).toBe('real')
    expect(q?.get('person')).toBe('p_9f3a1c20')
    expect(q?.get('since')).toMatch(/^\d{4}-\d\d-\d\dT/)
  })

  it('does not look for the worker unless a ring is up, and an engine that does not answer ends nothing', async () => {
    const s = await setup(decision())
    await s.brain.watch()
    expect(s.engine.requests.filter((r) => r.path.startsWith('/events'))).toHaveLength(0)
    await s.brain.tick()
    await s.engine.close()
    await s.brain.watch()
    expect(s.ringCalls).toHaveLength(1)
  })

  it('the case ending, or study mode silencing the coach, ends the ring without a response', async () => {
    for (const reasons of [['no_active_task'], ['study_mode', 'study_post_test'], ['no_events']]) {
      const s = await setup(decision())
      await s.brain.tick()
      s.set(quietAfter(reasons))
      await s.brain.tick()
      expect(s.ringCalls.at(-1), reasons.join()).toEqual(['clear', 'ended'])
    }
  })

  it('a takeover offer replaces the ring (it ends, nothing is posted); a ring the worker stopped is not drawn again', async () => {
    const s = await setup(decision())
    await s.brain.tick()
    s.set(decision({ action: 'takeover_offer', decision_id: 'd_5' }))
    await s.brain.tick()
    expect(s.ringCalls.at(-1)).toEqual(['clear', 'ended'])

    const t = await setup(decision())
    await t.brain.tick()
    t.ended() // the worker pressed Stop: the ring is gone on its own
    await t.brain.tick() // the (repeating) engine says the same thing: not drawn again
    expect(t.ringCalls.filter((c) => c[0] === 'point')).toHaveLength(1)
  })

  it('posts followed and dismissed (and only those, only for prompts that were really drawn, only for the brain\'s own decisions) and keeps what the engine said', async () => {
    const s = await setup(decision())
    const end = (how: Parameters<typeof s.brain.onPromptEnd>[0]['how'], over: Partial<Parameters<typeof s.brain.onPromptEnd>[0]> = {}) => s.brain.onPromptEnd({ ref: 'd_1', how, shown: true, ...over })
    end('followed')
    end('stop')
    end('user')
    end('replaced')
    end('stale')
    end('ended')
    end('followed', { shown: false }) // never drawn
    end('followed', { ref: undefined }) // not a brain decision (POST /coach/ring)
    await new Promise((r) => setTimeout(r, 50))
    expect(feedbacks(s.engine)).toEqual([
      { decision_id: 'd_1', outcome: 'followed' },
      { decision_id: 'd_1', outcome: 'dismissed' },
      { decision_id: 'd_1', outcome: 'dismissed' },
    ])
    expect(s.brain.status().lastFeedback).toMatchObject({ decisionId: 'd_1', ok: true, recorded: true })
  })

  it('stopped means no ring and no question; an engine that is down keeps what is there and never throws', async () => {
    const s = await setup(decision())
    await s.brain.tick()
    s.kill()
    await s.brain.tick()
    expect(s.ringCalls.at(-1)).toEqual(['clear', 'ended'])

    const down = await setup(decision())
    await down.engine.close()
    await down.brain.tick()
    expect(down.ringCalls).toHaveLength(0)
  })

  it('tells the chip which level and fade the engine is acting at (study mode included), every time it answers', async () => {
    const s = await setup(decision({ level: 'L1', chip: 'full' }))
    const hints: unknown[] = []
    const brain = createCoachBrain({ engine: createEngineClient({ endpoints: { engine: s.engine.url, agent: s.engine.url }, identity: ID, ...noTimers }), state: () => ({ task: task(1), level: 4, chip: 'gone', message: '' }), ring: { point: () => undefined, clear: () => undefined, followed: () => undefined, current: () => null }, chip: { setDecisionHint: (h) => void hints.push(h), refresh: () => 'full' }, immediate: false, ...noTimers })
    await brain.tick()
    expect(hints).toEqual([{ fade: 'full', level: 1 }])
  })

  it('outcomeFor maps only the worker\'s own responses', () => {
    expect(['followed', 'user', 'stop', 'replaced', 'stale', 'ended'].map((h) => outcomeFor(h as never))).toEqual(['followed', 'dismissed', 'dismissed', null, null, null])
  })
})

describe('feedback goes to the engine whatever the capture preference says', () => {
  it('client.coachFeedback posts decision_id and outcome', async () => {
    const engine = await fakeServer(() => ({ status: 200, body: {} }))
    const client = createEngineClient({ endpoints: { engine: engine.url, agent: engine.url }, identity: ID, ...noTimers })
    expect(await client.coachFeedback('d_9', 'dismissed')).toEqual({ ok: true, recorded: null, note: null })
    expect(engine.requests[0]).toEqual({ method: 'POST', path: '/coach/feedback', body: { decision_id: 'd_9', outcome: 'dismissed' } })
  })

  it('reads whether the engine recorded it, and says so plainly when the engine did not answer', async () => {
    const engine = await fakeServer(() => ({ status: 200, body: { decision_id: 'd_9', outcome: 'followed', recorded: false, note: 'already recorded' } }))
    const client = createEngineClient({ endpoints: { engine: engine.url, agent: engine.url }, identity: ID, ...noTimers })
    expect(await client.coachFeedback('d_9', 'followed')).toEqual({ ok: true, recorded: false, note: 'already recorded' })
    await engine.close()
    expect(await client.coachFeedback('d_9', 'followed')).toEqual({ ok: false, recorded: null, note: null })
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

  it('a coach prompt in the last minute counts as mid-task: only a long pause is a break, then the usual rules apply again', () => {
    const decided = sig({ idleSeconds: () => 20, lastCoachDecisionAt: () => now - 20_000 })
    expect(isNaturalBreak(decided, now)).toBe(false)
    expect(isNaturalBreak(sig({ idleSeconds: () => DEFAULT_RULES.midTaskIdleS, lastCoachDecisionAt: () => now - 20_000 }), now)).toBe(true)
    expect(isNaturalBreak(sig({ idleSeconds: () => 20, lastCoachDecisionAt: () => now - 61_000 }), now)).toBe(true)
    expect(isNaturalBreak(sig({ idleSeconds: () => 20, lastCoachDecisionAt: () => null }), now)).toBe(true)
  })

  it('while the engine says a task is in progress it takes a long pause, and after the last step the usual rules apply', () => {
    expect(isNaturalBreak(sig({ idleSeconds: () => 30, task: () => ({ step: 2, stepsTotal: 5 }) }), now)).toBe(false)
    expect(isNaturalBreak(sig({ idleSeconds: () => DEFAULT_RULES.midTaskIdleS, task: () => ({ step: 2, stepsTotal: 5 }) }), now)).toBe(true)
    expect(isNaturalBreak(sig({ idleSeconds: () => 20, task: () => ({ step: 5, stepsTotal: 5 }) }), now)).toBe(true)
  })
})

describe('proposal scheduler against a fake engine over HTTP', () => {
  const routine = (id: string, hours: number, status = 'proposed') => ({ id, title: `Routine ${id}`, status, minutes_per_week: 60, value: { hours_saved: [hours, hours + 1], horizon_weeks: 4 }, touches: ['case note'], never: ['submit'], proposal: { what: `What ${id}`, how_often: 'about 14 times in 3 weeks' } })

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
    expect(s.proposal).toEqual({ id: 'big', title: 'Routine big', what: 'What big', howOften: 'about 14 times in 3 weeks', hoursSaved: [4, 5], horizonWeeks: 4, touches: ['case note'], never: ['submit'] })
    expect(await s.sched.tick()).toBe('showing')
    expect(toHudProposal({ id: 'x', title: 'T', status: 'proposed', minutesPerWeek: null, hoursSaved: null, horizonWeeks: null, episodes: null, touches: [], never: [], what: '', howOften: '' }).what).toBe('T')
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

describe('chip driver after the overlay page reloads', () => {
  it('force sends the chip again even when nothing changed (and a gone chip too)', () => {
    const sent: string[] = []
    const d = createChipDriver({ overlay: { coach: (f) => void sent.push(f) }, local: () => ({ level: 3 as HelpLevel, streakClean: 0 }) })
    d.refresh()
    d.refresh()
    d.refresh(true)
    expect(sent).toEqual(['small', 'small'])
    const g = createChipDriver({ overlay: { coach: (f) => void sent.push(f) }, local: () => ({ level: 4 as HelpLevel, streakClean: 3 }) })
    g.refresh()
    g.refresh()
    g.refresh(true)
    expect(sent.slice(2)).toEqual(['gone', 'gone'])
  })
})
