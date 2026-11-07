// (e) Settings and toggles: defaults, every toggle reflected in /state, validation, locked level, persistence, scamShield gate.
import fs from 'node:fs'
import path from 'node:path'
import { beforeAll, describe, expect, it } from 'vitest'
import { REAL, USERDATA, dbg, resetApp, sleep, state, tool, waitFor } from './helpers'

const BOOLEAN_TOGGLES = ['captions', 'textOnly', 'bigAnnotations', 'highContrast', 'dyslexiaFont', 'explainJargon', 'teachBack', 'scamShield', 'pushToTalkOnly', 'listeningLight', 'wakeEnabled', 'carerSharing', 'doItForMeAllowed', 'demoMode'] as const

const patch = (p: Record<string, unknown>) => dbg<Record<string, unknown>>('/settings', { patch: p })
const setting = async (key: string) => (await state()).settings[key]

describe('settings', () => {
  beforeAll(async () => {
    await resetApp()
  })

  it('trust defaults: doItForMeAllowed and carerSharing are OFF; demoMode and captions ON (fresh profile)', async () => {
    const s = (await state()).settings
    expect(s.doItForMeAllowed).toBe(false)
    expect(s.carerSharing).toBe(false)
    expect(s.demoMode).toBe(true)
    expect(s.captions).toBe(true)
  })

  it.each(BOOLEAN_TOGGLES)('toggle %s flips in /state and flips back', async (key) => {
    const before = (await state()).settings[key] as boolean
    const r = await patch({ [key]: !before })
    expect(r.status).toBe(200)
    await waitFor(`${key} -> ${!before}`, async () => (await setting(key)) === !before, 2000, 50)
    await patch({ [key]: before })
    await waitFor(`${key} -> ${before}`, async () => (await setting(key)) === before, 2000, 50)
  })

  it('invalid values are dropped key by key; valid keys in the same patch still apply', async () => {
    const before = (await state()).settings
    const r = await patch({ voiceSpeed: 9, persona: 'bob', pacing: 'warp', helpLevelMode: 'chaos', bogusKey: true, voiceSpeed2: 1, captions: !before.captions })
    expect(r.status).toBe(200)
    const after = (await state()).settings
    expect(after.voiceSpeed).toBe(before.voiceSpeed)
    expect(after.persona).toBe(before.persona)
    expect(after.pacing).toBe(before.pacing)
    expect(after.helpLevelMode).toBe(before.helpLevelMode)
    expect('bogusKey' in after).toBe(false)
    expect(after.captions).toBe(!before.captions)
    await patch({ captions: before.captions })
  })

  it('voiceSpeed accepts the 0.75-1.25 range and rejects outside it', async () => {
    await patch({ voiceSpeed: 0.75 })
    expect(await setting('voiceSpeed')).toBe(0.75)
    await patch({ voiceSpeed: 1.25 })
    expect(await setting('voiceSpeed')).toBe(1.25)
    await patch({ voiceSpeed: 1.26 })
    expect(await setting('voiceSpeed')).toBe(1.25)
    await patch({ voiceSpeed: 1 })
  })

  it('locking the help level pins state.level and makes set_help_level refuse; unlocking restores it', async () => {
    await patch({ helpLevelMode: 'locked', lockedLevel: 4 })
    await waitFor('level locked at 4', async () => {
      const s = await state()
      return s.levelLocked && s.level === 4
    }, 2000, 50)
    const refused = await tool<{ applied: boolean }>('set_help_level', { level: 1, reason: 'qa' })
    expect(refused.result.applied).toBe(false)
    expect((await state()).level).toBe(4)
    await patch({ helpLevelMode: 'auto' })
    await waitFor('unlocked', async () => !(await state()).levelLocked, 2000, 50)
    const applied = await tool<{ applied: boolean; level: number }>('set_help_level', { level: 2, reason: 'qa' })
    // Advisory: the LevelEngine may overrule, so only a plain, error-free answer is required.
    expect(applied.result.error).toBeUndefined()
    expect(typeof applied.result.applied).toBe('boolean')
  })

  it('settings persist to settings.json in the (isolated) profile', async () => {
    await patch({ voiceSpeed: 1.1, explainJargon: false })
    await sleep(1800)
    const file = path.join(USERDATA, 'settings.json')
    expect(fs.existsSync(file), `settings.json at ${file}`).toBe(true)
    const saved = JSON.parse(fs.readFileSync(file, 'utf8')) as Record<string, unknown>
    expect(saved.voiceSpeed).toBe(1.1)
    expect(saved.explainJargon).toBe(false)
    expect(saved.doItForMeAllowed).toBe(false)
    await patch({ voiceSpeed: 1, explainJargon: true })
  })

  it.skipIf(!REAL)('scamShield off takes effect: a scam_check chip refuses and carries no report (toggle must not be cosmetic)', async () => {
    await patch({ scamShield: false })
    const r = await tool<{ agentId?: string }>('spawn_agent', { kind: 'scam_check', task: 'Check this message', payload: { text: 'Your account will be closed, verify now.' } })
    let chip: { status: string; result?: unknown; summary?: string } | undefined
    if (r.result.agentId) chip = await waitFor('chip settles', async () => {
      const c = (await state()).agents.find((a) => a.id === r.result.agentId)
      return c && c.status !== 'running' ? c : null
    }, 15_000, 200)
    await patch({ scamShield: true })
    expect(Boolean(r.result.error) || chip?.result === undefined, 'scam_check produced a report although Scam Shield is off').toBe(true)
  })
})
