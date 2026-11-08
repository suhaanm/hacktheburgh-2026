// Check voice with fake readings: no microphone, speaker, screen or network. Each stage is Ready or the one thing to do, and nothing here asks macOS for anything.
import { describe, expect, it } from 'vitest'
import { buildVoiceCheck, type VoiceCheckInputs } from './voice-check'
import { createVoiceCheckPort, parseVolumeSettings } from './voice-check-port'
import { LIVE_CONSENT_VERSION } from '../live/settings'
import { TokenError } from '../live/token'

const GOOD: VoiceCheckInputs = {
  now: 1,
  liveFlagOn: true,
  offline: false,
  keyPresent: true,
  modelId: 'live-model',
  killed: false,
  paused: false,
  consent: { liveEnabled: true, consentCurrent: true, voiceAnswer: 'yes' },
  perms: { microphone: 'granted', screen: 'granted', accessibility: true },
  wake: { switchOn: true, dormant: null, helper: { state: 'listening', code: null }, helperPresent: true },
  secureInput: 'off',
  sound: { outputMuted: false, outputVolume: 60, inputVolume: 60 },
  modelCheck: async () => ({ ok: true, reason: 'ok' }),
  tokenCheck: async () => ({ ok: true, reason: 'ok' }),
}
const run = (over: Partial<VoiceCheckInputs> = {}) => buildVoiceCheck({ ...GOOD, ...over })
const stage = (r: Awaited<ReturnType<typeof run>>, id: string) => r.stages.find((s) => s.id === id)!

describe('Check voice', () => {
  it('everything in place: every stage Ready, talking and Hey Knack both work', async () => {
    const r = await run()
    expect(r.ok).toBe(true)
    expect(r.heyKnack).toBe(true)
    expect(r.stages.every((s) => s.state === 'ready')).toBe(true)
    expect(r.stages.map((s) => s.id)).toEqual(['models', 'key', 'service', 'stopped', 'consent', 'microphone', 'secure', 'sound', 'speech', 'hey', 'accessibility', 'screen'])
  })

  it('the stop file: the stage says so and the report is not ok', async () => {
    const r = await run({ killed: true })
    expect(stage(r, 'stopped')).toMatchObject({ state: 'fix', line: 'Everything is stopped. Choose Resume in the menu bar.' })
    expect(r.ok).toBe(false)
    const p = await run({ paused: true })
    expect(stage(p, 'stopped').line).toBe('Knack is paused. Choose Resume in the menu bar.')
  })

  it('the offline mode, a missing key and a missing model each get their own line, and the network is not asked', async () => {
    let asked = 0
    const net = { modelCheck: async () => (asked++, { ok: true, reason: 'ok' }), tokenCheck: async () => (asked++, { ok: true, reason: 'ok' }) }
    const off = await run({ ...net, offline: true })
    expect(stage(off, 'models')).toMatchObject({ state: 'fix', action: { do: 'settings' }, line: 'Voice needs live models. Turn on Use live models in Settings.' })
    // The switch is on and the service just could not be reached: the real reason, no button to a switch that is already on.
    const unreachable = await run({ ...net, offline: true, modelsReason: 'boot_check_failed' })
    expect(stage(unreachable, 'models')).toMatchObject({ state: 'fix', action: null, line: 'Knack could not reach the model service. It keeps trying and will switch on by itself.' })
    expect(stage(unreachable, 'models').line).not.toMatch(/Settings|Use live models/)
    const noKey = await run({ ...net, offline: true, modelsReason: 'no_key', keyPresent: false })
    expect(stage(noKey, 'models')).toMatchObject({ state: 'fix', action: null })
    expect(stage(noKey, 'models').line).toContain('no Gemini key')
    // The worker's own switch off (or nothing said) keeps the Settings wording.
    expect(stage(await run({ ...net, offline: true, modelsReason: 'switched_off' }), 'models').action).toEqual({ do: 'settings' })
    const nokey = await run({ ...net, keyPresent: false })
    expect(stage(nokey, 'key').line).toBe('Voice needs a Gemini key. Add it to the .env file and reopen Knack.')
    const nomodel = await run({ ...net, modelId: null })
    expect(stage(nomodel, 'key').line).toBe('Voice has no model set. Add the voice model name to the .env file and reopen Knack.')
    const flag = await run({ ...net, liveFlagOn: false })
    expect(stage(flag, 'models').line).toContain('Voice is switched off')
    expect(asked).toBe(0)
  })

  it('the model and the voice service: unknown model, cannot stream, unreachable, refused key', async () => {
    expect(stage(await run({ modelCheck: async () => ({ ok: false, reason: 'unknown_model' }) }), 'key').line).toBe('The key cannot use the voice model that is set. Check both in the .env file and reopen Knack.')
    expect(stage(await run({ modelCheck: async () => ({ ok: false, reason: 'cannot_stream' }) }), 'key').line).toContain('cannot hold a voice conversation')
    expect(stage(await run({ modelCheck: async () => ({ ok: false, reason: 'unreachable' }) }), 'key').line).toContain('Check your internet connection')
    const refused = await run({ tokenCheck: async () => ({ ok: false, reason: 'refused' }) })
    expect(stage(refused, 'service')).toMatchObject({ state: 'fix', line: 'The voice service refused the key. Check it in the .env file and reopen Knack.' })
    expect(stage(await run({ tokenCheck: async () => ({ ok: false, reason: 'network' }) }), 'service').line).toContain('Check your internet connection')
    const threw = await run({ modelCheck: async () => { throw new Error('x') } })
    expect(stage(threw, 'key').state).toBe('fix')
  })

  it('the worker’s yes: not given, or Never (with the way back)', async () => {
    const none = await run({ consent: { liveEnabled: false, consentCurrent: false, voiceAnswer: 'unset' } })
    expect(stage(none, 'consent')).toMatchObject({ state: 'fix', action: null })
    expect(stage(none, 'consent').line).toContain('Say yes on the Talk with Knack card')
    const never = await run({ consent: { liveEnabled: false, consentCurrent: false, voiceAnswer: 'never' } })
    expect(stage(never, 'consent').action).toEqual({ do: 'ask_again' })
  })

  it('the microphone: never asked gives Allow (macOS asks on the click), denied gives the Settings pane, restricted gives no button', async () => {
    expect(stage(await run({ perms: { ...GOOD.perms, microphone: 'not-determined' } }), 'microphone')).toMatchObject({ state: 'fix', action: { do: 'ask', what: 'microphone' }, line: 'Knack has not asked for the microphone yet. Choose Allow.' })
    expect(stage(await run({ perms: { ...GOOD.perms, microphone: 'denied' } }), 'microphone')).toMatchObject({ action: { do: 'open', what: 'microphone' }, line: 'Switch Knack on in System Settings, Microphone.' })
    expect(stage(await run({ perms: { ...GOOD.perms, microphone: 'restricted' } }), 'microphone').action).toBeNull()
    expect((await run({ perms: { ...GOOD.perms, microphone: 'denied' } })).ok).toBe(false)
  })

  it('speech recognition and the listener only matter for Hey Knack: holding Option-Space stays ok without them', async () => {
    const notAsked = await run({ wake: { switchOn: true, dormant: null, helper: { state: 'stopped', code: null }, helperPresent: true } })
    expect(stage(notAsked, 'speech')).toMatchObject({ state: 'fix', needs: 'hey', action: { do: 'ask', what: 'speech' } })
    expect(notAsked.ok).toBe(true)
    expect(notAsked.heyKnack).toBe(false)
    const denied = await run({ wake: { switchOn: true, dormant: null, helper: { state: 'blocked', code: 'speech_denied' }, helperPresent: true } })
    expect(stage(denied, 'speech')).toMatchObject({ action: { do: 'open', what: 'speech' } })
    expect(stage(denied, 'hey').line).toContain('Hold Option-Space to talk meanwhile')
    expect(denied.ok).toBe(true)
    const switchedOff = await run({ wake: { switchOn: false, dormant: 'switched_off', helper: { state: 'stopped', code: null }, helperPresent: true } })
    expect(stage(switchedOff, 'speech')).toMatchObject({ state: 'fix', action: null, line: 'Not asked yet. Turn on Listen for Hey Knack and macOS will ask.' })
    const noHelper = await run({ wake: { switchOn: true, dormant: null, helper: { state: 'stopped', code: null }, helperPresent: false } })
    expect(stage(noHelper, 'hey').line).toBe('Hey Knack is not installed. Hold Option-Space to talk instead.')
    const off = await run({ wake: { switchOn: false, dormant: 'switched_off', helper: { state: 'stopped', code: null }, helperPresent: true } })
    expect(stage(off, 'hey')).toMatchObject({ state: 'fix', action: { do: 'settings' } })
    const asleep = await run({ wake: { switchOn: true, dormant: 'locked', helper: { state: 'stopped', code: null }, helperPresent: true } })
    expect(stage(asleep, 'hey').line).toBe('Not listening while the screen is locked.')
    const talking = await run({ wake: { switchOn: true, dormant: 'live_session', helper: { state: 'stopped', code: null }, helperPresent: true } })
    expect(stage(talking, 'hey').state).toBe('ready')
    const none = await run({ wake: null })
    expect(stage(none, 'hey').line).toBe('Hey Knack is not in this app. Hold Option-Space to talk.')
    expect(none.ok).toBe(true)
  })

  it('a password field, and the Mac’s own sound: muted, zero volume, zero microphone volume', async () => {
    expect(stage(await run({ secureInput: 'on' }), 'secure')).toMatchObject({ state: 'fix' })
    expect(stage(await run({ secureInput: 'unknown' }), 'secure').state).toBe('ready')
    expect(stage(await run({ sound: { outputMuted: true, outputVolume: 40, inputVolume: 40 } }), 'sound')).toMatchObject({ state: 'fix', action: { do: 'open', what: 'sound' }, line: 'The Mac is muted, so you could not hear Knack. Turn the sound on.' })
    expect(stage(await run({ sound: { outputMuted: false, outputVolume: 0, inputVolume: 40 } }), 'sound').line).toContain('volume is at zero')
    expect(stage(await run({ sound: { outputMuted: false, outputVolume: 40, inputVolume: 0 } }), 'sound').line).toContain('microphone volume is at zero')
    expect(stage(await run({ sound: null }), 'sound').state).toBe('ready')
    expect((await run({ sound: { outputMuted: true, outputVolume: 40, inputVolume: 40 } })).ok).toBe(false)
  })

  it('accessibility and screen recording are listed but never stop talking', async () => {
    const r = await run({ perms: { microphone: 'granted', screen: 'not-determined', accessibility: false } })
    expect(stage(r, 'accessibility')).toMatchObject({ state: 'fix', optional: true, action: { do: 'ask', what: 'accessibility' } })
    expect(stage(r, 'screen')).toMatchObject({ state: 'fix', optional: true, action: { do: 'ask', what: 'screen' } })
    expect(r.ok).toBe(true)
    expect(r.heyKnack).toBe(true)
    expect(stage(await run({ perms: { ...GOOD.perms, screen: 'denied' } }), 'screen').action).toEqual({ do: 'open', what: 'screen' })
  })

  it('every line is plain: short, no developer words, no banned phrases', async () => {
    const worst = await run({ offline: true, keyPresent: false, killed: true, consent: { liveEnabled: false, consentCurrent: false, voiceAnswer: 'never' }, perms: { microphone: 'denied', screen: 'denied', accessibility: false }, secureInput: 'on', sound: { outputMuted: true, outputVolume: 0, inputVolume: 0 }, wake: { switchOn: true, dormant: null, helper: { state: 'blocked', code: 'speech_denied' }, helperPresent: true } })
    for (const s of worst.stages) {
      expect(s.line.split(/\s+/).length, s.id).toBeLessThanOrEqual(30)
      expect(s.line, s.id).not.toMatch(/demo|mock|synthetic|simulated|example data|sample data|stand-in|please|oops|invalid|UNDERSTUDY_|GEMINI_|ledger/i)
    }
  })
})

describe('the real readings', () => {
  it('parses the volume settings, with a missing input volume', () => {
    expect(parseVolumeSettings('output volume:63, input volume:63, alert volume:100, output muted:false')).toEqual({ outputMuted: false, outputVolume: 63, inputVolume: 63 })
    expect(parseVolumeSettings('output volume:0, input volume:missing value, alert volume:100, output muted:true')).toEqual({ outputMuted: true, outputVolume: 0, inputVolume: null })
    expect(parseVolumeSettings('')).toBeNull()
  })

  const ports = (over: { env?: Record<string, string>; tokens?: 'ok' | TokenError } = {}) => {
    const patches: unknown[] = []
    const listen: boolean[] = []
    const asked: string[] = []
    const port = createVoiceCheckPort({
      env: { UNDERSTUDY_X_LIVE: '1', UNDERSTUDY_FLAG_VOICE: '1', GEMINI_API_KEY: 'k', GEMINI_MODEL_LIVE: 'live-model', ...over.env },
      platform: 'darwin',
      live: () => ({ settings: { get: () => ({ liveEnabled: true, liveConsentVersion: LIVE_CONSENT_VERSION }) as never } }),
      wake: () => ({
        status: () => ({ switchOn: true, listening: true, dormant: null, helper: { state: 'listening', code: null }, session: false, click: 'idle', line: '', fix: null, welcomed: true }) as never,
        settings: { get: () => ({ voiceAnswer: 'yes' }) as never, patch: (p) => void patches.push(p) },
        helperPresent: () => true,
        setListen: (on) => void listen.push(on),
      }),
      permissions: { status: async () => ({ microphone: 'granted', screen: 'granted', accessibility: true, probe: 'ok', needsRestart: false, hint: '' }) as never },
      killed: () => false,
      paused: () => false,
      consoleProbe: { read: async () => ({ secureInput: 'off', locked: false }) },
      volume: async () => 'output volume:50, input volume:50, alert volume:100, output muted:false',
      modelCheck: async (m) => (asked.push(`model:${m}`), { ok: true, reason: 'ok' }),
      minter: { mint: async () => (asked.push('token'), over.tokens instanceof TokenError ? Promise.reject(over.tokens) : { token: 'auth_tokens/x', expiresAt: 1 }) },
    })
    return { port, patches, listen, asked }
  }

  it('reads everything and says ready; the model and the token are asked once each, with no content', async () => {
    const { port, asked } = ports()
    const r = await port.check()
    expect(r.ok).toBe(true)
    expect(asked).toEqual(['model:live-model', 'token'])
  })
  it('a refused token is the voice service line; no key means the network is never asked', async () => {
    const refused = await ports({ tokens: new TokenError('refused', 'x') }).port.check()
    expect(refused.stages.find((s) => s.id === 'service')?.state).toBe('fix')
    const t = ports({ env: { GEMINI_API_KEY: '' } })
    const r = await t.port.check()
    expect(r.stages.find((s) => s.id === 'key')?.line).toContain('Gemini key')
    expect(t.asked).toEqual([])
  })
  it('Ask me again forgets an earlier Never or Not now; the yes is still the worker’s click on the card', () => {
    const { port, patches, listen } = ports()
    expect(port.askAgain()).toBe(true)
    expect(patches[0]).toEqual({ voiceAnswer: 'unset', voiceAskAfterMs: 0, screenAnswer: 'unset', screenAskAfterMs: 0 })
    expect(listen).toEqual([true])
    expect(JSON.stringify(patches)).not.toContain('"yes"')
  })
})
