import { describe, expect, it } from 'vitest'
import { createActForMe, ghostPath } from '../../src/main/agency/act-for-me'
import { Situation } from '../../src/main/agency/common'
import type { Proposal, ProposeRequest, ProposedStep } from '../../src/main/agency/computer-use'
import type { AgentChip } from '../../src/shared/protocol'
import { makeEnv, shot, type Env } from './helpers'

const GOAL = 'Find the opening times on the library page'

type Step = Partial<ProposedStep> & Pick<ProposedStep, 'tool'>

const action = (step: Step): Proposal => ({
  kind: 'action',
  ms: 1,
  step: { id: `${step.tool}:${step.point?.x ?? ''}:${step.point?.y ?? ''}:${step.text ?? ''}:${step.keys ?? ''}`, intent: '', ...step },
})
const click = (x: number, y: number, intent = 'Click the Start button', extra: Partial<ProposedStep> = {}): Proposal => action({ tool: 'click', point: { x, y }, intent, ...extra })
const finished = (text = 'All done.'): Proposal => ({ kind: 'finished', text, ms: 1 })

function setup(opts: Parameters<typeof makeEnv>[0] = {}, queue: Proposal[] = [], extra: { maxSteps?: number; totalMs?: number; loop?: boolean; onPropose?: (req: ProposeRequest) => void } = {}) {
  const env = makeEnv(opts)
  const sit = new Situation(env.ctx)
  const requests: ProposeRequest[] = []
  const proposals = [...queue]
  const act = createActForMe(env.deps, sit, async (k) => void env.learned.push(k), {
    gemini: () => {
      throw new Error('the model must not be reached in these tests')
    },
    loopEnabled: () => extra.loop ?? true,
    maxSteps: extra.maxSteps,
    totalMs: extra.totalMs,
    propose: async (req) => {
      requests.push({ ...req, history: [...req.history] })
      extra.onPropose?.(req)
      return proposals.shift() ?? finished('Nothing more to do.')
    },
  })
  return { env, sit, act, requests, proposals }
}
const nothingHappened = (env: Env) => {
  expect(env.calls).toEqual([])
}
const lastAudit = (env: Env) => env.auditLines().at(-1)

describe('act_for_me', () => {
  it('shows the ring and the ghost cursor BEFORE the confirmation, clicks once, verifies, and counts it', async () => {
    const { env, act, requests } = setup({}, [click(500, 400), finished()])
    let ringBefore = false
    let ghostBefore = false
    env.answers.push(() => {
      const all = env.shown.flat()
      ringBefore = all.some((a) => a.kind === 'ring')
      ghostBefore = all.some((a) => a.kind === 'ghostCursor')
      return 'Yes, do it'
    })
    const r = await act.run(GOAL)
    expect(ringBefore && ghostBefore).toBe(true)
    expect(env.asked).toEqual([{ question: "I'll click the Start button. OK?", options: ['Yes, do it', 'No, I will'] }])
    expect(env.calls).toEqual(['click 500,400'])
    expect(r).toMatchObject({ allowed: true, done: true, code: 'done', steps: 1, verified: true })
    expect(r.reason).toMatch(/offer to show/i)
    expect(env.learned).toEqual(['task:find the opening times on the library page'])
    expect(env.grabs).toContain('verify')
    // the model got the goal as the only task, a fresh shot each time, and the history of what was already done
    expect(requests[0]).toMatchObject({ goal: GOAL, history: [] })
    expect(requests[1].history).toHaveLength(1)
    expect(requests[1].history[0]).toMatch(/click the Start button/i)
    expect(env.auditLines().map((l) => [l.code, l.step])).toEqual([['step', 1], ['done', 1]])
    expect(env.cleared.at(-1)).toBeDefined()
  })

  it('agency off: refuses before any screenshot, question or action', async () => {
    const { env, act, requests } = setup({ agency: 'off' }, [click(1, 1)])
    expect(await act.run(GOAL)).toMatchObject({ allowed: false, done: false, code: 'agency_off' })
    nothingHappened(env)
    expect(env.asked).toEqual([])
    expect(env.grabs).toEqual([])
    expect(requests).toEqual([])
    expect(lastAudit(env)).toMatchObject({ decision: 'refused', code: 'agency_off' })
  })

  it('a goal with a denylisted word is refused up front', async () => {
    const { env, act, requests } = setup({}, [click(1, 1)])
    const r = await act.run('Buy a new phone case for me')
    expect(r).toMatchObject({ allowed: false, done: false, code: 'blocked' })
    expect(requests).toEqual([])
    expect(env.grabs).toEqual([])
    nothingHappened(env)
  })

  it('a scam check in progress refuses the task', async () => {
    const { env, act } = setup({}, [click(1, 1)])
    env.state.patch({ skill: { id: 'spot_scam', name: 'Spot a scam', step: 1, stepCount: 3 } })
    expect(await act.run(GOAL)).toMatchObject({ allowed: false, code: 'scam_check' })
    nothingHappened(env)
  })

  it('stays unavailable unless the loop flag is on', async () => {
    const { env, act, requests } = setup({}, [click(1, 1)], { loop: false })
    expect(await act.run(GOAL)).toMatchObject({ allowed: false, done: false, code: 'unavailable' })
    expect(requests).toEqual([])
    expect(env.grabs).toEqual([])
    expect(lastAudit(env)).toMatchObject({ decision: 'unavailable' })
  })

  it('declined: nothing is clicked and the chip is cancelled', async () => {
    const { env, act } = setup({}, [click(500, 400), finished()])
    env.answers.push('no')
    expect(await act.run(GOAL)).toMatchObject({ allowed: true, done: false, code: 'declined', steps: 0 })
    nothingHappened(env)
    expect(env.state.get().agents.find((a) => a.title === 'Doing this for you')?.status).toBe('cancelled')
    expect(lastAudit(env)).toMatchObject({ decision: 'declined' })
  })

  it('no answer at all counts as no', async () => {
    const { env, act } = setup({}, [click(500, 400)])
    env.answers.push('null')
    expect(await act.run(GOAL)).toMatchObject({ code: 'declined', done: false })
    nothingHappened(env)
  })

  it('Stop while the confirmation is open: nothing executes', async () => {
    const { env, act } = setup({}, [click(500, 400), finished()])
    env.answers.push(() => {
      env.bus.emit('session:ended', { reason: 'stop' })
      return 'Yes, do it'
    })
    expect(await act.run(GOAL)).toMatchObject({ code: 'stopped', done: false })
    nothingHappened(env)
    expect(lastAudit(env)).toMatchObject({ decision: 'stopped' })
  })

  it('Stop during the model call: the proposed action is dropped, no question, no action', async () => {
    const { env, act } = setup({}, [click(500, 400), finished()], { onPropose: () => env.bus.emit('session:ended', { reason: 'stop' }) })
    expect(await act.run(GOAL)).toMatchObject({ code: 'stopped', done: false, steps: 0 })
    nothingHappened(env)
    expect(env.asked).toEqual([])
  })

  it('act.stop() ends a running task the same way', async () => {
    const { env, act } = setup({}, [click(500, 400), finished()], { onPropose: () => act.stop() })
    expect(await act.run(GOAL)).toMatchObject({ code: 'stopped' })
    nothingHappened(env)
    expect(act.isRunning()).toBe(false)
  })

  it('settings switched off while the confirmation is open: the approval is not used', async () => {
    const { env, act } = setup({}, [click(500, 400), finished()])
    env.answers.push(() => {
      env.settings.patch({ agency: 'off' })
      return 'Yes, do it'
    })
    expect(await act.run(GOAL)).toMatchObject({ allowed: false, done: false, code: 'agency_off' })
    nothingHappened(env)
  })

  it('a denylisted target label is blocked: no confirmation, no actuator call, a "leave it to you" bubble', async () => {
    const { env, act } = setup({}, [click(500, 400, 'Click the Pay now button')])
    const r = await act.run(GOAL)
    expect(r).toMatchObject({ allowed: false, done: false, code: 'blocked' })
    expect(env.asked).toEqual([])
    nothingHappened(env)
    expect(env.shown.flat().some((a) => a.kind === 'bubble' && /leave this one to you/i.test(a.text))).toBe(true)
    expect(lastAudit(env)).toMatchObject({ decision: 'blocked' })
  })

  it('typing a password-like or denylisted word is blocked', async () => {
    const { env, act } = setup({}, [action({ tool: 'type', text: 'my password is hunter2', intent: 'Type into the box' })])
    expect(await act.run(GOAL)).toMatchObject({ allowed: false, code: 'blocked' })
    nothingHappened(env)
  })

  it('the same action id again: the model is told (feedback), the actuator ran once, and it can recover with another step', async () => {
    const { env, act, requests } = setup({}, [click(500, 400), click(500, 400), click(700, 300, 'Click the Next link'), finished()])
    const r = await act.run(GOAL)
    expect(r).toMatchObject({ done: true, code: 'done', steps: 2 })
    expect(env.calls).toEqual(['click 500,400', 'click 700,300'])
    expect(requests[2].feedback).toMatch(/already did .*click the start button.*DIFFERENT next step or finish/i)
    expect(requests[2].feedback).toMatch(/the screen changed after your last step/)
    expect(requests[3].feedback).toBeUndefined()
    expect(env.auditLines().some((l) => l.code === 'repeat')).toBe(true)
  })

  it('more than 2 recoveries per task: gave_up (same step), the actuator still ran once', async () => {
    const { env, act } = setup({}, [click(500, 400), click(500, 400), click(500, 400), click(500, 400), finished()])
    const r = await act.run(GOAL)
    expect(r).toMatchObject({ allowed: true, done: false, code: 'gave_up', steps: 1 })
    expect(r.reason).toMatch(/same step/i)
    expect(env.calls).toEqual(['click 500,400'])
  })

  it('never clicks the same element a third time: two near-identical points count as one element', async () => {
    const { env, act, requests } = setup({}, [click(500, 400), click(510, 405), click(505, 402), finished()])
    const r = await act.run(GOAL)
    expect(env.calls).toEqual(['click 500,400', 'click 510,405'])
    expect(r.steps).toBe(2)
    expect(requests.at(-1)?.history.join(' ')).toMatch(/already clicked twice/)
  })

  it('a failed action is never retried', async () => {
    const { env, act, requests } = setup({}, [click(500, 400), click(600, 600), finished()])
    env.actResults.set('click', { ok: false, reason: 'failed' })
    const r = await act.run(GOAL)
    expect(r).toMatchObject({ done: false, code: 'failed' })
    expect(env.calls).toEqual(['click 500,400'])
    expect(requests).toHaveLength(1)
  })

  it('a click that changes nothing: a short wait and a second look, ONE re-plan with feedback, then the task stops', async () => {
    const { env, act, requests } = setup({}, [click(100, 100), click(200, 200), click(300, 300), finished()])
    env.shots.push(...Array.from({ length: 12 }, () => shot('SAME', 9e15)))
    const r = await act.run(GOAL)
    expect(r).toMatchObject({ done: false, code: 'gave_up', steps: 2 })
    expect(r.reason).toMatch(/nothing on the screen changed/i)
    expect(env.calls).toEqual(['click 100,100', 'click 200,200'])
    expect(requests[1].feedback).toMatch(/no visible effect.*DIFFERENT next step or finish/i)
    expect(env.grabs.filter((g) => g === 'verify').length).toBeGreaterThanOrEqual(4)
  })

  it('a slow screen: the second look after a short wait sees the change, so the task goes on', async () => {
    const { env, act } = setup({}, [click(100, 100), finished()])
    env.shots.push(shot('SAME', 9e15), shot('SAME', 9e15), shot('LATER', env.clock.t + 5000))
    const r = await act.run(GOAL)
    expect(r).toMatchObject({ done: true, steps: 1 })
  })

  it('typed text that does not show on screen is retried ONCE by paste, and reported', async () => {
    const pasted: string[] = []
    const { env, act } = setup({ agency: 'ask_per_task' }, [click(500, 400), action({ tool: 'type', text: 'engineer', intent: 'Type the search' }), finished()])
    ;(env.deps.actuator as { pasteText?: (t: string) => Promise<{ ok: boolean }> }).pasteText = async (t) => (pasted.push(t), { ok: true })
    // click: changed; type: unchanged after typing, changed after the paste
    env.shots.push(shot('A', 9e15), shot('B', 9e15), shot('B', 9e15), shot('C', 9e15))
    const r = await act.run(GOAL)
    expect(env.calls).toContain('type engineer')
    expect(pasted).toEqual(['engineer'])
    expect(r.steps).toBe(2)
    expect(env.auditLines().some((l) => l.label === 'type: paste fallback' && l.ok === true)).toBe(true)
    expect(JSON.stringify(env.auditLines())).not.toContain('engineer')
  })

  it('keys or scroll that change nothing get one re-plan, then the task stops', async () => {
    const { env, act } = setup({}, [
      action({ tool: 'scroll', point: { x: 500, y: 500 }, dy: 5, intent: 'Scroll down' }),
      action({ tool: 'keys', keys: 'tab', intent: 'Press tab' }),
      action({ tool: 'keys', keys: 'space', intent: 'Press space' }),
      finished(),
    ])
    env.shots.push(...Array.from({ length: 12 }, () => shot('SAME', 9e15)))
    const r = await act.run(GOAL)
    expect(r).toMatchObject({ done: false, code: 'gave_up', steps: 2 })
    expect(env.calls).toEqual(['scroll 500,500,5', 'keys tab'])
  })

  it('stops at 12 steps and never claims success', async () => {
    const queue = Array.from({ length: 16 }, (_, i) => click(40 + i * 55, 100))
    const { env, act, requests } = setup({}, queue)
    const r = await act.run(GOAL)
    expect(r).toMatchObject({ done: false, code: 'gave_up', steps: 12 })
    expect(r.reason).toMatch(/12 steps/)
    expect(env.calls).toHaveLength(12)
    expect(requests.length).toBeLessThanOrEqual(13)
    expect(env.learned).toEqual([])
  })

  it('the total time cap ends the task', async () => {
    const { env, act } = setup({}, [click(500, 400), click(600, 600), finished()], { totalMs: 3000, onPropose: () => void (env.clock.t += 4000) })
    const r = await act.run(GOAL)
    expect(r).toMatchObject({ done: false, code: 'gave_up', steps: 1 })
    expect(r.reason).toMatch(/longer than 3 seconds/)
    expect(env.calls).toEqual(['click 500,400'])
  })

  it('ask_per_task: ONE plan confirmation covers every click and plain typing; only a risky step (Return) asks again', async () => {
    const { env, act } = setup({ agency: 'ask_per_task' }, [click(500, 400), click(520, 420, 'Click the search box'), action({ tool: 'type', text: 'opening times', intent: 'Type the search' }), finished()])
    const r = await act.run(GOAL)
    expect(r).toMatchObject({ done: true, code: 'done', steps: 3 })
    expect(env.asked).toHaveLength(1)
    expect(env.asked[0].question).toMatch(/^I'll try to: /)
    expect(env.asked[0].options).toEqual(['Yes, go ahead', 'No, I will'])
    expect(env.calls).toEqual(['click 500,400', 'click 520,420', 'type opening times'])
    // typed text never reaches the audit log
    expect(JSON.stringify(env.auditLines())).not.toContain('opening times')
  })

  it('ask_per_task: declining the plan ends it before any screenshot is acted on', async () => {
    const { env, act, requests } = setup({ agency: 'ask_per_task' }, [click(500, 400)])
    env.answers.push('no')
    expect(await act.run(GOAL)).toMatchObject({ code: 'declined', done: false })
    nothingHappened(env)
    expect(requests).toEqual([])
  })

  it("a model 'require_confirmation' forces a confirmation even when the plan was approved", async () => {
    const risky = click(500, 400, 'Click the link', { safety: { decision: 'require_confirmation', explanation: 'This opens another site' } })
    const { env, act } = setup({ agency: 'ask_per_task' }, [risky, finished()])
    await act.run(GOAL)
    expect(env.asked).toHaveLength(2)
    expect(env.asked[1].question).toMatch(/This opens another site/)
    expect(env.calls).toEqual(['click 500,400'])
  })

  it("a model 'blocked' halts the task", async () => {
    const { env, act } = setup({}, [{ kind: 'blocked', reason: 'Looks like a payment page.', ms: 1 }, click(500, 400)])
    const r = await act.run(GOAL)
    expect(r).toMatchObject({ allowed: false, done: false, code: 'blocked' })
    expect(r.reason).toMatch(/payment page/)
    nothingHappened(env)
    expect(env.asked).toEqual([])
  })

  it('no Accessibility: it only shows the ring and says what to click', async () => {
    const { env, act } = setup({ accessibility: false }, [click(500, 400), finished()])
    const r = await act.run(GOAL)
    expect(r).toMatchObject({ allowed: true, done: false, code: 'accessibility' })
    expect(r.reason).toMatch(/Accessibility/)
    expect(env.shown.flat().some((a) => a.kind === 'ring')).toBe(true)
    nothingHappened(env)
    expect(env.asked).toEqual([])
  })

  it('dry run: the action is logged, the task reports done as a dry run and is not counted', async () => {
    const { env, act } = setup({ dryRun: true }, [click(500, 400), finished()])
    const r = await act.run(GOAL)
    expect(r).toMatchObject({ done: true, code: 'done', dryRun: true, steps: 1 })
    expect(r.reason).toMatch(/dry run/i)
    expect(env.calls).toEqual(['click 500,400'])
    expect(env.learned).toEqual([])
    expect(env.auditLines()[0]).toMatchObject({ dryRun: true })
  })

  it('the model says finished but the Verifier is not sure: gave_up, never done', async () => {
    const { env, act } = setup({}, [click(500, 400), finished('I think that is it')])
    env.verdict.v = { completed: false, confidence: 0.4, evidence: 'not visible', uncertain: true }
    const r = await act.run(GOAL)
    expect(r).toMatchObject({ done: false, code: 'gave_up', verified: false, steps: 1 })
    expect(r.reason).toMatch(/do not say it is done/i)
    expect(env.learned).toEqual([])
  })

  it('finished with zero steps is not a success', async () => {
    const { env, act } = setup({}, [finished('I cannot find that')])
    const r = await act.run(GOAL)
    expect(r).toMatchObject({ done: false, code: 'gave_up', steps: 0 })
    expect(env.grabs).not.toContain('verify')
    nothingHappened(env)
  })

  it('a function the app does not do (drag) stops the task', async () => {
    const { env, act } = setup({}, [{ kind: 'unsupported', name: 'drag_and_drop', ms: 1 }])
    expect(await act.run(GOAL)).toMatchObject({ done: false, code: 'gave_up' })
    nothingHappened(env)
  })

  it('a model error gives a plain failure and changes nothing', async () => {
    const env = makeEnv()
    const sit = new Situation(env.ctx)
    const act = createActForMe(env.deps, sit, async () => undefined, {
      gemini: () => {
        throw new Error('unused')
      },
      loopEnabled: () => true,
      propose: async () => {
        throw new Error('503 secret-internal-detail')
      },
    })
    const r = await act.run(GOAL)
    expect(r).toMatchObject({ done: false, code: 'failed' })
    expect(r.reason).not.toContain('secret-internal-detail')
    nothingHappened(env)
  })

  it('a second task while one runs is busy; the first finishes normally', async () => {
    const { env, act } = setup({}, [click(500, 400), finished()])
    let release: () => void = () => undefined
    env.deps.confirm = { ask: (_q, options) => new Promise((resolve) => void (release = () => resolve(options[0]))) }
    const first = act.run(GOAL)
    await new Promise((r) => setTimeout(r, 0))
    expect(act.isRunning()).toBe(true)
    expect(await act.run(GOAL)).toMatchObject({ allowed: false, code: 'busy' })
    release()
    expect(await first).toMatchObject({ done: true })
    expect(act.isRunning()).toBe(false)
  })

  it('the tray chip goes running -> done and ends in the agents list', async () => {
    const { env, act } = setup({}, [click(500, 400), finished()])
    const seen: AgentChip['status'][] = []
    env.bus.on('agent:update', (e) => void seen.push(e.chip.status))
    await act.run(GOAL)
    expect(seen[0]).toBe('running')
    expect(seen.at(-1)).toBe('done')
    const chip = env.state.get().agents.find((a) => a.title === 'Doing this for you')
    expect(chip?.status).toBe('done')
  })

  it('the chip goes to error when the task could not finish', async () => {
    const { env, act } = setup({}, [click(500, 400), click(500, 400), click(500, 400), click(500, 400)])
    await act.run(GOAL)
    expect(env.state.get().agents.find((a) => a.title === 'Doing this for you')?.status).toBe('error')
  })

  it('a wait step sleeps and counts as a step but needs no confirmation', async () => {
    const { env, act } = setup({}, [action({ tool: 'wait', seconds: 2, intent: 'Wait for the page' }), click(500, 400), finished()])
    const r = await act.run(GOAL)
    expect(r).toMatchObject({ done: true, steps: 2 })
    expect(env.asked).toHaveLength(1)
    expect(env.calls).toEqual(['click 500,400'])
  })

  it('scroll, keys and double-click reach the matching actuator calls (after confirmation)', async () => {
    const { env, act } = setup({}, [
      action({ tool: 'scroll', point: { x: 500, y: 500 }, dy: 5, intent: 'Scroll down' }),
      action({ tool: 'keys', keys: 'tab', intent: 'Press tab' }),
      action({ tool: 'double_click', point: { x: 300, y: 300 }, intent: 'Open the folder' }),
      finished(),
    ])
    await act.run(GOAL)
    expect(env.calls).toEqual(['scroll 500,500,5', 'keys tab', 'doubleClick 300,300'])
    expect(env.asked).toHaveLength(3)
  })

  it('an unlisted key combination is refused by the policy', async () => {
    const { env, act } = setup({}, [action({ tool: 'keys', keys: 'cmd+shift+4', intent: 'Take a screenshot' })])
    expect(await act.run(GOAL)).toMatchObject({ allowed: false, code: 'blocked' })
    nothingHappened(env)
  })
})

describe('ghostPath', () => {
  it('starts at the pointer when known, else offset from the target, and ends on the target', () => {
    expect(ghostPath({ x: 10, y: 10 }, { x: 500, y: 500 })[0]).toEqual({ x: 10, y: 10 })
    const p = ghostPath(null, { x: 500, y: 500 })
    expect(p).toHaveLength(3)
    expect(p[2]).toEqual({ x: 500, y: 500 })
    expect(p[0]).not.toEqual(p[2])
  })
})
