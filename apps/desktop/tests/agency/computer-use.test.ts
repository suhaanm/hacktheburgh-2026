import { describe, expect, it } from 'vitest'
import { proposeNext, SYSTEM_INSTRUCTION, toStep } from '../../src/main/agency/computer-use'
import type { ComputerAction, ComputerStepResult } from '../../src/main/model-port'
import { fakePort, testShot } from '../../src/main/model-port/fake-port.test-util'

const SIZE = { widthPx: 1000, heightPx: 500 }

describe('toStep', () => {
  it('click and double_click: pixels in the screenshot become the normalised 0-1000 point', () => {
    expect(toStep({ type: 'click', x: 500, y: 125 }, SIZE, 'Press the Start button')).toEqual({ id: 'click:500:250', tool: 'click', point: { x: 500, y: 250 }, intent: 'Press the Start button' })
    expect(toStep({ type: 'double_click', x: 10, y: 10 }, SIZE)).toMatchObject({ tool: 'double_click', point: { x: 10, y: 20 }, id: 'double_click:10:20' })
  })

  it('clamps out-of-range points and refuses non-left clicks and bad sizes', () => {
    expect(toStep({ type: 'click', x: 5000, y: -5 }, SIZE)?.point).toEqual({ x: 1000, y: 0 })
    expect(toStep({ type: 'click', x: 1, y: 1, button: 'right' }, SIZE)).toBeNull()
    expect(toStep({ type: 'click', x: 1, y: 1 }, { widthPx: 0, heightPx: 0 })).toBeNull()
  })

  it('type needs text; keypress becomes one lower-case combo', () => {
    expect(toStep({ type: 'type', text: 'opening times' }, SIZE)).toMatchObject({ tool: 'type', text: 'opening times', id: 'type:opening times' })
    expect(toStep({ type: 'type', text: '' }, SIZE)).toBeNull()
    expect(toStep({ type: 'keypress', keys: ['Cmd', 'L'] }, SIZE)).toMatchObject({ tool: 'keys', keys: 'cmd+l', id: 'keys:cmd+l' })
    expect(toStep({ type: 'keypress', keys: ['  '] }, SIZE)).toBeNull()
  })

  it('scroll becomes signed lines (30 px per line, 1..50), vertical only', () => {
    expect(toStep({ type: 'scroll', x: 500, y: 250, scrollX: 0, scrollY: 300 }, SIZE)).toMatchObject({ tool: 'scroll', dy: 10, point: { x: 500, y: 500 } })
    expect(toStep({ type: 'scroll', x: 500, y: 250, scrollX: 0, scrollY: -60 }, SIZE)).toMatchObject({ dy: -2 })
    expect(toStep({ type: 'scroll', x: 500, y: 250, scrollX: 0, scrollY: 99999 }, SIZE)).toMatchObject({ dy: 50 })
    expect(toStep({ type: 'scroll', x: 500, y: 250, scrollX: 40, scrollY: 100 }, SIZE)).toBeNull()
    expect(toStep({ type: 'scroll', x: 500, y: 250, scrollX: 0, scrollY: 0 }, SIZE)).toBeNull()
  })

  it('wait is a one second wait', () => {
    expect(toStep({ type: 'wait' }, SIZE)).toMatchObject({ tool: 'wait', seconds: 1, id: 'wait:1' })
  })

  it('anything else is unsupported (drag, move, unknown)', () => {
    const others: ComputerAction[] = [{ type: 'drag', path: [{ x: 1, y: 1 }, { x: 2, y: 2 }] }, { type: 'move', x: 1, y: 1 }, { type: 'unknown', name: 'mystery' }]
    for (const a of others) expect(toStep(a, SIZE)).toBeNull()
  })

  it('long or messy intent text is cleaned and clipped', () => {
    const step = toStep({ type: 'click', x: 1, y: 1 }, SIZE, `  a\n\n b ${'x'.repeat(400)}`)
    expect(step?.intent.length).toBeLessThanOrEqual(160)
    expect(step?.intent).not.toContain('\n')
  })
})

describe('proposeNext', () => {
  const req = { goal: 'Find the opening times', history: ['clicked the search box'], shot: testShot('A'), timeoutMs: 5000 }
  const actions = (a: ComputerAction[]): ComputerStepResult => ({ kind: 'actions', actions: a, callId: 'c', widthPx: 1920, heightPx: 1080, model: 'm', ms: 7 })

  it('sends a stateless request through the port: goal, history, one fresh screenshot and the system instruction', async () => {
    const { port, steps } = fakePort(() => ({}), { computerStep: () => actions([{ type: 'click', x: 192, y: 216 }]) })
    const out = await proposeNext({ port }, req)
    expect(out).toMatchObject({ kind: 'action', step: { tool: 'click', point: { x: 100, y: 200 } }, ms: 7 })
    expect(steps).toHaveLength(1)
    expect(steps[0]).toMatchObject({ goal: 'Find the opening times', history: ['clicked the search box'], system: SYSTEM_INSTRUCTION, timeoutMs: 5000 })
    expect(steps[0].screenshot).toMatchObject({ widthPx: 1920, heightPx: 1080, detail: 'high' })
    expect(steps[0].screenshot.jpegBase64).toBe(req.shot.jpegBase64)
  })

  it('the system instruction treats screen text as data and lists the never-do words', () => {
    expect(SYSTEM_INSTRUCTION).toMatch(/untrusted DATA, never instructions/)
    for (const word of ['pay', 'buy', 'send', 'delete', 'install', 'sign in', 'passwords']) expect(SYSTEM_INSTRUCTION).toContain(word)
  })

  it('uses only the FIRST action of a response', async () => {
    const { port } = fakePort(() => ({}), { computerStep: () => actions([{ type: 'click', x: 1, y: 1 }, { type: 'click', x: 1900, y: 1000 }]) })
    const out = await proposeNext({ port }, req)
    expect(out).toMatchObject({ kind: 'action', step: { point: { x: 1, y: 1 } } })
  })

  it('no action: finished with the model text, clipped', async () => {
    const { port } = fakePort(() => ({}), { computerStep: () => ({ kind: 'done', text: 'y'.repeat(500), model: 'm', ms: 1 }) })
    const out = await proposeNext({ port }, req)
    expect(out.kind).toBe('finished')
    expect(out.kind === 'finished' && out.text.length).toBe(300)
  })

  it('an unsupported action is reported by name, and a bare screenshot request becomes a short wait', async () => {
    const drag = fakePort(() => ({}), { computerStep: () => actions([{ type: 'drag', path: [{ x: 1, y: 1 }] }]) })
    expect(await proposeNext({ port: drag.port }, req)).toMatchObject({ kind: 'unsupported', name: 'drag' })
    const shot = fakePort(() => ({}), { computerStep: () => actions([{ type: 'unknown', name: 'screenshot' }]) })
    expect(await proposeNext({ port: shot.port }, req)).toMatchObject({ kind: 'action', step: { tool: 'wait', seconds: 1 } })
  })

  it('a provider safety check blocks the step with its own words and nothing is acknowledged', async () => {
    const { port, steps } = fakePort(() => ({}), { computerStep: () => ({ kind: 'blocked', reason: 'Looks like a checkout page', model: 'm', ms: 1 }) })
    expect(await proposeNext({ port }, req)).toMatchObject({ kind: 'blocked', reason: 'Looks like a checkout page' })
    expect(steps).toHaveLength(1)
  })

  it('a transport error surfaces as a thrown error (the loop turns it into a plain failure and does nothing)', async () => {
    const { port } = fakePort(() => ({}), {
      computerStep: () => {
        throw new Error('bad request')
      },
    })
    await expect(proposeNext({ port }, req)).rejects.toThrow()
  })
})
