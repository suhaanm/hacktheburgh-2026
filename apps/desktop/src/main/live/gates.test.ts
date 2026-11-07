import { describe, expect, it } from 'vitest'
import { AUDIO_GATE_MAX_AGE_MS, GateMonitor, createGateReader, type GateSources } from './gates'
import { DEFAULT_LIVE_SETTINGS, liveConsentPatch, type LiveSettings } from './settings'
import { manualClock } from './live.test-util'

const consented = (over: Partial<LiveSettings> = {}): LiveSettings => ({ ...DEFAULT_LIVE_SETTINGS, ...liveConsentPatch({ voice: true, frames: true }), ...over }) as LiveSettings

function sources(over: Partial<GateSources> & { bundle?: string | null; secure?: 'on' | 'off' | 'unknown'; locked?: boolean | null; share?: boolean | null } = {}): GateSources {
  return {
    frontmost: { read: async () => (over.bundle === undefined ? 'com.apple.dt.xcode' : over.bundle) },
    console: { read: async () => ({ secureInput: over.secure ?? 'off', locked: over.locked ?? false }) },
    screenShare: { read: async () => over.share ?? false },
    killed: () => false,
    unattended: () => false,
    settings: () => consented(),
    deny: () => ({ strict: true, workerList: [] }),
    ...over,
  }
}

describe('the gates', () => {
  it('open for an ordinary app with consent', async () => {
    const r = createGateReader(sources())
    expect((await r.read('audio')).open).toBe(true)
    expect((await r.read('frames')).gate).toEqual({ consent: true, denylisted_app: false, secure_input: false, unattended: false })
  })
  it('precedence: killed, paused, unattended, secure input, denylisted app, no consent, locked', async () => {
    expect((await createGateReader(sources({ killed: () => true, unattended: () => true })).read('audio')).reason).toBe('killed')
    expect((await createGateReader(sources({ settings: () => consented({ livePausedUntilMs: Date.now() + 1e6 }), unattended: () => true })).read('audio')).reason).toBe('paused')
    expect((await createGateReader(sources({ unattended: () => true, secure: 'on', bundle: 'com.1password.1password' })).read('audio')).reason).toBe('unattended')
    expect((await createGateReader(sources({ secure: 'on', bundle: 'com.1password.1password' })).read('audio')).reason).toBe('secure_input')
    expect((await createGateReader(sources({ bundle: 'com.1password.1password' })).read('audio')).reason).toBe('denylisted_app')
    expect((await createGateReader(sources({ settings: () => consented({ liveEnabled: false }) })).read('audio')).reason).toBe('no_consent')
    expect((await createGateReader(sources({ locked: true })).read('audio')).reason).toBe('locked')
  })
  it('unattended always blocks, even with everything else fine', async () => {
    const v = await createGateReader(sources({ unattended: () => true })).read('frames')
    expect(v.open).toBe(false)
    expect(v.gate.unattended).toBe(true)
  })
  it('frames need their own consent; audio does not', async () => {
    const s = sources({ settings: () => consented({ liveFrames: false }) })
    expect((await createGateReader(s).read('audio')).open).toBe(true)
    const f = await createGateReader(s).read('frames')
    expect(f.open).toBe(false)
    expect(f.reason).toBe('no_consent')
  })
  it('strict mode blocks frames when the app or the secure-input state cannot be read, but a spoken question is not stopped by that', async () => {
    const unreadable = sources({ bundle: null, secure: 'unknown' })
    expect((await createGateReader(unreadable).read('frames')).open).toBe(false)
    expect((await createGateReader(unreadable).read('audio')).open).toBe(true)
    const loose = sources({ bundle: null, secure: 'unknown', deny: () => ({ strict: false, workerList: [] }) })
    expect((await createGateReader(loose).read('frames')).open).toBe(true)
  })
  it('messaging and mail apps are denied in strict mode, the worker list always, and password managers cannot be switched off', async () => {
    expect((await createGateReader(sources({ bundle: 'com.tinyspeck.slackmacgap' })).read('audio')).reason).toBe('denylisted_app')
    expect((await createGateReader(sources({ bundle: 'com.tinyspeck.slackmacgap', deny: () => ({ strict: false, workerList: [] }) })).read('audio')).open).toBe(true)
    expect((await createGateReader(sources({ bundle: 'com.example.private', deny: () => ({ strict: false, workerList: ['com.example.*'] }) })).read('audio')).reason).toBe('denylisted_app')
    expect((await createGateReader(sources({ bundle: 'com.bitwarden.desktop', deny: () => ({ strict: false, workerList: [] }) })).read('audio')).reason).toBe('denylisted_app')
  })
  it('a shared screen blocks frames only', async () => {
    const s = sources({ share: true })
    expect((await createGateReader(s).read('audio')).open).toBe(true)
    expect((await createGateReader(s).read('frames')).reason).toBe('screen_share')
  })
})

describe('the audio monitor', () => {
  it('is closed before its first reading, follows the probes, and goes stale (closed) when they stop answering', async () => {
    const clock = manualClock()
    let open = true
    const reader = { read: async () => ({ open, reason: open ? null : ('secure_input' as const), gate: { consent: true, denylisted_app: false, secure_input: !open, unattended: false }, at: clock.now() }) }
    const m = new GateMonitor(reader, clock, clock.now, 500)
    expect(m.audio().open).toBe(false)
    await m.start()
    expect(m.audio().open).toBe(true)
    open = false
    clock.advance(500)
    await Promise.resolve()
    await new Promise((r) => setTimeout(r, 0))
    expect(m.audio().open).toBe(false)
    expect(m.audio().reason).toBe('secure_input')
    m.stop()
    clock.advance(AUDIO_GATE_MAX_AGE_MS + 1)
    expect(m.audio().reason).toBe('stale')
  })
  it('a failing probe closes the gate instead of leaving the last good answer standing', async () => {
    const clock = manualClock()
    let fail = false
    const reader = { read: async () => { if (fail) throw new Error('probe died'); return { open: true, reason: null, gate: { consent: true, denylisted_app: false, secure_input: false, unattended: false }, at: clock.now() } } }
    const m = new GateMonitor(reader, clock, clock.now, 500)
    await m.start()
    expect(m.audio().open).toBe(true)
    fail = true
    await m.refresh()
    expect(m.audio().open).toBe(false)
    expect(m.audio().reason).toBe('stale')
    m.stop()
  })
  it('creates no timer until it is started and clears it when stopped', async () => {
    const clock = manualClock()
    const m = new GateMonitor({ read: async () => ({ open: true, reason: null, gate: { consent: true, denylisted_app: false, secure_input: false, unattended: false }, at: 0 }) }, clock, clock.now)
    expect(clock.active()).toBe(0)
    await m.start()
    expect(clock.active()).toBe(1)
    m.stop()
    expect(clock.active()).toBe(0)
  })
})
