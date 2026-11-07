import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { createLiveManager, type LiveManager, type ManagerDeps, type Refusal } from './manager'
import { LiveSettingsStore, liveConsentPatch } from './settings'
import { createMemoryLiveLedger } from './ledger'
import { LIVE_SYSTEM_INSTRUCTION } from './prompt'
import { CircuitBreaker, createUsageLog } from './meter'
import { chunks32ms, createFakeAudio, fakeCue, manualClock, startFakeLiveServer, tonePcm, waitFor, type FakeAudio, type FakeLiveServer, type ManualClock } from './live.test-util'
import type { LiveCuePort } from './ports'

type Listener = (p: any) => void
function fakeBus() {
  const m = new Map<string, Set<Listener>>()
  return {
    on: (e: string, l: Listener) => {
      if (!m.has(e)) m.set(e, new Set())
      m.get(e)!.add(l)
      return () => void m.get(e)!.delete(l)
    },
    emit: (e: string, p: unknown) => void [...(m.get(e) ?? [])].forEach((l) => l(p)),
    count: (e: string) => m.get(e)?.size ?? 0,
  }
}

const ENV_ON = { UNDERSTUDY_X_LIVE: '1', UNDERSTUDY_FLAG_VOICE: '1', GEMINI_MODEL_LIVE: 'test-live-model', GEMINI_API_KEY: 'k-test' }

interface H {
  server: FakeLiveServer
  audio: FakeAudio
  clock: ManualClock
  bus: ReturnType<typeof fakeBus>
  settings: LiveSettingsStore
  ledger: ReturnType<typeof createMemoryLiveLedger>
  usage: ReturnType<typeof createUsageLog>
  cue: LiveCuePort & ReturnType<typeof fakeCue>
  mint: { calls: number }
  state: { killed: boolean; acting: boolean; mic: 'granted' | 'denied' | 'not-determined' }
  mgr: LiveManager
  make(over?: Partial<ManagerDeps>): LiveManager
}
let h: H
const managers: LiveManager[] = []

beforeEach(async () => {
  const server = await startFakeLiveServer()
  const clock = manualClock()
  const settings = new LiveSettingsStore(null)
  settings.patch(liveConsentPatch({ voice: true, frames: false, dailyUsd: 0.5 }), { trusted: true })
  const mint = { calls: 0 }
  const state = { killed: false, acting: false, mic: 'granted' as 'granted' | 'denied' | 'not-determined' }
  const audio = createFakeAudio()
  const bus = fakeBus()
  const ledger = createMemoryLiveLedger()
  const usage = createUsageLog(null)
  const cue = fakeCue()
  const make = (over: Partial<ManagerDeps> = {}): LiveManager => {
    const m = createLiveManager({
      env: ENV_ON,
      settings,
      bus: bus as never,
      tokens: { mint: async () => (mint.calls++, { token: 'auth_tokens/TESTTOKEN0123456789', expiresAt: Date.now() + 1e6 }) },
      gateSources: { frontmost: { read: async () => 'com.apple.dt.xcode' }, console: { read: async () => ({ secureInput: 'off', locked: false }) }, killed: () => state.killed, unattended: () => state.acting, settings: () => settings.get(), deny: () => ({ strict: true, workerList: [] }) },
      gateTimers: clock,
      ledger,
      audio,
      cue,
      ring: { show: () => undefined, clear: () => undefined },
      usage,
      breaker: new CircuitBreaker({ now: clock.now }),
      micStatus: () => state.mic,
      agentActing: () => state.acting,
      killed: () => state.killed,
      url: server.url,
      timers: clock,
      now: clock.now,
      ...over,
    })
    managers.push(m)
    return m
  }
  h = { server, audio, clock, bus, settings, ledger, usage, cue, mint, state, mgr: make(), make }
})

afterEach(async () => {
  for (const m of managers.splice(0)) m.dispose()
  await h.server.close()
})

const press = (): void => h.bus.emit('talk', { source: 'hotkey', phase: 'press' })
const release = (): void => h.bus.emit('talk', { source: 'hotkey', phase: 'release' })

describe('nothing starts by itself', () => {
  it('with the flags off: no timer, no token, no microphone, no socket, even when the key is pressed', async () => {
    const m = h.make({ env: {} })
    m.start()
    expect(h.clock.active()).toBe(0)
    expect(h.bus.count('talk')).toBe(0)
    expect(h.bus.count('session:ended')).toBe(0)
    press()
    await new Promise((r) => setTimeout(r, 50))
    expect(h.mint.calls).toBe(0)
    expect(h.audio.micStarts).toBe(0)
    expect(h.server.received.connections).toBe(0)
    expect(m.status().phase).toBe('off')
    expect(m.workerUsedVoice()).toBe(false)
  })
  it('with the flags on but no key press: nothing happens, however long it waits, and no timer runs', async () => {
    h.mgr.start()
    expect(h.clock.active()).toBe(0)
    h.clock.advance(10 * 60_000)
    await new Promise((r) => setTimeout(r, 50))
    expect(h.mint.calls).toBe(0)
    expect(h.audio.micStarts).toBe(0)
    expect(h.server.received.connections).toBe(0)
    expect(h.mgr.status()).toMatchObject({ phase: 'idle', flagOn: true, enabled: true, usedVoice: false })
  })
  it('a release with no press does nothing', async () => {
    h.mgr.start()
    release()
    expect(h.audio.micStarts).toBe(0)
  })
  it('a manager that was never started listens to nothing', () => {
    expect(h.bus.count('talk')).toBe(0)
    press()
    expect(h.audio.micStarts).toBe(0)
  })
})

describe('the press', () => {
  it('opens the microphone and the socket, hears the worker only while the key is down, answers, and ends after the grace', async () => {
    h.mgr.start()
    press()
    await waitFor(() => h.server.received.connections === 1 && h.audio.micOpen)
    expect(h.mgr.status().phase === 'connecting' || h.mgr.status().phase === 'listening').toBe(true)
    expect(h.mgr.workerUsedVoice()).toBe(true)
    // context engineering: the provider's running context is bounded, the instruction is the fixed one, and no transcript is requested
    await waitFor(() => h.server.received.setup !== null)
    const setup = h.server.received.setup as Record<string, any>
    expect(setup.contextWindowCompression).toEqual({ triggerTokens: 8000, slidingWindow: { targetTokens: 4000 } })
    expect(setup.systemInstruction.parts[0].text).toBe(LIVE_SYSTEM_INSTRUCTION)
    expect(setup.inputAudioTranscription).toBeUndefined()
    for (const c of chunks32ms(tonePcm(0.4))) h.audio.feed(c)
    await waitFor(() => h.server.received.audio > 5)
    release()
    expect(h.audio.micOpen).toBe(false)
    await waitFor(() => h.audio.played.length >= 2)
    h.audio.idle()
    h.clock.advance(9000)
    await waitFor(() => h.mgr.status().phase === 'idle')
    const s = h.mgr.status()
    expect(s.lastEnd).toMatchObject({ reason: 'release_grace', mode: 'converse' })
    expect(s.todayUsd).toBeGreaterThan(0)
    expect(s.sessionsToday).toBe(1)
    const row = h.usage.rows()[0]!
    expect(Object.keys(row).sort()).toEqual(['day', 'ended', 'frames', 'mode', 'model', 'price_source', 'seconds_in', 'seconds_out', 't', 'turns', 'usd'])
  })
  it('a second press during the conversation is the same conversation', async () => {
    h.mgr.start()
    press()
    await waitFor(() => h.server.received.connections === 1)
    release()
    press()
    await new Promise((r) => setTimeout(r, 50))
    expect(h.server.received.connections).toBe(1)
    expect(h.mint.calls).toBe(1)
  })
  it('the shell stopping everything (session:ended) ends the conversation and closes the microphone', async () => {
    h.mgr.start()
    press()
    await waitFor(() => h.audio.micOpen)
    h.bus.emit('session:ended', { reason: 'stop' })
    expect(h.mgr.hasSession()).toBe(false)
    expect(h.audio.micOpen).toBe(false)
    expect(h.mgr.status().lastEnd?.reason).toBe('stop')
  })
  it('stopAll ends it with the reason given', async () => {
    h.mgr.start()
    press()
    await waitFor(() => h.audio.micOpen)
    h.mgr.stopAll('killed')
    expect(h.mgr.status().lastEnd?.reason).toBe('killed')
  })
  it('reports the HUD timer once a second while a conversation is open, and stops when it is not', async () => {
    h.mgr.start()
    const seen: number[] = []
    h.mgr.subscribe((s) => seen.push(s.elapsedMs))
    press()
    await waitFor(() => h.audio.micOpen)
    const n = seen.length
    h.clock.advance(3000)
    expect(seen.length).toBeGreaterThanOrEqual(n + 3)
    expect(Math.max(...seen)).toBeGreaterThanOrEqual(2000)
    expect(h.mgr.status().maxMs).toBe(300_000)
    h.mgr.stopAll()
    const m = seen.length
    h.clock.advance(3000)
    expect(seen.length).toBe(m)
  })
})

describe('the start gates (each refusal is a closed code, and nothing opens)', () => {
  const cases: Array<[Refusal, () => void]> = [
    ['not_enabled', () => h.settings.patch({ liveEnabled: false }, { trusted: true })],
    ['no_consent', () => h.settings.patch({ liveConsentVersion: 0 }, { trusted: true })],
    ['paused', () => void h.settings.pauseFor()],
    ['killed', () => void (h.state.killed = true)],
    ['agent_acting', () => void (h.state.acting = true)],
    ['mic_permission', () => void (h.state.mic = 'denied')],
  ]
  it.each(cases)('refuses with %s', async (reason, arrange) => {
    arrange()
    h.mgr.start()
    press()
    await new Promise((r) => setTimeout(r, 40))
    expect(h.mgr.status().refused).toBe(reason)
    expect(h.mint.calls).toBe(0)
    expect(h.audio.micStarts).toBe(0)
    expect(h.server.received.connections).toBe(0)
    expect(h.mgr.hasSession()).toBe(false)
  })
  it('never asks for the microphone: with the permission not yet decided it refuses and opens nothing', async () => {
    h.state.mic = 'not-determined'
    h.mgr.start()
    press()
    await new Promise((r) => setTimeout(r, 40))
    expect(h.mgr.status().refused).toBe('mic_permission')
    expect(h.audio.micStarts).toBe(0)
  })
  it.each([
    ['no_model', { UNDERSTUDY_X_LIVE: '1', UNDERSTUDY_FLAG_VOICE: '1', GEMINI_API_KEY: 'k' }],
    ['no_key', { UNDERSTUDY_X_LIVE: '1', UNDERSTUDY_FLAG_VOICE: '1', GEMINI_MODEL_LIVE: 'm' }],
    ['mock_mode', { ...ENV_ON, UNDERSTUDY_MOCK: '1' }],
    ['mock_mode', { ...ENV_ON, ALONGSIDE_MOCK: '1' }],
  ] as const)('refuses with %s from the environment alone', async (reason, env) => {
    const m = h.make({ env })
    m.start()
    press()
    await new Promise((r) => setTimeout(r, 40))
    expect(m.status().refused).toBe(reason)
    expect(h.mint.calls).toBe(0)
  })
  it('with the ledger route missing (an engine without it) nothing opens: no microphone, no token, no socket', async () => {
    h.ledger.refuse('ledger_unavailable')
    h.mgr.start()
    press()
    await waitFor(() => h.mgr.status().lastEnd !== null)
    expect(h.mgr.status().lastEnd?.reason).toBe('blocked')
    expect(h.mint.calls).toBe(0)
    expect(h.audio.micStarts).toBe(0)
    expect(h.server.received.connections).toBe(0)
    expect(h.mgr.hasSession()).toBe(false)
  })
  it('refuses once the day cap is spent, with the usage that earlier conversations recorded', async () => {
    h.usage.record({ t: '', day: Number(`${new Date(h.clock.now()).getFullYear()}${String(new Date(h.clock.now()).getMonth() + 1).padStart(2, '0')}${String(new Date(h.clock.now()).getDate()).padStart(2, '0')}`), mode: 'converse', seconds_in: 1, seconds_out: 1, frames: 0, turns: 1, usd: 0.5, ended: 'release_grace', price_source: 'assumed_default', model: 'm' })
    h.mgr.start()
    press()
    await new Promise((r) => setTimeout(r, 40))
    expect(h.mgr.status().refused).toBe('day_cap')
    expect(h.mint.calls).toBe(0)
  })
  it('refuses when the boot check found the configured model unusable, but not when the network was merely unreachable', async () => {
    const bad = h.make({ modelCheck: async () => ({ ok: false, reason: 'unknown_model' }) })
    bad.start()
    await new Promise((r) => setTimeout(r, 10))
    press()
    await new Promise((r) => setTimeout(r, 40))
    expect(bad.status().refused).toBe('model_unusable')
    expect(h.mint.calls).toBe(0)
  })
  it('an unreachable network at boot does not block a later try', async () => {
    const m = h.make({ modelCheck: async () => ({ ok: false, reason: 'unreachable' }) })
    m.start()
    await new Promise((r) => setTimeout(r, 10))
    expect(m.voiceAllowed()).toBe(true)
  })
})

describe('the circuit breaker', () => {
  it('three failed connections in a row open it; the fourth press is refused and the card carries on without voice', async () => {
    const m = h.make({ url: 'ws://127.0.0.1:1/live' })
    m.start()
    for (let i = 0; i < 3; i++) {
      press()
      await waitFor(() => !m.hasSession())
      release()
    }
    expect(m.status().breakerOpen).toBe(true)
    press()
    await new Promise((r) => setTimeout(r, 30))
    expect(m.status().refused).toBe('breaker_open')
    h.clock.advance(301_000)
    expect(m.status().breakerOpen).toBe(false)
  })
})

describe('Cue listens once', () => {
  it('waits for a talk press: no press, no microphone, null at the end of the window', async () => {
    h.mgr.start()
    const p = h.mgr.listen(2000)
    await new Promise((r) => setTimeout(r, 30))
    expect(h.audio.micStarts).toBe(0)
    expect(h.mint.calls).toBe(0)
    h.clock.advance(2100)
    expect(await p).toBeNull()
    expect(h.audio.micStarts).toBe(0)
  })
  it('a press inside the window opens a one-answer turn and resolves with the words heard', async () => {
    h.server.onTurnEnd = (srv) => srv.send({ serverContent: { inputTranscription: { text: 'the second one', finished: true } } })
    h.mgr.start()
    const p = h.mgr.listen(6000)
    await new Promise((r) => setTimeout(r, 20))
    press()
    await waitFor(() => h.audio.micOpen)
    expect(h.mgr.status().mode).toBe('transcribe')
    for (const c of chunks32ms(tonePcm(0.3))) h.audio.feed(c)
    await waitFor(() => h.server.received.audio > 3)
    release()
    await new Promise((r) => setTimeout(r, 40))
    h.clock.advance(500)
    expect(await p).toBe('the second one')
    expect(h.audio.micOpen).toBe(false)
    expect(h.audio.played).toEqual([])
    expect((h.server.received.setup as any).tools).toBeUndefined()
    expect(h.mgr.workerUsedVoice()).toBe(true)
    expect(h.mgr.hasSession()).toBe(false)
  })
  it('resolves null at once when voice is not allowed (and never opens anything)', async () => {
    h.state.mic = 'denied'
    h.mgr.start()
    expect(await h.mgr.listen(6000)).toBeNull()
    expect(h.audio.micStarts).toBe(0)
  })
  it('stopAll resolves a waiting listener with null', async () => {
    h.mgr.start()
    const p = h.mgr.listen(6000)
    h.mgr.stopAll()
    expect(await p).toBeNull()
  })
  it('only one listener at a time', async () => {
    h.mgr.start()
    void h.mgr.listen(6000)
    expect(await h.mgr.listen(6000)).toBeNull()
  })
})

describe('the question card answer reaches the model', () => {
  it('tells the running conversation which step the worker chose, by its pack label', async () => {
    h.mgr.start()
    press()
    await waitFor(() => h.server.received.connections === 1)
    await waitFor(() => h.audio.micOpen)
    await new Promise((r) => setTimeout(r, 30))
    h.cue.answer('calc_a')
    await waitFor(() => h.server.received.text.length === 1)
    expect(h.server.received.text[0]).toBe('The worker chose: Run calculator A')
  })
})
