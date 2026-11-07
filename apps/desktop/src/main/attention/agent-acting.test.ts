import { describe, expect, it } from 'vitest'
import { createAttentionAdapter, type AttentionPorts } from './adapter'
import { createFakeClient } from './client'
import { createVoiceLock } from './lock'
import { CALM_SIGNALS } from './signals'

const ports: AttentionPorts = { showNotice: () => undefined, hideNotice: () => undefined, setBadges: () => undefined, open: () => undefined }

function rig(over: { agentActing?: boolean; cornerCardUp?: boolean } = {}) {
  const fake = createFakeClient({ submit: () => ({ itemId: 'i_c1', show: true, reason: 'shown_now', coalesced: false }) })
  const lock = createVoiceLock(() => 1_000_000)
  const state = { agentActing: over.agentActing ?? false, cornerCardUp: over.cornerCardUp ?? false }
  const adapter = createAttentionAdapter({ client: fake.client, signals: () => CALM_SIGNALS, ports, lock, now: () => 1_000_000, agentActing: () => state.agentActing, cornerCardUp: () => state.cornerCardUp })
  return { adapter, fake, lock, state }
}
const dec = { kind: 'cue', episode_id: 'e_ABC123', expires_in_s: 12, trigger: 'auto' }

describe('Cue while Knack acts for the worker (reason agent_acting) or while a corner card is up', () => {
  it('refuses an unasked "now" item while an agent acts: a local check, the engine is not even asked, and no lock is taken', async () => {
    const r = rig({ agentActing: true })
    expect(await r.adapter.cuePort().admit(dec, () => undefined)).toEqual({ show: false, itemId: null })
    expect(await r.adapter.cuePort().admit({ ...dec, kind: 'offer' }, () => undefined)).toEqual({ show: false, itemId: null })
    expect(r.fake.calls.submit).toEqual([])
    expect(r.lock.holder()).toBeNull()
  })

  it('still shows a cue the worker asked for', async () => {
    const r = rig({ agentActing: true, cornerCardUp: true })
    const res = await r.adapter.cuePort().admit({ ...dec, trigger: 'asked' }, () => undefined)
    expect(res).toEqual({ show: true, itemId: 'i_c1' })
    expect(r.fake.calls.submit[0]).toMatchObject({ asked: true })
  })

  it('yields to a card in the corner column: an unasked cue with no target would dock into that corner', async () => {
    const r = rig({ cornerCardUp: true })
    expect((await r.adapter.cuePort().admit(dec, () => undefined)).show).toBe(false)
    expect(r.fake.calls.submit).toEqual([])
  })

  it('is as before when nothing acts and no card is up', async () => {
    const r = rig()
    expect(await r.adapter.cuePort().admit(dec, () => undefined)).toEqual({ show: true, itemId: 'i_c1' })
    r.state.agentActing = true
    r.adapter.cuePort().release()
    expect((await r.adapter.cuePort().admit(dec, () => undefined)).show).toBe(false)
    r.state.agentActing = false
    expect((await r.adapter.cuePort().admit(dec, () => undefined)).show).toBe(true)
  })
})
