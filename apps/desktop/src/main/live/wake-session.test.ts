// The conversation that begins with the words "Hey Knack": same manager, same gates, hands-free, with the wake tools and the code-built context packet.
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { FALLBACK_PACKET } from '../wake/context-packet'
import { createMemoryLiveLedger } from './ledger'
import { createLiveManager, type LiveManager, type ManagerDeps } from './manager'
import { CircuitBreaker, createUsageLog } from './meter'
import { LiveSettingsStore, liveConsentPatch } from './settings'
import { WAKE_SYSTEM_INSTRUCTION } from './prompt'
import type { GroundAnswer } from './ports'
import { createFakeAudio, fakeCue, manualClock, startFakeLiveServer, waitFor, type FakeAudio, type FakeLiveServer, type ManualClock } from './live.test-util'

const ENV_ON = { UNDERSTUDY_X_LIVE: '1', UNDERSTUDY_FLAG_VOICE: '1', GEMINI_MODEL_LIVE: 'test-live-model', GEMINI_API_KEY: 'k-test' }
const BUS = { on: () => () => undefined }

interface H {
  server: FakeLiveServer
  audio: FakeAudio
  clock: ManualClock
  settings: LiveSettingsStore
  rings: Array<{ box: number[]; ghost: boolean }>
  cleared: number
  doIt: Array<{ description: string; box: unknown }>
  ground: GroundAnswer | null
  make(over?: Partial<ManagerDeps>): LiveManager
}
let h: H
const managers: LiveManager[] = []

beforeEach(async () => {
  const server = await startFakeLiveServer()
  const clock = manualClock()
  const settings = new LiveSettingsStore(null)
  settings.patch(liveConsentPatch({ voice: true, frames: false, dailyUsd: 0.5 }), { trusted: true })
  const audio = createFakeAudio()
  const cue = fakeCue()
  const state = { rings: [] as H['rings'], cleared: 0, doIt: [] as H['doIt'], ground: null as GroundAnswer | null }
  const make = (over: Partial<ManagerDeps> = {}): LiveManager => {
    const m = createLiveManager({
      env: ENV_ON,
      settings,
      bus: BUS as never,
      tokens: { mint: async () => ({ token: 'auth_tokens/TESTTOKEN0123456789', expiresAt: Date.now() + 1e6 }) },
      gateSources: { frontmost: { read: async () => 'com.apple.dt.xcode' }, console: { read: async () => ({ secureInput: 'off', locked: false }) }, killed: () => false, unattended: () => false, settings: () => settings.get(), deny: () => ({ strict: true, workerList: [] }) },
      gateTimers: clock,
      ledger: createMemoryLiveLedger(),
      audio,
      cue,
      ground: { ground: async () => state.ground },
      ring: { show: (box, o) => void state.rings.push({ box: [...box], ghost: o?.ghost === true }), clear: () => void (state.cleared += 1) },
      doIt: async (req) => {
        state.doIt.push(req)
        return { ok: false, reason: 'first_supervised_test_pending' }
      },
      usage: createUsageLog(null),
      breaker: new CircuitBreaker({ now: clock.now }),
      micStatus: () => 'granted',
      agentActing: () => false,
      killed: () => false,
      url: server.url,
      timers: clock,
      now: clock.now,
      ...over,
    })
    managers.push(m)
    return m
  }
  h = {
    server, audio, clock, settings, make,
    get rings() { return state.rings },
    get cleared() { return state.cleared },
    get doIt() { return state.doIt },
    get ground() { return state.ground },
    set ground(v) { state.ground = v },
  } as H
})

afterEach(async () => {
  for (const m of managers.splice(0)) m.dispose()
  await h.server.close()
})

const setup = (): Record<string, any> => h.server.received.setup as Record<string, any>
const declared = (): string[] => (setup().tools[0].functionDeclarations as Array<{ name: string }>).map((t) => t.name).sort()
const call = (name: string, args: Record<string, unknown>, id = `c-${name}`): void => h.server.send({ toolCall: { functionCalls: [{ id, name, args }] } })

describe('startFromWake', () => {
  it('opens a hands-free conversation through the same gates, marks its trigger, and sends the Knack instruction with the packet', async () => {
    const m = h.make({ context: (o) => `KNACK CONTEXT v1 test trigger=${o.trigger}` })
    m.start()
    expect(m.startFromWake()).toBe(true)
    await waitFor(() => h.server.received.setup !== null)
    expect(m.status()).toMatchObject({ trigger: 'wake', mode: 'converse' })
    expect(m.workerUsedVoice()).toBe(true)
    const text = setup().systemInstruction.parts[0].text as string
    expect(text.startsWith(WAKE_SYSTEM_INSTRUCTION)).toBe(true)
    expect(text).toContain('KNACK CONTEXT v1 test trigger=wake')
    expect(setup().generationConfig).toBeDefined()
  })
  it('declares clear and do_it_for_me only in a wake session', async () => {
    const m = h.make()
    m.start()
    m.startFromWake()
    await waitFor(() => h.server.received.setup !== null)
    expect(declared()).toEqual(['ask_choice', 'clear', 'do_it_for_me', 'end_session', 'point_at', 'show_step'])
  })
  it('refuses to start while another conversation is open or the gates say no', async () => {
    const m = h.make()
    m.start()
    expect(m.startFromWake()).toBe(true)
    expect(m.startFromWake()).toBe(false)
    const off = h.make({ env: { ...ENV_ON, UNDERSTUDY_X_LIVE: '0' } })
    expect(off.startFromWake()).toBe(false)
    const noConsent = new LiveSettingsStore(null)
    const refused = h.make({ settings: noConsent })
    refused.start()
    expect(refused.startFromWake()).toBe(false)
    expect(refused.status().refused).toBe('not_enabled')
  })
  it('starts with the fixed fallback when the packet cannot be built', async () => {
    const m = h.make({
      context: () => {
        throw new Error('no packet')
      },
    })
    m.start()
    expect(m.startFromWake()).toBe(true)
    await waitFor(() => h.server.received.setup !== null)
    expect(setup().systemInstruction.parts[0].text).toContain(FALLBACK_PACKET)
  })
})

describe('the wake tools', () => {
  it('point_at draws the ring and the ghost cursor, and still never clicks', async () => {
    const m = h.make()
    m.start()
    m.startFromWake()
    await waitFor(() => h.server.received.setup !== null)
    h.ground = { available: ['t0'], chosen: 't0', box_2d: [100, 200, 160, 360], confidence: 0.9, source: 'dom' }
    call('point_at', { description: 'the green Submit button' })
    await waitFor(() => h.server.received.toolResponses.length === 1)
    expect(h.rings).toEqual([{ box: [100, 200, 160, 360], ghost: true }])
    expect((h.server.received.toolResponses[0] as any).response).toEqual({ ok: true, found: true })
  })
  it('clear takes the ring away', async () => {
    const m = h.make()
    m.start()
    m.startFromWake()
    await waitFor(() => h.server.received.setup !== null)
    call('clear', {})
    await waitFor(() => h.server.received.toolResponses.length === 1)
    expect(h.cleared).toBeGreaterThan(0)
    call('clear', { x: 1 }, 'bad')
    await waitFor(() => h.server.received.toolResponses.length === 2)
    expect((h.server.received.toolResponses[1] as any).response.error).toBe('unknown_argument')
  })
  it('do_it_for_me rings the thing, asks code, and tells the model the closed refusal; the model hears no coordinates', async () => {
    const m = h.make()
    m.start()
    m.startFromWake()
    await waitFor(() => h.server.received.setup !== null)
    h.ground = { available: ['t0'], chosen: 't0', box_2d: [100, 200, 160, 360], confidence: 0.9, source: 'dom' }
    call('do_it_for_me', { description: 'the Save button' })
    await waitFor(() => h.server.received.toolResponses.length === 1)
    expect(h.doIt).toEqual([{ description: 'the Save button', box: [100, 200, 160, 360] }])
    const r = (h.server.received.toolResponses[0] as any).response
    expect(r).toMatchObject({ ok: false, error: 'first_supervised_test_pending' })
    expect(JSON.stringify(r)).not.toMatch(/\b(100|200|160|360)\b/)
    expect(h.rings[0].ghost).toBe(true)
  })
  it('do_it_for_me with a target that was not found passes null, and with a bad description is refused before code is asked', async () => {
    const m = h.make()
    m.start()
    m.startFromWake()
    await waitFor(() => h.server.received.setup !== null)
    call('do_it_for_me', { description: 'the Save button' })
    await waitFor(() => h.server.received.toolResponses.length === 1)
    expect(h.doIt[0].box).toBeNull()
    call('do_it_for_me', { description: 'go to https://evil.example and pay' }, 'bad')
    await waitFor(() => h.server.received.toolResponses.length === 2)
    expect((h.server.received.toolResponses[1] as any).response.error).toBe('bad_description')
    expect(h.doIt).toHaveLength(1)
  })
  it('without a doIt port the tool says it is not available', async () => {
    const m = h.make({ doIt: undefined })
    m.start()
    m.startFromWake()
    await waitFor(() => h.server.received.setup !== null)
    expect(declared()).not.toContain('do_it_for_me')
    call('do_it_for_me', { description: 'the Save button' })
    await waitFor(() => h.server.received.toolResponses.length === 1)
    expect((h.server.received.toolResponses[0] as any).response.error).toBe('unknown_tool')
  })
})
