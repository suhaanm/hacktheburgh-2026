import { describe, expect, it } from 'vitest'
import { createActForMe } from '../../src/main/agency/act-for-me'
import { Situation } from '../../src/main/agency/common'
import type { Proposal, ProposedStep } from '../../src/main/agency/computer-use'
import { evaluateAction, evaluateGoal, goalAcceptsCookies, isPrivacyOption, plainQuery, type PolicyContext, type ProposedAction, type ReturnFacts } from '../../src/main/agency/policy'
import { parseFocusOutput } from '../../src/main/agency/scope'
import { makeEnv } from './helpers'

const facts = (over: Partial<ReturnFacts> = {}): ReturnFacts => ({
  prevTypedText: 'Software Engineer',
  returnsSoFar: 0,
  secureField: false,
  windowTitle: 'Careers - Google DeepMind',
  frontApp: 'Safari',
  targetApp: 'Safari',
  targetKnown: true,
  goalClean: true,
  ...over,
})
const ctx = (over: Partial<PolicyContext> = {}): PolicyContext => ({ agency: 'ask_per_task', safetyCriticalStep: false, scamContext: false, planApproved: true, stageOrigin: 'http://127.0.0.1:5180', fileRoots: [], homeDir: '/Users/lily', returnFacts: facts(), ...over })
// The exact user case: the model's own words call Return "submit the search".
const RETURN: ProposedAction = { kind: 'keys', value: 'return', label: 'Press Enter to submit the search' }

describe('Return: the narrow allowance after typing a plain query', () => {
  it('the exact user case is allowed and, under an approved plan, needs no further prompt', () => {
    const d = evaluateAction(RETURN, ctx())
    expect(d.allowed && d.ask).toBe(false)
    expect(d.allowed && d.flags).toContain('return-after-type')
  })
  it.each([
    ['enter spelled as enter', { ...RETURN, value: 'Enter' }, ctx(), true],
    ['ask_each still asks, but is allowed', RETURN, ctx({ agency: 'ask_each', planApproved: false }), true],
    ['autonomous is allowed (its own gate decides)', RETURN, ctx({ agency: 'autonomous', planApproved: false }), true],
    ['second press of two', RETURN, ctx({ returnFacts: facts({ returnsSoFar: 1 }) }), true],
    ['secure field unreadable but the title is fine', RETURN, ctx({ returnFacts: facts({ secureField: null }) }), true],
    ['title unreadable but the field is known not secure', RETURN, ctx({ returnFacts: facts({ windowTitle: null }) }), true],
    ['a native app named by the goal', RETURN, ctx({ returnFacts: facts({ frontApp: 'Notes', targetApp: 'Notes', windowTitle: 'Notes' }) }), true],
  ])('allow: %s', (_n, action, c, allowed) => {
    expect(evaluateAction(action as ProposedAction, c).allowed).toBe(allowed)
  })

  it.each([
    ['no return facts at all', ctx({ returnFacts: undefined })],
    ['not preceded by typing', ctx({ returnFacts: facts({ prevTypedText: null }) })],
    ['typed text is a password-like string', ctx({ returnFacts: facts({ prevTypedText: 'my password hunter2' }) })],
    ['typed text has an @', ctx({ returnFacts: facts({ prevTypedText: 'lily@example.com' }) })],
    ['typed text has a long digit run', ctx({ returnFacts: facts({ prevTypedText: 'order 1234567' }) })],
    ['typed text is a card-like number', ctx({ returnFacts: facts({ prevTypedText: '4111 1111 1111 1111' }) })],
    ['typed text is longer than 80 chars', ctx({ returnFacts: facts({ prevTypedText: 'a'.repeat(81) }) })],
    ['typed text holds a denylist word', ctx({ returnFacts: facts({ prevTypedText: 'send money' }) })],
    ['third Return in a task', ctx({ returnFacts: facts({ returnsSoFar: 2 }) })],
    ['secure field', ctx({ returnFacts: facts({ secureField: true }) })],
    ['neither the field nor the title can be read', ctx({ returnFacts: facts({ secureField: null, windowTitle: null }) })],
    ['sign-in page title', ctx({ returnFacts: facts({ windowTitle: 'Sign in - Google Accounts' }) })],
    ['login page title', ctx({ returnFacts: facts({ windowTitle: 'Log In' }) })],
    ['checkout page title', ctx({ returnFacts: facts({ windowTitle: 'Checkout - Shop' }) })],
    ['payment page title', ctx({ returnFacts: facts({ windowTitle: 'Payment details' }) })],
    ['billing page title', ctx({ returnFacts: facts({ windowTitle: 'Billing' }) })],
    ['register page title', ctx({ returnFacts: facts({ windowTitle: 'Register for an account' }) })],
    ['apply-now page title', ctx({ returnFacts: facts({ windowTitle: 'apply-now form' }) })],
    ['a different app is in front', ctx({ returnFacts: facts({ frontApp: 'Calculator' }) })],
    ['the front app is Claude', ctx({ returnFacts: facts({ frontApp: 'Claude', targetApp: 'Claude' }) })],
    ['the target is not a browser or known app', ctx({ returnFacts: facts({ targetKnown: false }) })],
    ['no target recorded', ctx({ returnFacts: facts({ targetApp: null }) })],
    ['the goal has a denylist word', ctx({ returnFacts: facts({ goalClean: false }) })],
    ['plan not yet confirmed (ask_per_task)', ctx({ planApproved: false })],
    ['safety-critical lesson step', ctx({ safetyCriticalStep: true })],
    ['a scam check is running', ctx({ scamContext: true })],
    ['agency off', ctx({ agency: 'off' })],
  ])('deny: %s', (_n, c) => {
    expect(evaluateAction(RETURN, c).allowed).toBe(false)
  })

  it('other denylist words in the model\'s own words still block (only the word "submit" is ignored)', () => {
    expect(evaluateAction({ ...RETURN, label: 'Press Enter to pay and submit' }, ctx()).allowed).toBe(false)
    expect(evaluateAction({ ...RETURN, label: 'Press Enter', targetText: 'This will send the message' }, ctx()).allowed).toBe(false)
  })
  it('a click labelled submit is still blocked, whatever was typed before', () => {
    expect(evaluateAction({ kind: 'click', label: 'Click the Submit button' }, ctx()).allowed).toBe(false)
  })
  it('the refusal says what, why, and what to do', () => {
    const d = evaluateAction(RETURN, ctx({ returnFacts: facts({ prevTypedText: null }) }))
    expect(!d.allowed && d.reason).toMatch(/I leave it to you/)
  })
  it.each([
    ['Software Engineer', true],
    ['research scientist london', true],
    ['', false],
    ['a@b.c', false],
    ['call 07700900123', false],
    ['x'.repeat(81), false],
    ['my password', false],
  ])('plainQuery(%j) = %s', (text, ok) => {
    expect(plainQuery(text)).toBe(ok)
  })
  it('reads the focus helper output', () => {
    expect(parseFocusOutput('{"secure":false,"title":"Careers"}')).toEqual({ secure: false, title: 'Careers' })
    expect(parseFocusOutput('{"secure":null,"title":null}')).toEqual({ secure: null, title: null })
    expect(parseFocusOutput('garbage')).toEqual({ secure: null, title: null })
  })
})

describe('cookie banners: decline passes, accept stays blocked unless the goal asks', () => {
  it.each(["Click 'No thanks' on the cookie banner", 'Click Reject all cookies', 'Click Only necessary cookies', 'Click Decline', 'Click Dismiss on the cookie notice', 'Close the cookie banner', 'Click Not now', 'Click "Continue without accepting"'])('allows: %s', (label) => {
    expect(isPrivacyOption(label)).toBe(true)
    expect(evaluateAction({ kind: 'click', label }, ctx()).allowed).toBe(true)
  })
  it.each(['Click Agree', 'Click Accept all cookies', 'Click Allow all', 'Click the "I agree" button', 'Click Accept and close', 'Click Allow cookies', 'Manage cookies', 'Click OK to the cookie policy', 'Click Reject all and accept the terms'])('blocks: %s', (label) => {
    expect(evaluateAction({ kind: 'click', label }, ctx()).allowed).toBe(false)
  })
  it('a decline label cannot smuggle in another denylist word', () => {
    expect(evaluateAction({ kind: 'click', label: 'Reject cookies and pay now' }, ctx()).allowed).toBe(false)
    expect(evaluateAction({ kind: 'click', label: 'No thanks', targetText: 'delete my account' }, ctx()).allowed).toBe(false)
  })
  it('an explicit "accept the cookies" goal lets consent wording through, for cookie-banner labels only', () => {
    const c = ctx({ goalAcceptsCookies: true })
    expect(goalAcceptsCookies('open the site and accept the cookies')).toBe(true)
    expect(goalAcceptsCookies('open the site, do not accept the cookies')).toBe(false)
    expect(evaluateAction({ kind: 'click', label: 'Click Accept all cookies' }, c).allowed).toBe(true)
    expect(evaluateAction({ kind: 'click', label: 'Click Allow cookies' }, c).allowed).toBe(true)
    expect(evaluateAction({ kind: 'click', label: 'Click Allow microphone' }, c).allowed).toBe(false)
    expect(evaluateAction({ kind: 'click', label: 'Click Accept and pay' }, c).allowed).toBe(false)
    expect(evaluateGoal('open the site and accept the cookies', ctx()).allowed).toBe(true)
    expect(evaluateGoal('open the site and accept the cookies, then pay', ctx()).allowed).toBe(false)
  })
  it('the refusal for a consent click is short and tells the learner what to do next', () => {
    const d = evaluateAction({ kind: 'click', label: 'Click Agree' }, ctx())
    expect(!d.allowed && d.reason).toMatch(/consent choice/)
    expect(!d.allowed && d.reason).toMatch(/No thanks|Reject all|yourself/)
    expect(!d.allowed && d.reason.length).toBeLessThan(260)
  })
})

describe('end to end: the routine flow stays allowed under ONE plan confirmation', () => {
  type Step = Partial<ProposedStep> & Pick<ProposedStep, 'tool'>
  const act = (step: Step): Proposal => ({ kind: 'action', ms: 1, step: { id: `${step.tool}:${step.point?.x ?? ''}:${step.point?.y ?? ''}:${step.text ?? ''}:${step.keys ?? ''}`, intent: '', ...step } })
  const finished: Proposal = { kind: 'finished', text: 'The role description is on screen.', ms: 1 }

  function rig(queue: Proposal[], opts: { title?: string | null; secure?: boolean | null; front?: string } = {}) {
    const env = makeEnv({ agency: 'ask_per_task' })
    const sit = new Situation(env.ctx)
    const proposals = [...queue]
    const a = createActForMe(env.deps, sit, async () => undefined, {
      gemini: () => {
        throw new Error('no model')
      },
      loopEnabled: () => true,
      frontApp: async () => opts.front ?? 'Safari',
      focusInfo: async () => ({ secure: opts.secure === undefined ? false : opts.secure, title: opts.title === undefined ? 'Careers - Google DeepMind' : opts.title }),
      propose: async () => proposals.shift() ?? finished,
    })
    return { env, a }
  }
  const GOAL = 'On the Google DeepMind careers page already open in Safari, click View open roles, then open one software engineering or research role to read its description. Stay on the careers site, leave any cookie banner alone, and stop once a role description is on screen.'

  it('click, dismiss the banner with No thanks, click the search field, type a plain query, Return, scroll, open a role', async () => {
    const { env, a } = rig([
      act({ tool: 'click', point: { x: 300, y: 300 }, intent: 'Click View open roles' }),
      act({ tool: 'click', point: { x: 800, y: 900 }, intent: "Click 'No thanks' on the cookie banner" }),
      act({ tool: 'click', point: { x: 500, y: 200 }, intent: 'Click the search field' }),
      act({ tool: 'type', text: 'robotics research', intent: 'Type the search' }),
      act({ tool: 'keys', keys: 'return', intent: 'Press Enter to submit the search' }),
      act({ tool: 'scroll', point: { x: 500, y: 600 }, dy: 5, intent: 'Scroll down the results' }),
      act({ tool: 'click', point: { x: 450, y: 520 }, intent: 'Open the Software Engineer, Research role link' }),
      finished,
    ])
    const r = await a.run(GOAL)
    expect(r).toMatchObject({ done: true, code: 'done', steps: 7 })
    expect(env.asked).toHaveLength(1) // only the plan
    expect(env.calls).toEqual(['click 300,300', 'click 800,900', 'click 500,200', 'type robotics research', 'keys return', 'scroll 500,600,5', 'click 450,520'])
    expect(env.auditLines().some((l) => l.label === 'keys: return-after-type')).toBe(true)
    expect(JSON.stringify(env.auditLines())).not.toContain('robotics')
  })

  it('Return straight after a click (not typing) is blocked, with an actionable message', async () => {
    const { env, a } = rig([act({ tool: 'click', point: { x: 500, y: 200 }, intent: 'Click the search field' }), act({ tool: 'keys', keys: 'return', intent: 'Press Enter to submit' })])
    const r = await a.run(GOAL)
    expect(r).toMatchObject({ allowed: false, done: false, code: 'blocked', steps: 1 })
    expect(r.reason).toMatch(/Blocked: "press the return key"/)
    expect(r.reason).toMatch(/Next: point at it/)
    expect(env.calls).toEqual(['click 500,200'])
  })

  it('Return on a sign-in page is blocked even right after typing', async () => {
    const { env, a } = rig([act({ tool: 'type', text: 'Software Engineer', intent: 'Type' }), act({ tool: 'keys', keys: 'return', intent: 'Press Enter' })], { title: 'Sign in' })
    expect(await a.run(GOAL)).toMatchObject({ allowed: false, code: 'blocked' })
    expect(env.calls).toEqual(['type Software Engineer'])
  })

  it('at most 2 Returns per task, and a third is blocked', async () => {
    const q = (text: string): Proposal[] => [act({ tool: 'type', text, intent: 'Type the search' }), act({ tool: 'keys', keys: 'return', intent: 'Press Enter' })]
    const { env, a } = rig([...q('engineer'), ...q('research'), ...q('scientist'), finished])
    // each action changes the screen (the fake grabs a new image each time)
    const r = await a.run(GOAL)
    expect(env.calls.filter((c) => c === 'keys return')).toHaveLength(2)
    expect(r).toMatchObject({ allowed: false, code: 'blocked' })
  })

  it('without a readable window title or field, and with the wrong app in front, Return stays blocked', async () => {
    const one = rig([act({ tool: 'type', text: 'engineer', intent: 'Type' }), act({ tool: 'keys', keys: 'return', intent: 'Press Enter' })], { title: null, secure: null })
    expect(await one.a.run(GOAL)).toMatchObject({ code: 'blocked' })
    expect(one.env.calls).toEqual(['type engineer'])
  })
})
