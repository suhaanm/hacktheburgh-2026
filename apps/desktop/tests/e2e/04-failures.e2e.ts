// (d) Failure injection at the HTTP boundary of the REAL services (see src/main/dev/fetch-probe.ts). Real mode only.
// Passing means: no hang, a plain-English outcome, no stack traces/SDK jargon, app still healthy.
import { afterEach, beforeAll, describe, expect, it } from 'vitest'
import { APP_LOG, REAL, VISIBLE, clearFault, clearOverlayLog, dbg, dev, fetchLog, overlayLog, resetApp, setFault, state, tool, uglyText, waitFor } from './helpers'
import fs from 'node:fs'

const SCAM_TEXT = 'Aldermoor Bank: your account will be closed in 24 hours. Verify now at http://aldermoor-secure-verify.co/login'

describe.skipIf(!REAL)('failure injection (real services)', () => {
  beforeAll(async () => {
    await resetApp()
    if (VISIBLE) {
      await dev('/dev/stage/open', {})
      await dev('/dev/stage/call', { fn: 'go', args: ['video/lily'] })
    }
  })
  afterEach(async () => {
    await clearFault()
    await tool('end_lesson', { summary: 'test cleanup' })
  })

  // Built-in skills use static plans; only a custom goal reaches the Architect (Argon).
  it('Architect timeout on a custom goal does not hang or crash: start_lesson answers (pointer fallback)', async (ctx) => {
    await setFault({ match: 'argon', mode: 'timeout' })
    const t0 = Date.now()
    const { result } = await tool<{ stepCount: number; skillId: string }>('start_lesson', { goal: 'Teach me how to book a train ticket online' })
    const elapsed = Date.now() - t0
    const faulted = (await fetchLog()).filter((e) => e.faulted && /argon/.test(e.model ?? e.path))
    if (!faulted.length) return ctx.skip('Architect made no Argon call: fault not exercised (INCONCLUSIVE)')
    console.log(`[e2e] architect timeout: fallback after ${elapsed} ms`)
    expect(result.error, `start_lesson error: ${result.error}`).toBeUndefined()
    expect(result.stepCount).toBeGreaterThanOrEqual(1)
    expect(elapsed, 'architect timeout must not leave the learner waiting').toBeLessThan(30_000)
  }, 120_000)

  it('Architect HTTP 500 / garbage on a custom goal also degrades gracefully', async (ctx) => {
    for (const mode of ['http500', 'garbage'] as const) {
      await tool('end_lesson', { summary: 'reset' })
      await setFault({ match: 'argon', mode })
      const { result } = await tool<{ stepCount: number }>('start_lesson', { goal: 'Teach me how to book a train ticket online' })
      const faulted = (await fetchLog()).filter((e) => e.faulted === mode && /argon/.test(e.model ?? e.path))
      if (!faulted.length) return ctx.skip('Architect made no Argon call: fault not exercised (INCONCLUSIVE)')
      expect(result.error, `${mode}: ${result.error}`).toBeUndefined()
      expect(result.stepCount).toBeGreaterThanOrEqual(1)
    }
  }, 120_000)

  for (const mode of ['http500', 'http429', 'http401', 'network', 'garbage', 'empty'] as const) {
    it(`Grounder ${mode}: point_at answers found:false or a plain error, fast, with nothing drawn`, async (ctx) => {
      if (!VISIBLE) return ctx.skip('needs --visible for real capture')
      await clearOverlayLog()
      await setFault({ match: '*', mode })
      const t0 = Date.now()
      const { result } = await tool<{ found?: boolean; note?: string }>('point_at', { target: 'large green button reading Start call' })
      const elapsed = Date.now() - t0
      const faulted = (await fetchLog()).some((e) => e.faulted === mode)
      if (!faulted) return ctx.skip('Grounder made no Google API call: fault not exercised (INCONCLUSIVE)')
      const text = result.error ?? result.note
      expect(result.found === false || Boolean(result.error), 'must not claim a find').toBe(true)
      expect(uglyText(text), `jargon/stack in "${text}"`).toBeNull()
      expect(elapsed).toBeLessThan(45_000)
      const rings = (await overlayLog()).filter((o) => o.op === 'show').flatMap((o) => o.annotations ?? []).filter((a) => a.kind === 'ring')
      expect(rings).toHaveLength(0)
    }, 90_000)
  }

  it('Verifier failure never produces a success tick and stays plain English', async (ctx) => {
    if (!VISIBLE) return ctx.skip('needs --visible for real capture')
    await tool('start_lesson', { goal: 'Join a video call with Lily' })
    await clearOverlayLog()
    await setFault({ match: '*', mode: 'http500' })
    const { result } = await tool<{ completed?: boolean; uncertain?: boolean; evidence?: string }>('verify_step', { expected_outcome: 'The call window is open.' })
    const faulted = (await fetchLog()).some((e) => e.faulted === 'http500')
    if (!faulted) return ctx.skip('Verifier made no Google API call: fault not exercised (INCONCLUSIVE)')
    expect(result.completed === true, 'a failed verification must not report completed').toBe(false)
    expect(uglyText(result.error ?? result.evidence)).toBeNull()
    const ticks = (await overlayLog()).filter((o) => o.op === 'show').flatMap((o) => o.annotations ?? []).filter((a) => a.kind === 'tick' && (a as { ok?: boolean }).ok !== false)
    expect(ticks).toHaveLength(0)
  }, 90_000)

  it('Scam analyst API error: chip ends in a plain-English error (or an honest cannot_tell), never a stack trace', async () => {
    await setFault({ match: '*', mode: 'http500' })
    const spawned = await tool<{ agentId: string }>('spawn_agent', { kind: 'scam_check', task: SCAM_TEXT })
    expect(spawned.result.error).toBeUndefined()
    const chip = await waitFor('scam chip finishes', async () => {
      const c = (await state()).agents.find((a) => a.id === spawned.result.agentId)
      return c && c.status !== 'running' ? c : null
    }, 90_000, 400)
    expect(['error', 'done']).toContain(chip.status)
    expect(uglyText(chip.summary), `chip summary "${chip.summary}"`).toBeNull()
    if (chip.status === 'done') expect(chip.result?.report?.verdict).toBe('cannot_tell')
  }, 120_000)

  it('after all that the app is healthy, state.lastError (if any) is plain English, and the log has no unhandled rejections', async () => {
    expect((await dbg('/health')).status).toBe(200)
    expect(uglyText((await state()).lastError)).toBeNull()
    const log = fs.readFileSync(APP_LOG, 'utf8')
    expect(log).not.toMatch(/UnhandledPromiseRejection|Uncaught Exception|Unhandled rejection/i)
  })
})
