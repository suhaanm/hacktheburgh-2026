// (f) Stop / idle / session lifecycle through the bus: wake -> connecting -> (live) -> stop -> resting; persona switch; Stop clears everything.
import { beforeAll, describe, expect, it } from 'vitest'
import { REAL, clearOverlayLog, dbg, overlayLog, resetApp, sleep, state, tool, waitFor } from './helpers'

const ACTIVE = ['connecting', 'live', 'thinking', 'speaking']
const RESTING = ['listening_for_name', 'asleep']

describe('session lifecycle', () => {
  beforeAll(async () => {
    await resetApp()
    await waitFor('resting', async () => RESTING.includes((await state()).phase), 5000)
  })

  it('wake (button) starts a session for the persona: phase leaves resting, persona set', async () => {
    const r = await dbg('/wake', { personaId: 'marcus' })
    expect(r.status).toBe(200)
    const s = await waitFor('session active', async () => {
      const cur = await state()
      return ACTIVE.includes(cur.phase) || cur.phase === 'error' ? cur : null
    }, 5000, 100)
    // A session that immediately errors (no mic, no network, no token) is a finding, not a pass.
    expect(s.phase, `phase ${s.phase}, lastError: ${s.lastError ?? '-'}`).not.toBe('error')
    expect(s.persona).toBe('marcus')
    expect(s.settings.persona).toBe('marcus')
  })

  it('a second wake with another persona replaces the session (persona switch)', async () => {
    await dbg('/wake', { personaId: 'amelia' })
    await waitFor('persona amelia', async () => (await state()).persona === 'amelia', 5000, 100)
    const s = await state()
    expect(ACTIVE).toContain(s.phase)
  })

  it('Stop returns to resting, clears the lesson, overlay, and any pending confirm', async () => {
    await tool('start_lesson', { goal: 'Join a video call' })
    const pending = tool('ask_user_confirm', { question: 'Is this a test?', options: ['Yes', 'No'] })
    await waitFor('confirm pending', async () => (await state()).pendingConfirm, 3000, 50)
    await clearOverlayLog()
    const stop = await dbg('/stop', {})
    expect(stop.status).toBe(200)
    const s = await waitFor('resting after stop', async () => {
      const cur = await state()
      return RESTING.includes(cur.phase) ? cur : null
    }, 5000, 100)
    expect(s.skill).toBeUndefined()
    expect(s.pendingConfirm).toBeUndefined()
    const answered = await pending
    expect(answered.result.error).toBeUndefined()
    expect((answered.result as { choice: string | null }).choice, 'Stop must cancel, never approve').toBeNull()
    expect((await overlayLog()).some((o) => o.op === 'clear')).toBe(true)
  })

  it('Stop while already resting is harmless (idempotent)', async () => {
    const before = await state()
    expect((await dbg('/stop', {})).status).toBe(200)
    const after = await state()
    expect(RESTING).toContain(after.phase)
    expect(after.persona).toBe(before.persona)
  })

  it('wakeEnabled=false rests at asleep after a session; true rests at listening_for_name', async () => {
    await dbg('/settings', { patch: { wakeEnabled: false } })
    await dbg('/wake', { personaId: 'marcus' })
    await waitFor('active', async () => ACTIVE.includes((await state()).phase), 5000, 100)
    await dbg('/stop', {})
    await waitFor('asleep', async () => (await state()).phase === 'asleep', 5000, 100)
    await dbg('/settings', { patch: { wakeEnabled: true } })
    await dbg('/wake', { personaId: 'marcus' })
    await waitFor('active', async () => ACTIVE.includes((await state()).phase), 5000, 100)
    await dbg('/stop', {})
    await waitFor('listening_for_name', async () => (await state()).phase === 'listening_for_name', 5000, 100)
  })

  // Real Live connection: token mint + WebSocket + mic. Prints the phase timeline so a failure shows WHY (permissions, network, token).
  it.skipIf(!REAL)('a real wake reaches phase live within 15 s (token + socket + mic); prints the phase timeline', async () => {
    await dbg('/stop', {})
    await waitFor('resting', async () => RESTING.includes((await state()).phase), 5000, 100)
    await dbg('/wake', { personaId: 'amelia' })
    const t0 = Date.now()
    const timeline: string[] = []
    let last = ''
    let reached = false
    while (Date.now() - t0 < 15_000) {
      const s = await state()
      const key = `${s.phase}${s.lastError ? ` [${s.lastError.slice(0, 120)}]` : ''}`
      if (key !== last) {
        timeline.push(`+${((Date.now() - t0) / 1000).toFixed(1)}s ${key}`)
        last = key
      }
      if (s.phase === 'live' || s.phase === 'speaking' || s.phase === 'thinking') {
        reached = true
        break
      }
      if (s.phase === 'error') break
      await sleep(200)
    }
    console.log(`[e2e] live phase timeline: ${timeline.join(' | ')}`)
    expect(reached, `Live never reached "live": ${timeline.join(' | ')}`).toBe(true)
  }, 30_000)

  // The brief says an idle session ends after 20 s. Slow; only meaningful once the dock's Live session really runs.
  it.skipIf(!REAL)('an idle session ends by itself (~20 s, reason idle)', async (ctx) => {
    await dbg('/stop', {})
    await waitFor('resting', async () => RESTING.includes((await state()).phase), 5000, 100)
    await dbg('/wake', { personaId: 'amelia' })
    await waitFor('active', async () => ACTIVE.includes((await state()).phase), 8000, 200)
    const t0 = Date.now()
    const seen: string[] = []
    let slowest = 0
    let ended = false
    while (Date.now() - t0 < 45_000) {
      const p0 = Date.now()
      const phase = await state().then((s) => s.phase, () => 'unreachable')
      slowest = Math.max(slowest, Date.now() - p0)
      const stamp = `${((Date.now() - t0) / 1000).toFixed(0)}s`
      if (!seen.length || !seen[seen.length - 1].endsWith(` ${phase}`)) seen.push(`${stamp} ${phase}`)
      if (RESTING.includes(phase)) {
        ended = true
        break
      }
      await sleep(500)
    }
    const said = (await state()).captions.map((c) => `${c.speaker}: ${c.text.slice(0, 80)}`)
    console.log(`[e2e] idle phases: ${seen.join(' | ')}; slowest /state ${slowest} ms; captions during silence: ${JSON.stringify(said)}`)
    if (!ended && said.some((l) => l.startsWith('user:'))) return ctx.skip(`INCONCLUSIVE: the open mic heard speech during the test (${said.filter((l) => l.startsWith('user:')).join(' / ')}); rerun in a silent room`)
    expect(ended, `session did not end by itself in 45 s: ${seen.join(' | ')} (slowest /state ${slowest} ms)`).toBe(true)
  }, 70_000)
})
