import { mkdtempSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { createActForMe } from '../../src/main/agency/act-for-me'
import { Situation } from '../../src/main/agency/common'
import type { Proposal } from '../../src/main/agency/computer-use'
import { evaluateAction, evaluateGoal, isConsentWord, stripNegatedClauses, type PolicyContext, type ProposedAction } from '../../src/main/agency/policy'
import { checkScope, isBrowser, parseLsappinfoName, scopeFromGoal, type ScopeState } from '../../src/main/agency/scope'
import { SettingsStore } from '../../src/main/settings'
import { makeEnv } from './helpers'

const ctx = (over: Partial<PolicyContext> = {}): PolicyContext => ({ agency: 'ask_per_task', safetyCriticalStep: false, scamContext: false, planApproved: true, stageOrigin: 'http://127.0.0.1:5180', fileRoots: [], homeDir: '/Users/lily', ...over })

describe('goal scan is negation-aware', () => {
  const REAL_GOAL =
    'On the Google DeepMind careers page already open in Safari, click View open roles, then open one software engineering or research role to read its description. Stay on the careers site, leave any cookie banner alone, and stop once a role description is on screen.'
  it.each([
    ['open View open roles, do not sign in or submit anything', true],
    ["open View open roles, don't sign in or submit anything", true],
    ['read the page and never click Agree or Accept all cookies', true],
    ['browse the site without paying or signing in', true],
    ['do not click Agree, Accept all, do not sign in or submit anything', true],
    ['scroll the list, avoid the cookie banner', true],
    [REAL_GOAL, true],
    ['sign in to my bank', false],
    ['pay the bill', false],
    ['log in and check the balance', false],
    ['do not sign in, then pay the bill', false],
    ['open the page without signing in; then submit the form', false],
    ['never mind, buy it', false],
    ['click Agree on the cookie banner', false],
    ['accept all cookies', true], // the person explicitly asked for it
    ['accept all cookies and pay the bill', false],
    ['click Accept on the terms and conditions', false],
    ['I agree to the terms, open the page', false],
  ])('%s -> allowed=%s', (goal, allowed) => {
    expect(evaluateGoal(goal, ctx()).allowed).toBe(allowed)
  })

  it('removes only the negated clause', () => {
    expect(stripNegatedClauses('open roles, do not sign in or submit anything')).toBe('open roles,')
    expect(stripNegatedClauses('open the page without signing in, then pay the bill')).toBe('open the page , then pay the bill')
  })

  it('the label, target-text and typed-text scans never use negation', () => {
    for (const a of [
      { kind: 'click', label: 'Do not sign in' },
      { kind: 'click', label: 'Click Pay without delay' },
      { kind: 'type', text: 'never mind my password' },
      { kind: 'click', label: 'Click the button', targetText: 'avoid: Submit' },
    ] as ProposedAction[]) {
      expect(evaluateAction(a, ctx()).allowed).toBe(false)
    }
  })
})

describe('consent and cookie choices stay with the person', () => {
  it.each(['Click Agree', 'Click the "I agree" button', 'Click Allow all', 'Click Accept all cookies', 'Manage cookies', 'Give consent', 'Click Cookie settings'])('blocks the label "%s" and says so', (label) => {
    const d = evaluateAction({ kind: 'click', label }, ctx())
    expect(d.allowed).toBe(false)
    if (!d.allowed) expect(d.reason).toMatch(/consent choice|leave it to you/i)
  })
  it('the explanation names consent choices for agree / consent / cookie words', () => {
    for (const label of ['Click Agree', 'Click the cookie banner OK', 'Give consent']) {
      const d = evaluateAction({ kind: 'click', label }, ctx())
      expect(!d.allowed && d.reason).toMatch(/I leave consent choices to you/)
      expect(!d.allowed && d.flags).toContain('consent')
    }
    expect(isConsentWord('agree')).toBe(true)
    expect(isConsentWord('pay')).toBe(false)
  })
  it('ordinary labels are untouched', () => {
    expect(evaluateAction({ kind: 'click', label: 'Click View open roles' }, ctx()).allowed).toBe(true)
  })
  it('a goal that is itself a consent choice is refused with the consent wording', () => {
    const d = evaluateGoal('click Agree on the banner', ctx())
    expect(!d.allowed && d.reason).toMatch(/consent choice/)
  })
})

describe('settings: ask_per_task is the default and unchosen profiles migrate', () => {
  const profile = (json: Record<string, unknown>): SettingsStore => {
    const dir = mkdtempSync(path.join(os.tmpdir(), 'agency-settings-'))
    writeFileSync(path.join(dir, 'settings.json'), JSON.stringify(json))
    return new SettingsStore(dir)
  }
  it.each([
    [{ onboardingDone: true, agency: 'off' }, 'ask_per_task'],
    [{ onboardingDone: true, agency: 'ask_each' }, 'ask_per_task'],
    [{ onboardingDone: true, agency: 'off', agencyChosen: false }, 'ask_per_task'],
    [{ onboardingDone: true }, 'ask_per_task'],
    [{ agency: 'off', agencyChosen: true }, 'off'],
    [{ agency: 'ask_each', agencyChosen: true }, 'ask_each'],
    [{ agency: 'ask_per_task', agencyChosen: true }, 'ask_per_task'],
  ])('saved %j loads as %s', (saved, expected) => {
    const s = profile(saved).get()
    expect(s.agency).toBe(expected)
    expect(s.doItForMeAllowed).toBe(expected !== 'off')
  })
  it('a fresh in-memory store defaults to ask_per_task', () => {
    expect(new SettingsStore(null).get().agency).toBe('ask_per_task')
  })
})

describe('scope: which app the task is about', () => {
  it.each([
    ['In the Calculator app press 7 times 6 equals', { kind: 'app', app: 'Calculator' }],
    ['On the Google DeepMind careers page already open in Safari, click View open roles', { kind: 'browser' }],
    ['go to www.example.com and read it', { kind: 'browser' }],
    ['make the text bigger here', { kind: 'first' }],
  ])('%s', (goal, scope) => {
    expect(scopeFromGoal(goal)).toEqual(scope)
  })

  it('reads the app name from lsappinfo output', () => {
    expect(parseLsappinfoName('"LSDisplayName"="Safari"\n')).toBe('Safari')
    expect(parseLsappinfoName('')).toBeNull()
  })

  const browser = (): ScopeState => ({ scope: { kind: 'browser' } })
  const calculator = (): ScopeState => ({ scope: { kind: 'app', app: 'Calculator' } })
  it.each([
    [browser(), 'Safari', true],
    [browser(), 'Google Chrome', true],
    [browser(), 'Arc', true],
    [browser(), 'Alongside', true],
    [browser(), 'Electron', true],
    [browser(), 'Calculator', false],
    [browser(), 'Claude', false],
    [browser(), 'Terminal', false],
    [browser(), 'iTerm2', false],
    [calculator(), 'Calculator', true],
    [calculator(), 'Safari', false],
    [calculator(), 'Alongside', true],
    [calculator(), 'Claude', false],
    [{ scope: { kind: 'first' } } as ScopeState, 'Notes', true],
    [{ scope: { kind: 'first' } } as ScopeState, 'Ghostty', false],
    [{ scope: { kind: 'first' } } as ScopeState, null, true],
  ])('%j with %s in front -> allowed=%s', (state, front, ok) => {
    expect(checkScope(state, front).ok).toBe(ok)
  })

  it("a 'first' scope locks to the first app it sees", () => {
    const state: ScopeState = { scope: { kind: 'first' } }
    expect(checkScope(state, 'Notes').ok).toBe(true)
    expect(checkScope(state, 'Safari').ok).toBe(false)
    expect(checkScope(state, 'Alongside').ok).toBe(true)
    expect(checkScope(state, 'Notes').ok).toBe(true)
  })

  it('Claude-named apps and browsers are told apart', () => {
    expect(isBrowser('Safari')).toBe(true)
    expect(isBrowser('Calculator')).toBe(false)
    expect(checkScope({ scope: { kind: 'browser' } }, 'Claude Code').ok).toBe(false)
  })
})

describe('scope in the act_for_me loop (fake front-app provider)', () => {
  const click = (x: number, y: number, intent = 'Click the key'): Proposal => ({ kind: 'action', ms: 1, step: { id: `click:${x}:${y}`, tool: 'click', point: { x, y }, intent } })
  const typed = (text: string): Proposal => ({ kind: 'action', ms: 1, step: { id: `type:${text}`, tool: 'type', text, intent: 'Type it' } })
  const finished: Proposal = { kind: 'finished', text: 'done', ms: 1 }

  function rig(goal: string, fronts: Array<string | null>, queue: Proposal[], agency: 'ask_each' | 'ask_per_task' = 'ask_each') {
    const env = makeEnv({ agency })
    const sit = new Situation(env.ctx)
    const proposals = [...queue]
    const reads: string[] = []
    let i = 0
    const act = createActForMe(env.deps, sit, async () => undefined, {
      gemini: () => {
        throw new Error('no model')
      },
      loopEnabled: () => true,
      frontApp: async () => {
        const v = fronts[Math.min(i++, fronts.length - 1)]
        reads.push(String(v))
        return v
      },
      propose: async () => proposals.shift() ?? finished,
    })
    return { env, act, reads, goal }
  }

  it('a web goal in Safari runs, and the audit line names the front app', async () => {
    const { env, act, goal } = rig('open the careers page in Safari', ['Safari'], [click(500, 400), finished])
    const r = await act.run(goal)
    expect(r.code).toBe('done')
    expect(env.calls).toEqual(['click 500,400'])
    expect(env.auditLines().some((l) => l.app === 'Safari')).toBe(true)
  })

  it('stops with a plain message when another app comes to the front: nothing is clicked', async () => {
    const { env, act } = rig('In the Calculator app press 7', ['Calculator', 'Safari'], [click(500, 400), click(520, 400, 'Click six'), finished])
    const r = await act.run('In the Calculator app press 7')
    expect(r).toMatchObject({ allowed: false, done: false, code: 'blocked' })
    expect(r.reason).toMatch(/Safari came to the front, but this task is only about Calculator/)
    expect(env.calls).toEqual([])
    expect(env.auditLines().at(-1)).toMatchObject({ decision: 'blocked', label: 'scope', app: 'Safari' })
  })

  it.each(['Claude', 'Terminal', 'iTerm2'])('never acts when %s is in front', async (app) => {
    const { env, act } = rig('open the careers page in Safari', [app], [click(500, 400), finished])
    const r = await act.run('open the careers page in Safari')
    expect(r).toMatchObject({ done: false, code: 'blocked' })
    expect(r.reason).toMatch(/never act in it/)
    expect(env.calls).toEqual([])
  })

  it("Alongside's own window in front (the confirmation prompt) is allowed, and typing first brings the target app back", async () => {
    // reads: task start (Safari, recorded before any prompt), step top (Safari), after confirm (Alongside), refocus check (Alongside), re-check (Safari)
    const { env, act } = rig('type a search in Safari', ['Safari', 'Safari', 'Alongside', 'Alongside', 'Safari'], [typed('engineer'), finished])
    const r = await act.run('type a search in Safari')
    expect(r.code).toBe('done')
    expect(env.calls).toEqual(['openApp Safari', 'type engineer'])
  })

  it('the app in front at the START is recorded before the prompt takes the focus, so typing can bring it back', async () => {
    // start: Safari; then only Alongside (the prompt) is ever in front until the app is re-opened
    const { env, act } = rig('type a search in Safari', ['Safari', 'Alongside', 'Alongside', 'Alongside', 'Safari'], [typed('engineer'), finished], 'ask_per_task')
    const r = await act.run('type a search in Safari')
    expect(r.code).toBe('done')
    expect(env.calls).toEqual(['openApp Safari', 'type engineer'])
  })

  it('a named native app is brought back before typing even when it was never seen in front', async () => {
    const { env, act } = rig('In the Calculator app type 7', ['Alongside'], [typed('7'), finished])
    await act.run('In the Calculator app type 7')
    expect(env.calls[0]).toBe('openApp Calculator')
  })

  it('an unreadable front app never blocks', async () => {
    const { env, act } = rig('open the careers page in Safari', [null], [click(500, 400), finished])
    expect((await act.run('open the careers page in Safari')).code).toBe('done')
    expect(env.calls).toEqual(['click 500,400'])
  })
})
