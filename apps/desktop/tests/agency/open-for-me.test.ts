import { statSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { Situation } from '../../src/main/agency/common'
import { lastAuditLine } from '../../src/main/agency/audit'
import { createOpenForMe } from '../../src/main/agency/open-for-me'
import { ActionLimiter } from '../../src/main/agency/policy'
import { makeEnv, type Env } from './helpers'

function setup(opts: Parameters<typeof makeEnv>[0] = {}) {
  const env = makeEnv(opts)
  const sit = new Situation(env.ctx)
  const open = createOpenForMe(env.deps, sit, new ActionLimiter(1_000_000, 1500, 12), (k) => void env.learned.push(k))
  return { env, sit, open }
}
const noActuatorCalls = (env: Env) => expect(env.calls).toEqual([])

describe('open_for_me', () => {
  it('opens a website after a real-click confirmation, audits it and counts it', async () => {
    const { env, open } = setup()
    const r = await open({ kind: 'url', value: 'https://www.ageuk.org.uk/information-advice' })
    expect(r).toMatchObject({ allowed: true, done: true, code: 'done', label: 'www.ageuk.org.uk' })
    expect(r.reason).toMatch(/offer to show/i)
    expect(env.asked).toEqual([{ question: "I'll open www.ageuk.org.uk for you. OK?", options: ['Yes, open it', 'No, I will'] }])
    expect(env.calls).toEqual(['openUrl https://www.ageuk.org.uk/information-advice'])
    // the explanation is on screen BEFORE the confirmation, and cleared afterwards
    expect(env.shown[0][0]).toMatchObject({ kind: 'bubble' })
    const lines = env.auditLines()
    expect(lines).toHaveLength(1)
    expect(lines[0]).toMatchObject({ tool: 'open_for_me', decision: 'allowed', ok: true, code: 'done', host: 'www.ageuk.org.uk' })
    expect(JSON.stringify(lines)).not.toContain('information-advice') // paths and queries stay out of the log
    expect(statSync(path.join(env.dir, 'actions.log')).mode & 0o777).toBe(0o600)
    expect(env.learned).toEqual(['open:www.ageuk.org.uk'])
    expect(JSON.parse((await lastAuditLine(env.dir)) as string)).toMatchObject({ tool: 'open_for_me', ok: true })
  })

  it('agency off: refuses and never asks or acts', async () => {
    const { env, open } = setup({ agency: 'off' })
    const r = await open({ kind: 'url', value: 'https://www.ageuk.org.uk' })
    expect(r).toMatchObject({ allowed: false, done: false, code: 'agency_off' })
    expect(env.asked).toEqual([])
    noActuatorCalls(env)
    expect(env.auditLines()[0]).toMatchObject({ decision: 'refused', code: 'agency_off' })
  })

  it('ask_per_task still confirms a stand-alone open (one action is the plan)', async () => {
    const { env, open } = setup({ agency: 'ask_per_task' })
    await open({ kind: 'app', value: 'Safari' })
    expect(env.asked).toHaveLength(1)
    expect(env.calls).toEqual(['openApp Safari'])
  })

  it('declined (No, or no answer): nothing is opened', async () => {
    for (const answer of ['no', 'null'] as const) {
      const { env, open } = setup()
      env.answers.push(answer)
      const r = await open({ kind: 'url', value: 'https://www.ageuk.org.uk' })
      expect(r).toMatchObject({ allowed: true, done: false, code: 'declined' })
      noActuatorCalls(env)
      expect(env.auditLines()[0]).toMatchObject({ decision: 'declined', ok: false })
    }
  })

  it('Stop while the confirmation is open: stopped, nothing opened', async () => {
    const { env, open } = setup()
    env.answers.push(() => {
      env.bus.emit('session:ended', { reason: 'stop' })
      return null
    })
    expect(await open({ kind: 'url', value: 'https://www.ageuk.org.uk' })).toMatchObject({ code: 'stopped', done: false })
    noActuatorCalls(env)
  })

  it('agency switched off while the modal waits: nothing is opened', async () => {
    const { env, open } = setup()
    env.answers.push(() => {
      env.settings.patch({ agency: 'off' })
      return 'Yes, open it'
    })
    expect(await open({ kind: 'url', value: 'https://www.ageuk.org.uk' })).toMatchObject({ allowed: false, code: 'agency_off' })
    noActuatorCalls(env)
  })

  it.each([
    ['javascript:alert(1)'],
    ['file:///etc/passwd'],
    ['https://user:pw@example.com'],
    ['http://localhost:3000'],
    ['http://127.0.0.1:9999'],
    ['https://xn--pple-43d.com'],
  ])('blocks %s without asking', async (value) => {
    const { env, open } = setup()
    const r = await open({ kind: 'url', value })
    expect(r.allowed).toBe(false)
    expect(['blocked', 'invalid']).toContain(r.code)
    expect(env.asked).toEqual([])
    noActuatorCalls(env)
  })

  it('opens our own stage on 127.0.0.1:5180 (and only that origin)', async () => {
    const { env, open } = setup()
    expect(await open({ kind: 'url', value: 'http://127.0.0.1:5180/' })).toMatchObject({ done: true })
    expect(env.calls).toEqual(['openUrl http://127.0.0.1:5180/'])
  })

  it('refuses during a scam check and on a safety-critical step', async () => {
    const a = setup()
    a.env.state.patch({ skill: { id: 'spot_scam', name: 'Spot a scam', step: 1, stepCount: 3 } })
    expect(await a.open({ kind: 'url', value: 'https://www.ageuk.org.uk' })).toMatchObject({ allowed: false, code: 'scam_check' })
    const b = setup()
    b.env.bus.emit('lesson:step', { lessonId: 'l', skillId: 'bigger_text', stepIndex: 0, stepCount: 2, phase: 'started', step: { id: 's', index: 0, instruction: 'x', targetDescription: 'x', expectedOutcome: 'x', hints: { l1: '', l2: '', l3: '' }, safetyCritical: true } })
    expect(await b.open({ kind: 'app', value: 'Safari' })).toMatchObject({ allowed: false, code: 'safety_step' })
    noActuatorCalls(a.env)
    noActuatorCalls(b.env)
  })

  it('apps, files and settings go through the right actuator calls', async () => {
    const { env, open } = setup()
    expect(await open({ kind: 'app', value: 'Terminal' })).toMatchObject({ allowed: false })
    expect(await open({ kind: 'settings', value: 'privacy' })).toMatchObject({ allowed: false })
    expect(await open({ kind: 'file', value: '/Users/lily/.ssh/id_rsa' })).toMatchObject({ allowed: false })
    env.clock.t += 5000
    expect(await open({ kind: 'settings', value: 'Text size' })).toMatchObject({ done: true })
    env.clock.t += 5000
    expect(await open({ kind: 'file', value: '/Users/lily/Documents/bill.pdf' })).toMatchObject({ done: true })
    expect(env.calls).toEqual(['openSettingsPane accessibility-display', 'revealPath /Users/lily/Documents/bill.pdf'])
  })

  it('files go through the FILES index: unknown paths are refused, the resolved real path is what gets revealed', async () => {
    const { env, open } = setup()
    env.deps.s.files = { resolveIndexedPath: (p: string) => (p === '/Users/lily/Documents/gp-letter.pdf' ? '/Users/lily/Documents/real/gp-letter.pdf' : null) } as never
    expect(await open({ kind: 'file', value: '/Users/lily/Documents/other.pdf' })).toMatchObject({ allowed: false, code: 'blocked' })
    env.clock.t += 5000
    expect(await open({ kind: 'file', value: '/Users/lily/Documents/gp-letter.pdf' })).toMatchObject({ done: true })
    expect(env.calls).toEqual(['revealPath /Users/lily/Documents/real/gp-letter.pdf'])
  })

  it('a settings pane macOS does not know falls back to opening Settings', async () => {
    const { env, open } = setup()
    env.actResults.set('openSettingsPane', { ok: false, reason: 'failed' })
    expect(await open({ kind: 'settings', value: 'displays' })).toMatchObject({ done: true })
    expect(env.calls).toEqual(['openSettingsPane displays', 'openApp System Settings'])
  })

  it('an OS failure is reported, audited and never retried', async () => {
    const { env, open } = setup()
    env.actResults.set('openApp', { ok: false, reason: 'failed', detail: 'no such app' })
    expect(await open({ kind: 'app', value: 'Nonexistent' })).toMatchObject({ allowed: true, done: false, code: 'failed' })
    expect(env.calls).toEqual(['openApp Nonexistent'])
    expect(env.auditLines()[0]).toMatchObject({ ok: false, code: 'failed' })
    expect(env.learned).toEqual([])
  })

  it('dry run: logged, not performed, not counted', async () => {
    const { env, open } = setup({ dryRun: true })
    const r = await open({ kind: 'url', value: 'https://www.ageuk.org.uk' })
    expect(r).toMatchObject({ done: true, dryRun: true })
    expect(env.auditLines()[0]).toMatchObject({ dryRun: true })
    expect(env.learned).toEqual([])
  })

  it('two opens inside 1.5 s are spaced out, a runaway is stopped', async () => {
    const { env, open } = setup()
    await open({ kind: 'url', value: 'https://www.ageuk.org.uk' })
    const t0 = env.clock.t
    await open({ kind: 'url', value: 'https://www.nhs.uk' })
    expect(env.clock.t - t0).toBeGreaterThanOrEqual(1400)
    let blocked = 0
    for (let i = 0; i < 20; i++) {
      const r = await open({ kind: 'url', value: `https://example${i}.com` })
      if (r.code === 'rate_limited') blocked++
    }
    expect(blocked).toBeGreaterThan(0)
  })

  it('never writes screen content or typed text to the audit log', async () => {
    const { env, open } = setup()
    await open({ kind: 'url', value: 'https://www.google.com/search?q=my+secret+thing' })
    expect(JSON.stringify(env.auditLines())).not.toMatch(/secret thing|q=/)
  })
})
