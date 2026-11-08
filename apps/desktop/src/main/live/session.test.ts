// The session against a local fake Live server: the whole conversation, the limits, the tools, the gates. Time is a manual clock for the
// session's own limits; the websocket is real (loopback). No microphone, no network host, no key.
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { createMemoryLiveLedger, type MemoryLiveLedger } from './ledger'
import { SessionMeter, pricesFromEnv } from './meter'
import { LiveSession, type EndReason, type SessionConfig, type SessionDeps, type SessionSummary } from './session'
import { createToolHost } from './tool-host'
import { chunks32ms, createFakeAudio, fakeCue, manualClock, modelAudio, openVerdict, replyScript, startFakeLiveServer, tonePcm, waitFor, type FakeAudio, type FakeLiveServer, type ManualClock } from './live.test-util'
import type { GateVerdict } from './gates'
import type { LiveFrame } from './egress'
import type { GroundAnswer } from './ports'

const config = (over: Partial<SessionConfig> = {}): SessionConfig => ({
  mode: 'converse',
  model: 'test-live-model',
  voiceName: 'Sulafat',
  systemInstruction: 'You are a test.',
  turnMode: 'vad',
  idleMs: 60_000,
  graceMs: 8000,
  maxMs: 300_000,
  sessionUsd: 0.15,
  dayBaseUsd: 0,
  dailyUsd: 0.5,
  framesEnabled: false,
  frameIntervalMs: 5000,
  silenceTailMs: 700,
  transcriptWaitMs: 3000,
  ...over,
})

interface Harness {
  server: FakeLiveServer
  audio: FakeAudio
  ledger: MemoryLiveLedger
  clock: ManualClock
  meter: SessionMeter
  cue: ReturnType<typeof fakeCue>
  verdict: { audio: GateVerdict; frames: GateVerdict }
  flags: { killed: boolean; acting: boolean }
  rings: Array<[number, number, number, number]>
  frameBytes: Buffer[]
  groundAnswer: GroundAnswer | null
  mints: { n: number }
  mk(over?: Partial<SessionConfig>, deps?: Partial<SessionDeps>): LiveSession
  summary(): SessionSummary | null
  ended: EndReason[]
}

let h: Harness
const sessions: LiveSession[] = []

beforeEach(async () => {
  const server = await startFakeLiveServer()
  const clock = manualClock()
  const audio = createFakeAudio()
  const ledger = createMemoryLiveLedger()
  const cue = fakeCue()
  const verdict = { audio: openVerdict(), frames: openVerdict() }
  const flags = { killed: false, acting: false }
  const rings: Array<[number, number, number, number]> = []
  const frameBytes: Buffer[] = []
  const state = { groundAnswer: null as GroundAnswer | null }
  const ended: EndReason[] = []
  let last: SessionSummary | null = null
  const meter = new SessionMeter(pricesFromEnv({}))
  const mints = { n: 0 }
  h = {
    mints,
    server,
    audio,
    ledger,
    clock,
    meter,
    cue,
    verdict,
    flags,
    rings,
    frameBytes,
    get groundAnswer() {
      return state.groundAnswer
    },
    set groundAnswer(v) {
      state.groundAnswer = v
    },
    ended,
    summary: () => last,
    mk(over = {}, deps = {}) {
      const host = createToolHost({ cue, ground: { ground: async () => state.groundAnswer }, ring: { show: (b) => void rings.push(b), clear: () => undefined } })
      const s = new LiveSession({
        config: config(over),
        tokens: { mint: async () => (mints.n++, { token: 'auth_tokens/TESTTOKEN0123456789', expiresAt: Date.now() + 600_000 }) },
        url: server.url,
        gates: { audio: () => verdict.audio, frames: async () => verdict.frames, start: async () => verdict.audio, stop: () => undefined },
        ledger,
        meter,
        audio,
        tools: host,
        frames: {
          grab: async () => {
            const jpeg = Buffer.from([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3, 4, 5, 6, 7, 8])
            frameBytes.push(jpeg)
            return { jpeg, width: 640, height: 360, release: () => jpeg.fill(0) } as LiveFrame
          },
        },
        agentActing: () => flags.acting,
        killed: () => flags.killed,
        timers: clock,
        now: clock.now,
        ...deps,
      })
      s.onEnded((x) => {
        last = x
        ended.push(x.reason)
      })
      sessions.push(s)
      return s
    },
  }
})

afterEach(async () => {
  for (const s of sessions.splice(0)) s.end('stop')
  await h.server.close()
})

const speak = async (s: LiveSession, seconds = 0.5): Promise<void> => {
  for (const c of chunks32ms(tonePcm(seconds))) h.audio.feed(c)
  await waitFor(() => h.server.received.audio > 0)
}

describe('a conversation', () => {
  it('opens the socket with the token in a header (never in the URL), sends the setup, and does nothing else until the worker speaks', async () => {
    const s = h.mk()
    await s.start()
    expect(h.server.received.authHeader).toBe('Token auth_tokens/TESTTOKEN0123456789')
    expect(h.server.received.url).toBe('/live')
    expect(h.server.url).not.toContain('TESTTOKEN')
    const setup = h.server.received.setup as Record<string, any>
    expect(setup.model).toBe('models/test-live-model')
    expect(setup.generationConfig.thinkingConfig).toBeUndefined()
    expect(setup.inputAudioTranscription).toBeUndefined() // a conversation receives no transcript at all
    expect(setup.outputAudioTranscription).toBeUndefined()
    expect(setup.contextWindowCompression).toEqual({ slidingWindow: {} }) // the test config sets no bound; the manager does
    expect(h.audio.micOpen).toBe(true) // the key is down: the mic is open
    expect(h.server.received.audio).toBe(0)
    expect(h.server.received.video).toBe(0)
  })

  it('sends the microphone only while the key is held, then ends the turn and plays the reply', async () => {
    const s = h.mk()
    await s.start()
    await speak(s)
    const before = h.server.received.audio
    s.release()
    expect(h.audio.micOpen).toBe(false)
    await waitFor(() => h.audio.played.length >= 2)
    // chunks pushed after the release (a late buffer) go nowhere
    for (const c of chunks32ms(tonePcm(0.2))) s.pushMic(c, 0.3)
    await new Promise((r) => setTimeout(r, 30))
    expect(h.server.received.audio).toBeGreaterThanOrEqual(before) // only the silence tail was added
    expect(h.server.received.streamEnds).toBe(1)
    expect(s.phase === 'speaking' || s.phase === 'thinking').toBe(true)
    expect(s.elapsedMs).toBe(0) // the manual clock has not moved
  })

  it('ends after the quiet grace once the key is up and the model has finished', async () => {
    const s = h.mk()
    await s.start()
    await speak(s)
    s.release()
    await waitFor(() => h.audio.played.length >= 2)
    h.audio.idle()
    h.clock.advance(7_000)
    expect(s.isEnded).toBe(false)
    h.clock.advance(2_000)
    expect(h.ended).toEqual(['release_grace'])
    expect(h.audio.flushes).toBeGreaterThan(0)
  })

  it('a second press within the grace is the same conversation, cuts the model off and reopens the microphone', async () => {
    const s = h.mk()
    await s.start()
    await speak(s)
    s.release()
    await waitFor(() => h.audio.played.length >= 2)
    h.clock.advance(3000)
    const flushes = h.audio.flushes
    s.press()
    expect(h.audio.flushes).toBe(flushes + 1)
    expect(h.audio.micStarts).toBe(2)
    expect(s.isEnded).toBe(false)
    expect(h.server.received.connections).toBe(1)
  })

  it('a tap that ends before the renderer finished opening the microphone leaves it closed', async () => {
    h.audio.startDelayMs = 80
    const s = h.mk()
    const started = s.start()
    s.release() // the key is already up
    await started
    await new Promise((r) => setTimeout(r, 150))
    expect(h.audio.micOpen).toBe(false)
    expect(h.audio.micStops).toBeGreaterThanOrEqual(1)
    expect(h.server.received.audioBytes).toBeLessThanOrEqual(22_410) // nothing but the 700 ms of silence that closes the turn
  })

  it('a conversation that ends while the microphone is still opening does not leave it open', async () => {
    h.audio.startDelayMs = 80
    h.flags.killed = false
    const s = h.mk()
    const started = s.start()
    await new Promise((r) => setTimeout(r, 20))
    s.end('stop')
    await started
    await new Promise((r) => setTimeout(r, 150))
    expect(h.audio.micOpen).toBe(false)
  })

  it('ends a held key that makes no sound after the idle limit', async () => {
    const s = h.mk({ idleMs: 60_000 })
    await s.start()
    h.clock.advance(59_000)
    expect(s.isEnded).toBe(false)
    h.clock.advance(2_000)
    expect(h.ended).toEqual(['idle'])
  })

  it('a held key with sound stays alive past the idle limit, but never past the hard cap', async () => {
    const s = h.mk({ idleMs: 10_000, maxMs: 30_000 })
    await s.start()
    for (let t = 0; t < 24; t++) {
      s.pushMic(chunks32ms(tonePcm(0.05))[0]!, 0.3)
      h.clock.advance(1000)
    }
    expect(s.isEnded).toBe(false)
    h.clock.advance(10_000)
    expect(h.ended).toEqual(['max_duration'])
  })

  it('the hard cap is five minutes by default', async () => {
    const s = h.mk()
    await s.start()
    for (let t = 0; t < 299; t++) {
      s.pushMic(chunks32ms(tonePcm(0.05))[0]!, 0.3)
      h.clock.advance(1000)
    }
    expect(s.isEnded).toBe(false)
    h.clock.advance(2000)
    expect(h.ended).toEqual(['max_duration'])
  })

  it('stops on the kill switch and when an agent starts acting', async () => {
    const a = h.mk()
    await a.start()
    h.flags.killed = true
    h.clock.advance(300)
    expect(h.ended).toEqual(['killed'])
    h.flags.killed = false
    const b = h.mk()
    await b.start()
    h.flags.acting = true
    h.clock.advance(300)
    expect(h.ended).toEqual(['killed', 'agent_acting'])
  })

  it('does not even connect when the gate is closed at the start (unattended, private app, no consent)', async () => {
    h.verdict.audio = openVerdict({ open: false, reason: 'unattended' })
    const s = h.mk()
    await s.start()
    expect(h.ended).toEqual(['unattended'])
    expect(h.server.received.connections).toBe(0)
    expect(h.audio.micStarts).toBe(0)
  })

  it('a private app coming to the front mid-conversation stops what leaves, without ending it; an unattended gate ends it', async () => {
    const s = h.mk()
    await s.start()
    const notices: string[] = []
    s.onNotice((n) => notices.push(`${n.kind}:${n.reason}`))
    await speak(s, 0.2)
    const sent = h.server.received.audio
    h.verdict.audio = openVerdict({ open: false, reason: 'denylisted_app' })
    for (const c of chunks32ms(tonePcm(0.3))) h.audio.feed(c)
    await new Promise((r) => setTimeout(r, 30))
    expect(h.server.received.audio).toBe(sent)
    expect(notices).toEqual(['blocked:denylisted_app']) // one notice, not one per chunk
    expect(s.isEnded).toBe(false)
    h.verdict.audio = openVerdict({ open: false, reason: 'unattended' })
    h.audio.feed(chunks32ms(tonePcm(0.05))[0]!)
    expect(h.ended).toEqual(['unattended'])
  })

  it('falls back cleanly when the connection cannot be made', async () => {
    const s = h.mk({}, { url: 'ws://127.0.0.1:1/live' })
    await s.start()
    expect(h.ended).toEqual(['error'])
    expect(h.audio.micOpen).toBe(false)
  })

  it('a microphone that cannot be opened ends the session without a socket staying open', async () => {
    h.audio.failMic = 'permission'
    const s = h.mk()
    const notices: string[] = []
    s.onNotice((n) => notices.push(`${n.kind}:${n.reason}`))
    await s.start()
    expect(h.ended).toEqual(['mic_unavailable'])
    expect(notices).toContain('mic:permission')
  })

  it('a dropped socket is resumed once; a socket that cannot come back ends the session as connection_lost', async () => {
    const s = h.mk()
    await s.start()
    h.server.send({ sessionResumptionUpdate: { newHandle: 'h1', resumable: true } })
    await new Promise((r) => setTimeout(r, 20))
    h.server.drop()
    await waitFor(() => h.server.received.connections === 2, 4000)
    expect(s.isEnded).toBe(false)
    h.server.refuseAll = true
    h.server.drop()
    await waitFor(() => h.ended.length === 1, 8000)
    expect(h.ended).toEqual(['connection_lost'])
  })
})

describe('money', () => {
  it('meters audio and the server usage report, and ends at the per-conversation cap', async () => {
    const s = h.mk({ sessionUsd: 0.0005 })
    await s.start()
    await speak(s, 1)
    s.release()
    await waitFor(() => h.meter.turns >= 1)
    expect(h.meter.audioInSeconds).toBeGreaterThan(1)
    expect(h.meter.audioOutSeconds).toBeGreaterThan(0.5)
    expect(h.meter.usd()).toBeGreaterThan(0)
    h.clock.advance(300)
    expect(h.ended).toEqual(['cost_session'])
    expect(h.summary()?.usd).toBeGreaterThan(0)
  })

  it('stops uploading the moment the cap is reached, before the next tick', async () => {
    const s = h.mk({ sessionUsd: 0.00002 }) // about a quarter of a second of audio at the assumed price
    await s.start()
    const chunks = chunks32ms(tonePcm(2))
    for (const c of chunks.slice(0, 40)) h.audio.feed(c)
    await waitFor(() => h.server.received.audio > 0)
    await new Promise((r) => setTimeout(r, 50))
    const sent = h.server.received.audio
    expect(sent).toBeGreaterThan(0)
    expect(sent).toBeLessThan(15) // 40 chunks were offered; the cap stopped it, including the chunks that waited for the ledger
  })

  it('the day cap counts what earlier conversations spent', async () => {
    const s = h.mk({ dayBaseUsd: 0.49999, dailyUsd: 0.5 })
    await s.start()
    await speak(s, 1)
    h.clock.advance(300)
    expect(h.ended).toEqual(['cost_day'])
  })
})

describe('tools', () => {
  const call = (name: string, args: Record<string, unknown>, id = `c-${name}`): void =>
    h.server.send({ toolCall: { functionCalls: [{ id, name, args }] } })

  it('declares only the four tools, with the candidate ids as the only allowed step ids', async () => {
    const s = h.mk()
    await s.start()
    const tools = (h.server.received.setup as any).tools[0].functionDeclarations as Array<{ name: string; parameters?: any }>
    expect(tools.map((t) => t.name).sort()).toEqual(['ask_choice', 'end_session', 'point_at', 'show_step'])
    expect(tools.find((t) => t.name === 'show_step')!.parameters.properties.step_id.enum).toEqual(['read_case', 'calc_a', 'cliff_a'])
  })

  it('a tool call that finishes before the outgoing channel exists is answered once it does, not dropped', async () => {
    h.audio.startDelayMs = 400 // the renderer is slow to open the microphone, so the channel is not there yet
    const s = h.mk()
    void s.start()
    await waitFor(() => h.server.received.setup !== null)
    call('point_at', { description: 'the green Submit button' }, 'early')
    await new Promise((r) => setTimeout(r, 150))
    expect(h.server.received.toolResponses).toHaveLength(0) // nothing could be sent yet
    expect(h.audio.micOpen).toBe(false)
    await waitFor(() => h.server.received.toolResponses.length === 1)
    expect((h.server.received.toolResponses[0] as any).id ?? JSON.stringify(h.server.received.toolResponses[0])).toContain('early')
    expect(s.isEnded).toBe(false)
  })

  it('a reply that was waiting is dropped with a session that ends first', async () => {
    h.audio.startDelayMs = 400
    const s = h.mk()
    void s.start()
    await waitFor(() => h.server.received.setup !== null)
    call('point_at', { description: 'the green Submit button' }, 'late')
    await new Promise((r) => setTimeout(r, 100))
    s.end('stop')
    await new Promise((r) => setTimeout(r, 500))
    expect(h.server.received.toolResponses).toHaveLength(0)
  })

  it('point_at: found only when the grounder chose the description with confidence and a sane box; the model never hears coordinates', async () => {
    const s = h.mk()
    await s.start()
    h.groundAnswer = { available: ['t0'], chosen: 't0', box_2d: [100, 200, 160, 360], confidence: 0.9, source: 'dom' }
    call('point_at', { description: 'the green Submit button' })
    await waitFor(() => h.server.received.toolResponses.length === 1)
    const r = h.server.received.toolResponses[0] as any
    expect(r.response).toEqual({ ok: true, found: true })
    expect(JSON.stringify(r)).not.toMatch(/\b(100|200|160|360)\b/)
    expect(h.rings).toEqual([[100, 200, 160, 360]])
    // not found: chose another menu entry, low confidence, absurd box
    h.groundAnswer = { available: [], chosen: 't1', box_2d: [100, 200, 160, 360], confidence: 0.9, source: 'vision' }
    call('point_at', { description: 'the red Cancel button' }, 'c2')
    h.groundAnswer = null
    await waitFor(() => h.server.received.toolResponses.length === 2)
    expect((h.server.received.toolResponses[1] as any).response).toEqual({ ok: true, found: false })
    expect(h.rings.length).toBe(1)
  })

  it('refuses unknown tools, unknown arguments, ids outside the closed list, and bad descriptions, and tells the model so', async () => {
    const s = h.mk()
    await s.start()
    call('click_at', { x: 1, y: 2 }, 'a')
    call('point_at', { description: 'the button', url: 'https://evil.example' }, 'b')
    call('show_step', { step_id: 'delete_everything' }, 'c')
    call('ask_choice', { options: ['read_case', 'nope'] }, 'd')
    call('point_at', { description: 'email me at a@b.com' }, 'e')
    call('end_session', { now: true }, 'f')
    await waitFor(() => h.server.received.toolResponses.length === 6)
    const byId = Object.fromEntries(h.server.received.toolResponses.map((r: any) => [r.id, r.response]))
    expect(byId.a.error).toBe('unknown_tool')
    expect(byId.b.error).toBe('unknown_argument')
    expect(byId.c.error).toBe('not_a_listed_step')
    expect(byId.d.error).toBe('not_a_listed_step')
    expect(byId.e.error).toBe('bad_description')
    expect(byId.f.error).toBe('unknown_argument')
    expect(h.cue.shown).toEqual([])
    expect(h.cue.asked).toEqual([])
    expect(h.rings).toEqual([])
    expect(s.isEnded).toBe(false)
  })

  it('show_step returns the pack chip; ask_choice opens the card; the answer is told to the model by its pack label', async () => {
    const s = h.mk()
    await s.start()
    call('show_step', { step_id: 'calc_a' }, 'a')
    call('ask_choice', { options: ['read_case', 'cliff_a'] }, 'b')
    await waitFor(() => h.server.received.toolResponses.length === 2)
    expect(h.cue.shown).toEqual(['calc_a'])
    expect(h.cue.asked).toEqual([['read_case', 'cliff_a']])
    const a = h.server.received.toolResponses.find((r: any) => r.id === 'a') as any
    expect(a.response).toEqual({ ok: true, shown: true, chip: 'Next: Run calculator A' })
    s.noteAnswer('cliff_a')
    await waitFor(() => h.server.received.text.length === 1)
    expect(h.server.received.text[0]).toBe('The worker chose: Check cliff edges (A)')
  })

  it('end_session ends the conversation after the model finishes its goodbye', async () => {
    const s = h.mk()
    await s.start()
    call('end_session', {})
    await waitFor(() => h.server.received.toolResponses.length === 1)
    h.server.send({ serverContent: { modelTurn: { parts: [{ inlineData: { mimeType: 'audio/pcm;rate=24000', data: modelAudio(300) } }] } } })
    h.server.send({ serverContent: { turnComplete: true } })
    await waitFor(() => h.audio.played.length === 1)
    expect(s.isEnded).toBe(false) // still playing the farewell
    h.audio.idle()
    h.clock.advance(400)
    expect(h.ended).toEqual(['goodbye'])
  })
})

describe('frames', () => {
  it('sends one frame at most every five seconds, a ledger row before each, and none when the gate or the ledger says no', async () => {
    const s = h.mk({ framesEnabled: true, frameIntervalMs: 1000 }) // asks for 1 s; the code holds it to 5 s
    await s.start()
    await waitFor(() => h.server.received.video === 1)
    expect(h.ledger.announced.length).toBe(1)
    expect(h.ledger.announced[0]).toMatchObject({ count: 1, width: 640, height: 360, model: 'test-live-model' })
    expect(h.ledger.announced[0]!.sha8).toMatch(/^[0-9a-f]{16}$/)
    h.clock.advance(2000)
    h.clock.advance(2000)
    await new Promise((r) => setTimeout(r, 30))
    expect(h.server.received.video).toBe(1)
    h.clock.advance(1500)
    await waitFor(() => h.server.received.video === 2)
    // the engine refuses: the frame stays home, the conversation carries on
    h.ledger.refuse('no_consent')
    h.clock.advance(5000)
    await waitFor(() => h.ledger.announced.length === 3)
    await new Promise((r) => setTimeout(r, 30))
    expect(h.server.received.video).toBe(2)
    expect(s.isEnded).toBe(false)
    // every captured frame buffer was zeroed after use
    expect(h.frameBytes.length).toBeGreaterThanOrEqual(3)
    for (const b of h.frameBytes) expect(b.every((x) => x === 0)).toBe(true)
  })

  it('takes no frame at all while the gate is closed for frames (a private app in front)', async () => {
    h.verdict.frames = openVerdict({ open: false, reason: 'denylisted_app' })
    const s = h.mk({ framesEnabled: true })
    await s.start()
    h.clock.advance(6000)
    await new Promise((r) => setTimeout(r, 30))
    expect(h.frameBytes.length).toBe(0)
    expect(h.ledger.announced.length).toBe(0)
    expect(h.server.received.video).toBe(0)
  })

  it('sends no frames unless the worker turned frames on', async () => {
    const s = h.mk({ framesEnabled: false })
    await s.start()
    h.clock.advance(20_000)
    await new Promise((r) => setTimeout(r, 30))
    expect(h.server.received.video).toBe(0)
    expect(h.frameBytes.length).toBe(0)
    void s
  })
})

describe('audio ledger rows', () => {
  it('writes one row per worker turn BEFORE any audio of it is sent, and completes it with seconds and bytes', async () => {
    const order: string[] = []
    const origAnnounce = h.ledger.announceAudio!.bind(h.ledger)
    h.ledger.announceAudio = async (t) => {
      order.push(`announce(received=${h.server.received.audio})`)
      return origAnnounce(t)
    }
    const s = h.mk()
    await s.start()
    await speak(s, 0.4)
    s.release()
    await waitFor(() => h.ledger.audioResults.length === 1)
    expect(order).toEqual(['announce(received=0)']) // the first turn was announced at the press, before a byte of it was sent
    expect(h.ledger.audioAnnounced).toHaveLength(1)
    expect(h.ledger.audioAnnounced[0]).toMatchObject({ model: 'test-live-model', turn: 'converse', gate: { consent: true, unattended: false } })
    const r = h.ledger.audioResults[0]!.result
    expect(r.seconds).toBeGreaterThan(0.4)
    expect(r.bytes).toBeGreaterThan(10_000)
    // a second press is a second turn
    s.press()
    await speak(s, 0.2)
    s.release()
    await waitFor(() => h.ledger.audioAnnounced.length === 2 && h.ledger.audioResults.length === 2)
  })

  it('opens NOTHING when the ledger route is missing or unreachable: no microphone, no token, no socket', async () => {
    h.ledger.refuse('ledger_unavailable')
    const s = h.mk()
    const notices: string[] = []
    s.onNotice((n) => notices.push(`${n.kind}:${n.reason}`))
    await s.start()
    expect(h.ended).toEqual(['blocked'])
    expect(notices).toEqual(['ledger:ledger_unavailable'])
    expect(h.audio.micStarts).toBe(0)
    expect(h.mints.n).toBe(0)
    expect(h.server.received.connections).toBe(0)
    expect(h.server.received.audio).toBe(0)
  })

  it('a ledger that throws is the same as a ledger that is missing', async () => {
    h.ledger.announceAudio = async () => {
      throw new Error('engine down')
    }
    const s = h.mk()
    await s.start()
    expect(h.ended).toEqual(['blocked'])
    expect(h.server.received.connections).toBe(0)
    expect(h.audio.micStarts).toBe(0)
  })

  it('the first turn is announced at the key press, before the socket opens, and completed as not sent if the connection never came up', async () => {
    const order: string[] = []
    const orig = h.ledger.announceAudio.bind(h.ledger)
    h.ledger.announceAudio = async (t) => {
      order.push(`announce(connections=${h.server.received.connections})`)
      return orig(t)
    }
    const s = h.mk({}, { url: 'ws://127.0.0.1:1/live' })
    await s.start()
    expect(order).toEqual(['announce(connections=0)'])
    expect(h.ended).toEqual(['error'])
    await waitFor(() => h.ledger.audioResults.length === 1)
    expect(h.ledger.audioResults[0]!.result).toMatchObject({ ok: false, seconds: 0, bytes: 0 })
  })

  it('an unattended refusal from the ledger ends it as unattended', async () => {
    h.ledger.refuse('unattended')
    const s = h.mk()
    await s.start()
    expect(h.ended).toEqual(['unattended'])
    expect(h.server.received.connections).toBe(0)
  })

  it('the audio ledger rows hold no content: only the model, the gate booleans and the turn kind', async () => {
    const s = h.mk()
    await s.start()
    await speak(s, 0.2)
    s.release()
    await waitFor(() => h.ledger.audioResults.length === 1)
    expect(Object.keys(h.ledger.audioAnnounced[0]!).sort()).toEqual(['gate', 'model', 'turn'])
    expect(Object.keys(h.ledger.audioResults[0]!.result).sort()).toEqual(['bytes', 'latency_ms', 'ok', 'seconds'])
  })
})

describe('transcribe mode (Cue listens once)', () => {
  it('returns what was heard and ends; no tools are declared, nothing is played', async () => {
    h.server.onTurnEnd = (srv) => {
      srv.send({ serverContent: { inputTranscription: { text: 'the second' } } })
      srv.send({ serverContent: { inputTranscription: { text: ' one', finished: true } } })
      srv.send({ serverContent: { turnComplete: true } })
    }
    const s = h.mk({ mode: 'transcribe', graceMs: 3000, transcriptWaitMs: 3000 })
    await s.start()
    await speak(s, 0.3)
    s.release()
    await waitFor(() => s.phase === 'waiting')
    await new Promise((r) => setTimeout(r, 30))
    h.clock.advance(300)
    expect(h.ended).toEqual(['transcript'])
    expect(h.summary()?.transcript).toBe('the second one')
    expect((h.server.received.setup as any).tools).toBeUndefined()
    expect((h.server.received.setup as any).inputAudioTranscription).toEqual({})
    expect(h.audio.played).toEqual([])
    expect(h.ledger.audioAnnounced[0]?.turn).toBe('transcribe')
  })

  it('returns null when nothing was heard', async () => {
    h.server.onTurnEnd = () => undefined
    const s = h.mk({ mode: 'transcribe' })
    await s.start()
    await speak(s, 0.1)
    s.release()
    h.clock.advance(3500)
    expect(h.ended).toEqual(['transcript'])
    expect(h.summary()?.transcript).toBeNull()
  })

  it('the transcript is not kept after the summary is delivered (it lives in memory for the turn only)', async () => {
    h.server.onTurnEnd = (srv) => srv.send({ serverContent: { inputTranscription: { text: 'number two', finished: true } } })
    const s = h.mk({ mode: 'transcribe' })
    await s.start()
    await speak(s, 0.1)
    s.release()
    await new Promise((r) => setTimeout(r, 30))
    h.clock.advance(400)
    expect(h.ended).toEqual(['transcript'])
    expect(JSON.stringify(s)).not.toContain('number two')
  })
})

describe('turn latency bookkeeping', () => {
  it('records the time from the key release to the first model audio, per answered turn', async () => {
    h.server.onTurnEnd = (srv) => replyScript(srv)
    const s = h.mk()
    await s.start()
    await speak(s)
    s.release()
    await waitFor(() => (h.summary() ?? { ttfaMs: [] }).ttfaMs.length === 0 && h.audio.played.length >= 1)
    s.end('stop')
    expect(h.summary()?.ttfaMs.length).toBe(1)
    expect(h.summary()?.ttfaMs[0]).toBeGreaterThanOrEqual(0)
    expect(h.summary()?.ttfrMs.length).toBe(1)
  })

  it('counts a tool call as the first response of a turn that was answered without a word', async () => {
    h.server.onTurnEnd = (srv) => {
      srv.send({ toolCall: { functionCalls: [{ id: 'p1', name: 'show_step', args: { step_id: 'calc_a' } }] } })
      srv.send({ serverContent: { turnComplete: true } })
    }
    const s = h.mk()
    await s.start()
    await speak(s)
    s.release()
    await waitFor(() => h.server.received.toolResponses.length === 1)
    s.end('stop')
    expect(h.summary()?.ttfaMs).toEqual([])
    expect(h.summary()?.ttfrMs.length).toBe(1)
    expect(h.summary()?.tools).toEqual([{ name: 'show_step', ok: true }])
    expect((h.server.received.toolResponses[0] as any).scheduling).toBe('WHEN_IDLE')
  })
})
