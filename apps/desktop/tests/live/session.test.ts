import { afterEach, describe, expect, it, vi } from 'vitest'
import { LiveSession, type LiveSessionOptions } from '../../src/renderer/live/LiveSession'
import type { LiveEndReason, ToolCallRequest } from '../../src/renderer/live/types'
import { FakeMic, FakeSpeaker, FakeWebSocket, headerJpeg, tick } from './fakes'

type Rec = { ended: LiveEndReason[]; phases: string[]; transcripts: Array<{ role: string; text: string; final: boolean }>; errors: string[]; metrics: unknown[] }

async function boot(over: Partial<LiveSessionOptions> = {}, start: Parameters<LiveSession['start']>[0] = { voiceName: 'Charon' }) {
  FakeWebSocket.reset()
  FakeWebSocket.autoSetup = true
  FakeWebSocket.failOpen = false
  const mic = new FakeMic()
  const speaker = new FakeSpeaker()
  const session = new LiveSession({
    host: { getAuth: async () => ({ kind: 'token', value: 'tok' }), systemInstruction: async () => 'SYSTEM' },
    audioIn: mic,
    audioOut: speaker,
    model: 'gemini-3.8-live',
    idleTimeoutMs: 0,
    WebSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
    toolHandler: async () => ({ ok: true }),
    ...over,
  })
  const rec: Rec = { ended: [], phases: [], transcripts: [], errors: [], metrics: [] }
  session.on('ended', (e) => rec.ended.push(e.reason))
  session.on('state', (s) => rec.phases.push(s.phase))
  session.on('transcript', (t) => rec.transcripts.push(t))
  session.on('error', (e) => rec.errors.push(e.message))
  session.on('metrics', (m) => rec.metrics.push(m))
  await session.start(start)
  return { session, mic, speaker, rec, ws: () => FakeWebSocket.instances.at(-1)! }
}

const audioEvent = { serverContent: { modelTurn: { parts: [{ inlineData: { data: 'AAAA', mimeType: 'audio/pcm;rate=24000' } }] } } }

afterEach(() => {
  vi.useRealTimers()
})

describe('LiveSession lifecycle', () => {
  it('sends a setup with compression, resumption, transcription and the persona voice + instruction', async () => {
    const { ws, session } = await boot()
    const setup = ws().setups[0]!
    expect(setup.contextWindowCompression).toEqual({ slidingWindow: {} })
    expect(setup.sessionResumption).toEqual({})
    expect(JSON.stringify(setup.systemInstruction)).toContain('SYSTEM')
    expect(JSON.stringify(setup.generationConfig)).toContain('Charon')
    expect(session.phase).toBe('live')
    await session.stop()
  })

  it('stop() ends exactly once, releases mic and speaker, and closes the socket', async () => {
    const { session, mic, speaker, rec, ws } = await boot()
    await session.stop('stop')
    await session.stop('stop')
    expect(rec.ended).toEqual(['stop'])
    expect(mic.stopped).toBe(true)
    expect(speaker.closed).toBe(true)
    expect(ws().readyState).toBe(3)
    expect(session.phase).toBe('ended')
  })

  it('fails start() with a fatal error and ends when the socket closes before setup', async () => {
    FakeWebSocket.reset()
    FakeWebSocket.autoSetup = false
    const mic = new FakeMic()
    const session = new LiveSession({
      host: { getAuth: async () => ({ kind: 'token', value: 't' }), systemInstruction: async () => 'S' },
      audioIn: mic,
      audioOut: new FakeSpeaker(),
      model: 'm',
      WebSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
    })
    const ended: string[] = []
    const errors: string[] = []
    session.on('ended', (e) => ended.push(e.reason))
    session.on('error', (e) => errors.push(e.message))
    const p = session.start({ voiceName: 'Charon' }).catch((e: Error) => e)
    await tick(5)
    FakeWebSocket.instances[0]!.close(1007, 'Thinking level is not supported for this model.')
    const err = await p
    expect(String(err)).toContain('1007')
    expect(ended).toEqual(['error'])
    expect(errors[0]).toContain('Thinking level')
    expect(mic.stopped).toBe(true)
  })
})

describe('chat (text mode and missing microphone)', () => {
  it('textOnly sessions never open the mic, never play the model voice, and answer typed turns as chat transcripts', async () => {
    const { session, mic, speaker, ws, rec } = await boot({}, { voiceName: 'Charon', textOnly: true })
    expect(mic.starts).toBe(0)
    expect(session.isTextMode).toBe(true)
    expect(session.sendUserText('how do I make text bigger?')).toBe(true)
    expect(ws().realtime.at(-1)).toEqual({ text: 'how do I make text bigger?' })
    ws().serverSend(audioEvent)
    ws().serverSend({ serverContent: { outputTranscription: { text: 'Open Settings, then Display.' } } })
    ws().serverSend({ serverContent: { generationComplete: true } })
    expect(speaker.played).toEqual([]) // muted
    // Final at generationComplete (turnComplete would trail by the length of the speech nobody is playing).
    expect(rec.transcripts.at(-1)).toEqual({ role: 'assistant', text: 'Open Settings, then Display.', final: true })
    expect(session.phase).toBe('live')
    await session.stop()
  })

  it('micOptional keeps the session alive when the microphone is blocked, and typing still works', async () => {
    FakeWebSocket.reset()
    const mic = new FakeMic()
    mic.failStart = true
    const session = new LiveSession({
      host: { getAuth: async () => ({ kind: 'token', value: 't' }), systemInstruction: async () => 'S' },
      audioIn: mic,
      audioOut: new FakeSpeaker(),
      model: 'm',
      idleTimeoutMs: 0,
      WebSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
    })
    const notices: string[] = []
    session.on('notice', (n) => notices.push(n.kind))
    await session.start({ voiceName: 'Charon', micOptional: true })
    expect(notices).toEqual(['mic_unavailable'])
    expect(session.phase).toBe('live')
    expect(session.sendUserText('hello')).toBe(true)
    expect(FakeWebSocket.instances[0]!.realtime.at(-1)).toEqual({ text: 'hello' })
    await session.stop()
  })

  it('without micOptional a blocked microphone is a start failure', async () => {
    FakeWebSocket.reset()
    const mic = new FakeMic()
    mic.failStart = true
    const session = new LiveSession({
      host: { getAuth: async () => ({ kind: 'token', value: 't' }), systemInstruction: async () => 'S' },
      audioIn: mic,
      audioOut: new FakeSpeaker(),
      model: 'm',
      WebSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
    })
    await expect(session.start({ voiceName: 'Charon' })).rejects.toThrow(/Permission denied/)
  })

  it('switching to text mode releases the mic and mutes playback; switching back reopens the mic', async () => {
    const { session, mic, speaker, ws } = await boot()
    expect(mic.starts).toBe(1)
    await session.setTextMode(true)
    expect(mic.stopped).toBe(true)
    expect(ws().realtime.at(-1)).toEqual({ audioStreamEnd: true })
    ws().serverSend(audioEvent)
    expect(speaker.played).toEqual([])
    await session.setTextMode(false)
    expect(mic.starts).toBe(2)
    expect(session.isTextMode).toBe(false)
    ws().serverSend({ serverContent: { turnComplete: true } })
    ws().serverSend(audioEvent)
    expect(speaker.played).toEqual(['AAAA'])
    await session.stop()
  })

  it('typed turns count as learner activity for the idle timer', async () => {
    vi.useFakeTimers()
    const { session, rec } = await boot({ idleTimeoutMs: 20_000 })
    await vi.advanceTimersByTimeAsync(15_000)
    session.sendUserText('still here')
    await vi.advanceTimersByTimeAsync(15_000)
    expect(rec.ended).toEqual([])
    await vi.advanceTimersByTimeAsync(10_000)
    expect(rec.ended).toEqual(['idle'])
  })
})

describe('stop while connecting', () => {
  const make = (systemInstruction: () => Promise<string>) => {
    FakeWebSocket.reset()
    FakeWebSocket.autoSetup = false
    FakeWebSocket.failOpen = false
    const mic = new FakeMic()
    const session = new LiveSession({
      host: { getAuth: async () => ({ kind: 'token', value: 't' }), systemInstruction },
      audioIn: mic,
      audioOut: new FakeSpeaker(),
      model: 'm',
      WebSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
    })
    const errors: string[] = []
    const ended: string[] = []
    session.on('error', (e) => errors.push(e.message))
    session.on('ended', (e) => ended.push(e.reason))
    return { session, mic, errors, ended }
  }

  it('before the socket exists: opens no socket and no mic, start() resolves quietly', async () => {
    const { session, mic, errors, ended } = make(async () => {
      await tick(20)
      return 'S'
    })
    const p = session.start({ voiceName: 'Charon' })
    await session.stop('stop')
    await p
    expect(FakeWebSocket.instances).toHaveLength(0)
    expect(mic.push).toBeNull()
    expect(errors).toEqual([])
    expect(ended).toEqual(['stop'])
  })

  it('while the socket is opening: closes it and does not report an error', async () => {
    const { session, mic, errors, ended } = make(async () => 'S')
    const p = session.start({ voiceName: 'Charon' })
    await tick(5)
    await session.stop('stop')
    await p
    expect(FakeWebSocket.instances[0]!.readyState).toBe(3)
    expect(mic.stopped).toBe(true)
    expect(errors).toEqual([])
    expect(ended).toEqual(['stop'])
  })
})

describe('audio in/out', () => {
  it('forwards mic chunks as 16 kHz PCM realtime audio and drops them while muted (with audioStreamEnd)', async () => {
    const { session, mic, ws } = await boot()
    mic.push!('QUJD', 0.1)
    session.setMicMuted(true)
    mic.push!('WFla', 0.1)
    session.setMicMuted(false)
    mic.push!('REVG', 0.1)
    const rt = ws().realtime
    expect(rt[0]).toEqual({ audio: { data: 'QUJD', mimeType: 'audio/pcm;rate=16000' } })
    expect(rt[1]).toEqual({ audioStreamEnd: true })
    expect(rt[2]).toEqual({ audio: { data: 'REVG', mimeType: 'audio/pcm;rate=16000' } })
    await session.stop()
  })

  it('buffers mic chunks captured while connecting, or uses the spotter pre-roll instead of them', async () => {
    for (const withPreRoll of [false, true]) {
      FakeWebSocket.reset()
      FakeWebSocket.autoSetup = false
      const mic = new FakeMic()
      const session = new LiveSession({
        host: { getAuth: async () => ({ kind: 'token', value: 't' }), systemInstruction: async () => 'S' },
        audioIn: mic,
        audioOut: new FakeSpeaker(),
        model: 'm',
        idleTimeoutMs: 0,
        WebSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
      })
      const p = session.start({ voiceName: 'Charon', takePreRoll: withPreRoll ? () => ['R1', 'R2'] : undefined })
      await tick(5)
      mic.push!('P1', 0.1)
      FakeWebSocket.instances[0]!.serverSend({ setupComplete: {} })
      await p
      const data = FakeWebSocket.instances[0]!.realtime.map((r) => (r.audio as { data: string }).data)
      expect(data).toEqual(withPreRoll ? ['R1', 'R2'] : ['P1'])
      await session.stop()
    }
  })

  it('plays model audio, shows speaking, and flushes instantly on interrupted', async () => {
    const { ws, speaker, rec, session } = await boot()
    ws().serverSend(audioEvent)
    expect(speaker.played).toEqual(['AAAA'])
    expect(session.phase).toBe('speaking')
    ws().serverSend({ serverContent: { interrupted: true } })
    expect(speaker.flushes).toBe(1)
    expect(session.phase).toBe('live')
    expect(rec.phases).toContain('speaking')
    await session.stop()
  })

  it('returns to live only after playback drains following turnComplete', async () => {
    const { ws, speaker, session } = await boot()
    ws().serverSend(audioEvent)
    ws().serverSend({ serverContent: { turnComplete: true } })
    expect(session.phase).toBe('speaking') // still playing the queue
    speaker.drain()
    expect(session.phase).toBe('live')
    await session.stop()
  })

  it('reports time-to-first-audio from the last voiced mic chunk', async () => {
    const { ws, mic, rec, session } = await boot()
    mic.push!('QQ==', 0.2)
    await tick(20)
    ws().serverSend(audioEvent)
    const ttfa = rec.metrics.find((m) => (m as { kind: string }).kind === 'ttfa') as { ms: number; trigger: string }
    expect(ttfa.trigger).toBe('voice')
    expect(ttfa.ms).toBeGreaterThanOrEqual(15)
    await session.stop()
  })
})

describe('transcripts', () => {
  it('emits cumulative text per turn and finalizes on turnComplete', async () => {
    const { ws, rec, session } = await boot()
    ws().serverSend({ serverContent: { inputTranscription: { text: 'show me ' } } })
    ws().serverSend({ serverContent: { inputTranscription: { text: 'the button' } } })
    ws().serverSend({ serverContent: { outputTranscription: { text: 'Sure, ' } } })
    ws().serverSend({ serverContent: { outputTranscription: { text: 'look here.' } } })
    ws().serverSend({ serverContent: { turnComplete: true } })
    const user = rec.transcripts.filter((t) => t.role === 'user')
    const model = rec.transcripts.filter((t) => t.role === 'assistant')
    expect(user.map((t) => t.text)).toEqual(['show me ', 'show me the button', 'show me the button'])
    expect(user.at(-1)!.final).toBe(true)
    expect(model.map((t) => t.text)).toEqual(['Sure, ', 'Sure, look here.', 'Sure, look here.'])
    expect(model.at(-1)!.final).toBe(true)
    await session.stop()
  })

  it('finalizes the assistant line when interrupted', async () => {
    const { ws, rec, session } = await boot()
    ws().serverSend({ serverContent: { outputTranscription: { text: 'First, open' } } })
    ws().serverSend({ serverContent: { interrupted: true } })
    expect(rec.transcripts.at(-1)).toEqual({ role: 'assistant', text: 'First, open', final: true })
    await session.stop()
  })
})

describe('tools', () => {
  it('answers each call in its own task with a top-level scheduling and never blocks the receive path', async () => {
    let releaseSlow: () => void = () => undefined
    const handler = vi.fn(async (call: ToolCallRequest) => {
      if (call.id === 'slow') await new Promise<void>((r) => (releaseSlow = r))
      return call.name === 'point_at' ? { found: true, confidence: 0.9 } : { ok: true }
    })
    const { ws, session } = await boot({ toolHandler: handler })
    ws().serverSend({ toolCall: { functionCalls: [{ id: 'slow', name: 'verify_step', args: { expected_outcome: 'x' } }, { id: 'fast', name: 'point_at', args: { target: 'btn' } }] } })
    await tick(5)
    // The fast call is answered while the slow one is still running, and audio keeps flowing meanwhile.
    ws().serverSend(audioEvent)
    expect(ws().toolResponses).toEqual([{ id: 'fast', name: 'point_at', response: { found: true, confidence: 0.9 }, scheduling: 'SILENT' }])
    releaseSlow()
    await tick(5)
    expect(ws().toolResponses.map((r) => r.id)).toEqual(['fast', 'slow'])
    expect(ws().toolResponses[1]).toMatchObject({ scheduling: 'WHEN_IDLE' })
    await session.stop()
  })

  it('turns handler failures into an { error } response instead of leaving the model hanging', async () => {
    const { ws, session } = await boot({ toolHandler: async () => Promise.reject(new Error('grounder offline')) })
    ws().serverSend({ toolCall: { functionCalls: [{ id: 'a', name: 'point_at', args: { target: 't' } }] } })
    await tick(5)
    expect(ws().toolResponses[0]).toMatchObject({ id: 'a', response: { error: 'grounder offline' }, scheduling: 'WHEN_IDLE' })
    await session.stop()
  })

  it('does not set scheduling on the blocking ask_user_confirm response', async () => {
    const { ws, session } = await boot({ toolHandler: async () => ({ choice: 'Yes' }) })
    ws().serverSend({ toolCall: { functionCalls: [{ id: 'c', name: 'ask_user_confirm', args: {} }] } })
    await tick(5)
    expect(ws().toolResponses[0]).toEqual({ id: 'c', name: 'ask_user_confirm', response: { choice: 'Yes' } })
    await session.stop()
  })

  it('aborts a cancelled call and sends no response for it', async () => {
    let aborted = false
    const { ws, session } = await boot({
      toolHandler: (_c, signal) =>
        new Promise((_res, rej) => {
          signal.addEventListener('abort', () => {
            aborted = true
            rej(new Error('cancelled'))
          })
        }),
    })
    ws().serverSend({ toolCall: { functionCalls: [{ id: 'x', name: 'point_at', args: { target: 't' } }] } })
    await tick(2)
    ws().serverSend({ toolCallCancellation: { ids: ['x'] } })
    await tick(5)
    expect(aborted).toBe(true)
    expect(ws().toolResponses).toEqual([])
    await session.stop()
  })

  it('wraps non-object results', async () => {
    const { ws, session } = await boot({ toolHandler: async () => 'done' })
    ws().serverSend({ toolCall: { functionCalls: [{ id: 'a', name: 'clear_annotations', args: {} }] } })
    await tick(5)
    expect(ws().toolResponses[0]).toMatchObject({ response: { result: 'done' } })
    await session.stop()
  })
})

describe('injection', () => {
  it('sends immediately when idle, queues while speaking, flushes when idle, and cuts in with interrupt:true', async () => {
    const { ws, speaker, session } = await boot()
    session.injectText('[RUNNER] one')
    expect(ws().realtime.at(-1)).toEqual({ text: '[RUNNER] one' })
    ws().serverSend(audioEvent) // model starts speaking
    const before = ws().realtime.length
    session.injectText('[STALL] two')
    session.injectText('[STALL] three')
    expect(ws().realtime.length).toBe(before) // queued
    ws().serverSend({ serverContent: { turnComplete: true } })
    speaker.drain()
    expect(ws().realtime.at(-1)).toEqual({ text: '[STALL] two\n[STALL] three' }) // coalesced
    ws().serverSend(audioEvent)
    session.injectText('[RUNNER] now', { interrupt: true })
    expect(ws().realtime.at(-1)).toEqual({ text: '[RUNNER] now' })
    await session.stop()
  })

  it('delivers a queued injection after maxInjectWaitMs even if the model never goes idle', async () => {
    vi.useFakeTimers()
    const { ws, session } = await boot({ maxInjectWaitMs: 3000 })
    ws().serverSend(audioEvent)
    session.injectText('[STALL] late')
    vi.advanceTimersByTime(3100)
    expect(ws().realtime.at(-1)).toEqual({ text: '[STALL] late' })
    await session.stop()
  })

  it('can send as a clientContent user turn, or silently as context', async () => {
    const { ws, session } = await boot({ injectVia: 'clientContent' })
    session.injectText('hello')
    expect(ws().sent.at(-1)).toEqual({ clientContent: { turns: [{ role: 'user', parts: [{ text: 'hello' }] }], turnComplete: true } })
    session.injectText('[AGENT_RESULT] fyi', { silent: true })
    expect(ws().sent.at(-1)).toMatchObject({ clientContent: { turnComplete: false } })
    await session.stop()
  })

  it('refuses to inject when not connected', async () => {
    const { session } = await boot()
    await session.stop()
    expect(session.injectText('x')).toBe(false)
  })
})

describe('endings', () => {
  it('ends with reason idle after the idle timeout, but not while a tool is running or the mic is muted', async () => {
    vi.useFakeTimers()
    let release: () => void = () => undefined
    const { session, ws, rec } = await boot({ idleTimeoutMs: 20_000, toolHandler: () => new Promise((r) => (release = () => r({ ok: true }))) })
    ws().serverSend({ toolCall: { functionCalls: [{ id: 'a', name: 'start_lesson', args: { goal: 'g' } }] } })
    vi.advanceTimersByTime(30_000)
    expect(rec.ended).toEqual([]) // tool in flight
    release()
    await vi.advanceTimersByTimeAsync(5)
    session.setMicMuted(true)
    vi.advanceTimersByTime(60_000)
    expect(rec.ended).toEqual([]) // muted
    session.setMicMuted(false)
    vi.advanceTimersByTime(21_000)
    expect(rec.ended).toEqual(['idle'])
  })

  it('loud room noise without recognised speech does not keep the session (and screen reading) alive', async () => {
    vi.useFakeTimers()
    const { session, mic, rec } = await boot({ idleTimeoutMs: 20_000 })
    for (let i = 0; i < 30; i++) {
      mic.push!('QQ==', 0.3)
      vi.advanceTimersByTime(1000)
    }
    expect(rec.ended).toEqual(['idle'])
    void session
  })

  it('a longer idle timeout can be set (lessons)', async () => {
    vi.useFakeTimers()
    const { session, rec } = await boot({ idleTimeoutMs: 20_000 })
    session.setIdleTimeout(120_000)
    vi.advanceTimersByTime(100_000)
    expect(rec.ended).toEqual([])
    vi.advanceTimersByTime(21_000)
    expect(rec.ended).toEqual(['idle'])
  })

  it('ends with reason goodbye after the farewell finishes playing', async () => {
    const { ws, speaker, rec } = await boot()
    ws().serverSend({ serverContent: { inputTranscription: { text: 'ok thanks, goodbye' } } })
    ws().serverSend(audioEvent)
    ws().serverSend({ serverContent: { outputTranscription: { text: 'Goodbye!' } } })
    ws().serverSend({ serverContent: { turnComplete: true } })
    expect(rec.ended).toEqual([]) // farewell still playing
    speaker.drain()
    await tick(2)
    expect(rec.ended).toEqual(['goodbye'])
  })
})

describe('idle accounting and echo guard', () => {
  it('a silent 45 s session with 1 fps frames ends at ~20 s: frames never count as activity', async () => {
    vi.useFakeTimers()
    const grabbed: number[] = []
    const { session, rec, ws } = await boot({
      idleTimeoutMs: 20_000,
      frames: {
        grab: async () => {
          grabbed.push(Date.now())
          return { jpegBase64: headerJpeg(), changeScore: 0.5 }
        },
      },
    })
    for (let t = 0; t < 45; t++) await vi.advanceTimersByTimeAsync(1000)
    expect(rec.ended).toEqual(['idle'])
    expect(ws().realtime.filter((r) => r.video).length).toBeGreaterThan(10) // frames really were flowing
    expect(rec.phases).not.toContain('speaking')
    void session
  })

  it('model speech does not keep an idle session alive (a model talking to itself still ends)', async () => {
    vi.useFakeTimers()
    const { ws, rec, speaker } = await boot({ idleTimeoutMs: 20_000 })
    for (let t = 0; t < 40; t++) {
      if (t % 5 === 0) {
        ws().serverSend(audioEvent)
        ws().serverSend({ serverContent: { outputTranscription: { text: 'Are you still there? ' }, turnComplete: true } })
        speaker.drain()
      }
      await vi.advanceTimersByTimeAsync(1000)
    }
    expect(rec.ended).toEqual(['idle'])
  })

  it('learner speech and stage directions do count as activity', async () => {
    vi.useFakeTimers()
    const { ws, session, rec } = await boot({ idleTimeoutMs: 20_000 })
    await vi.advanceTimersByTimeAsync(15_000)
    ws().serverSend({ serverContent: { inputTranscription: { text: 'what do I click next please' }, turnComplete: true } })
    await vi.advanceTimersByTimeAsync(15_000)
    session.injectText('[RUNNER] step 2')
    await vi.advanceTimersByTimeAsync(15_000)
    expect(rec.ended).toEqual([])
    await vi.advanceTimersByTimeAsync(10_000)
    expect(rec.ended).toEqual(['idle'])
  })

  it('recognises its own voice in the mic transcript: hides it, is not activity, switches to half duplex', async () => {
    vi.useFakeTimers()
    const notices: string[] = []
    const { ws, session, mic, rec, speaker } = await boot({ idleTimeoutMs: 20_000 })
    session.on('notice', (n) => notices.push(n.kind))
    ws().serverSend(audioEvent)
    ws().serverSend({ serverContent: { outputTranscription: { text: 'Look at the green Start call button at the bottom of the window. ' } } })
    ws().serverSend({ serverContent: { inputTranscription: { text: 'look at the green start call button at the bottom of the window' } } })
    ws().serverSend({ serverContent: { turnComplete: true } })
    speaker.drain()
    expect(rec.transcripts.filter((t) => t.role === 'user')).toEqual([])
    expect(notices).toEqual(['echo_guard'])
    // Half duplex now: mic chunks are not uploaded while the model speaks, but a loud shout is.
    ws().serverSend(audioEvent)
    const before = ws().realtime.length
    mic.push!('QUIET', 0.05)
    expect(ws().realtime.length).toBe(before)
    mic.push!('SHOUT', 0.6)
    expect(ws().realtime.length).toBe(before + 1)
    // And a real answer afterwards is still captioned.
    ws().serverSend({ serverContent: { turnComplete: true } })
    speaker.drain()
    await vi.advanceTimersByTimeAsync(1000)
    ws().serverSend({ serverContent: { inputTranscription: { text: 'I clicked it already, what now' }, turnComplete: true } })
    expect(rec.transcripts.filter((t) => t.role === 'user' && t.final).map((t) => t.text)).toEqual(['I clicked it already, what now'])
  })

  it('does not mistake a real question that shares a few words with the answer for an echo', async () => {
    const { ws, rec } = await boot()
    ws().serverSend(audioEvent)
    ws().serverSend({ serverContent: { outputTranscription: { text: 'Click the green Start call button at the bottom. ' }, turnComplete: true } })
    ws().serverSend({ serverContent: { inputTranscription: { text: 'where is the green button on my screen' }, turnComplete: true } })
    expect(rec.transcripts.filter((t) => t.role === 'user' && t.final).map((t) => t.text)).toEqual(['where is the green button on my screen'])
  })
})

describe('resumption', () => {
  it('reconnects after an unexpected drop using the latest resumption handle', async () => {
    const { ws, session, rec } = await boot()
    const first = ws()
    first.serverSend({ sessionResumptionUpdate: { newHandle: 'handle-1', resumable: true } })
    const resumed = new Promise<{ resumed: boolean }>((res) => session.on('resumption', (r) => r.reconnected && res(r)))
    first.drop(1006)
    const r = await resumed
    expect(r.resumed).toBe(true)
    expect(FakeWebSocket.instances).toHaveLength(2)
    expect(FakeWebSocket.instances[1]!.setups[0]!.sessionResumption).toEqual({ handle: 'handle-1' })
    expect(rec.ended).toEqual([])
    // Audio flows to the new socket.
    session.injectText('after reconnect')
    expect(FakeWebSocket.instances[1]!.realtime.at(-1)).toEqual({ text: 'after reconnect' })
    await session.stop()
  })

  it('replaces the socket on GoAway (close first: the server allows one client per session) and keeps speech spoken during the gap', async () => {
    const { ws, session, mic, rec } = await boot()
    const first = ws()
    first.serverSend({ sessionResumptionUpdate: { newHandle: 'handle-2', resumable: true } })
    const resumed = new Promise<void>((res) => session.on('resumption', (r) => r.reconnected && res()))
    first.serverSend({ goAway: { timeLeft: '30s' } })
    await tick(20)
    expect(first.closedWith?.reason).toBe('handover')
    expect(FakeWebSocket.instances).toHaveLength(1) // still waiting its short pause: no concurrent socket
    mic.push!('GAP1', 0.1) // spoken while reconnecting: buffered
    await resumed
    const second = FakeWebSocket.instances[1]!
    expect(second.setups[0]!.sessionResumption).toEqual({ handle: 'handle-2' })
    expect(second.realtime.map((r) => (r.audio as { data: string } | undefined)?.data)).toContain('GAP1')
    mic.push!('LIVE1', 0.1)
    expect(second.realtime.at(-1)).toEqual({ audio: { data: 'LIVE1', mimeType: 'audio/pcm;rate=16000' } })
    expect(rec.ended).toEqual([]) // the old socket closing must not end the session
    await session.stop()
  })

  it('waits for a resumable moment before handing over', async () => {
    const { ws, session } = await boot()
    const first = ws()
    first.serverSend(audioEvent) // generating: not resumable
    first.serverSend({ goAway: { timeLeft: '30s' } })
    await tick(300)
    expect(first.closedWith).toBeNull()
    first.serverSend({ sessionResumptionUpdate: { newHandle: 'h3', resumable: true } })
    await tick(400)
    expect(first.closedWith?.reason).toBe('handover')
    expect(FakeWebSocket.instances[1]!.setups[0]!.sessionResumption).toEqual({ handle: 'h3' })
    await session.stop()
  })

  it('gives up with a fatal error after repeated reconnect failures', async () => {
    const { ws, rec } = await boot({ maxReconnectAttempts: 3 })
    FakeWebSocket.failOpen = true
    const first = ws()
    first.drop(1006)
    await vi.waitFor(() => expect(rec.ended).toEqual(['error']), { timeout: 6000, interval: 100 })
    expect(rec.errors.join(' ')).toContain('connection lost')
    FakeWebSocket.failOpen = false
  }, 8000)
})
