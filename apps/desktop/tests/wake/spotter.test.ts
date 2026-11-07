import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PERSONA_LIST } from '../../src/shared/personas'
import { createWakeSpotter, type WakeAudioSource, type WakeEngine, type WakeEngineHandlers, type WakeEvent, type WakeStatus } from '../../src/renderer/wake'

class FakeAudio implements WakeAudioSource {
  starts = 0
  stops = 0
  open = false
  private cb: ((p: Int16Array) => void) | null = null
  failWith: Error | null = null
  async start(onPcm: (p: Int16Array) => void): Promise<void> {
    if (this.failWith) throw this.failWith
    this.starts++
    this.open = true
    this.cb = onPcm
  }
  stop(): void {
    this.stops++
    this.open = false
    this.cb = null
  }
  // 100 ms of audio whose samples carry a marker so pre-roll contents can be checked.
  feed(marker: number, frames = 1): void {
    for (let i = 0; i < frames; i++) this.cb?.(new Int16Array(1600).fill(marker))
  }
}

class FakeEngine implements WakeEngine {
  sent: Int16Array[] = []
  stopped = false
  constructor(
    readonly h: WakeEngineHandlers,
    private readonly failStart: Error | null,
    private readonly autoReady: boolean,
  ) {}
  async start(): Promise<void> {
    if (this.failStart) throw this.failStart
    if (this.autoReady) this.h.onReady()
  }
  send(p: Int16Array): void {
    this.sent.push(p)
  }
  stop(): void {
    this.stopped = true
  }
}

function rig(opts: Partial<Parameters<typeof createWakeSpotter>[0]> & { failStarts?: number } = {}) {
  const audio = new FakeAudio()
  const engines: FakeEngine[] = []
  const wakes: WakeEvent[] = []
  const statuses: WakeStatus[] = []
  let failStarts = opts.failStarts ?? 0
  const spotter = createWakeSpotter({
    personas: PERSONA_LIST,
    createAudioSource: () => audio,
    createEngine: (h) => {
      const fail = failStarts-- > 0 ? new Error('boom') : null
      const e = new FakeEngine(h, fail, true)
      engines.push(e)
      return e
    },
    onWake: (e) => wakes.push(e),
    onStatus: (s) => statuses.push(s),
    ...opts,
  })
  return { audio, engines, wakes, statuses, spotter, last: () => engines[engines.length - 1]! }
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-10-31T12:00:00Z'))
})
afterEach(() => vi.useRealTimers())

describe('wake spotter', () => {
  it('goes starting -> listening and reports the cloud privacy truth', async () => {
    const r = rig()
    await r.spotter.start()
    expect(r.statuses.map((s) => s.state)).toEqual(['starting', 'listening'])
    expect(r.spotter.getStatus()).toMatchObject({ listening: true, cloud: true, pausedFor: [], engine: 'gemini-transcribe-live' })
  })

  it('fires onWake with the matched persona and source "wake"; ignores unrelated speech', async () => {
    const r = rig()
    await r.spotter.start()
    r.last().h.onTranscript('Hey Google, what is the weather', false)
    r.last().h.onTranscript('Marcus Aurelius was an emperor', true)
    expect(r.wakes).toHaveLength(0)
    r.last().h.onTranscript('Hey Amelia, how do I join the video call', false)
    expect(r.wakes).toHaveLength(1)
    expect(r.wakes[0]).toMatchObject({ personaId: 'amelia', source: 'wake', score: 1, trailing: 'how do i join the video call' })
  })

  it('an interim that stands unchanged counts as an utterance end, so a bare "Amelia." still wakes (ASR dropped "hey")', async () => {
    const r = rig()
    await r.spotter.start()
    r.last().h.onTranscript('Amelia.', false)
    await vi.advanceTimersByTimeAsync(600)
    r.last().h.onTranscript('Amelia.', false)
    expect(r.wakes).toHaveLength(0)
    await vi.advanceTimersByTimeAsync(700)
    r.last().h.onTranscript('Amelia.', false)
    expect(r.wakes).toHaveLength(1)
    expect(r.wakes[0]!.personaId).toBe('amelia')
  })

  it('a bare name that keeps growing into a sentence never wakes, however long it stands', async () => {
    const r = rig()
    await r.spotter.start()
    r.last().h.onTranscript('Marcus', false)
    await vi.advanceTimersByTimeAsync(1500)
    r.last().h.onTranscript('Marcus Aurelius', false)
    await vi.advanceTimersByTimeAsync(1500)
    r.last().h.onTranscript('Marcus Aurelius', false)
    await vi.advanceTimersByTimeAsync(1500)
    r.last().h.onTranscript('Marcus Aurelius was a Roman emperor', false)
    expect(r.wakes).toHaveLength(0)
  })

  it('stops streaming to the cloud right after a wake, and the cooldown swallows a duplicate', async () => {
    const r = rig()
    await r.spotter.start()
    const first = r.last()
    first.h.onTranscript('Hey Marcus', false)
    expect(first.stopped).toBe(true)
    expect(r.spotter.getStatus()).toMatchObject({ state: 'paused', listening: false, pausedFor: ['live'] })
    first.h.onTranscript('Hey Marcus', true) // stale engine callback after stop must be ignored
    expect(r.wakes).toHaveLength(1)
  })

  it('only forwards mic audio to the engine while listening', async () => {
    const r = rig()
    await r.spotter.start()
    r.audio.feed(1, 3)
    expect(r.last().sent).toHaveLength(3)
    r.spotter.pause('manual')
    r.audio.feed(2, 2)
    expect(r.last().sent).toHaveLength(3)
  })

  it('takePreroll hands LIVE ~1.5 s before the name plus everything after, then releases the mic', async () => {
    const r = rig()
    await r.spotter.start()
    r.audio.feed(1, 40) // 4 s of earlier speech; only the last 1.5 s may be returned
    r.audio.feed(2, 5) // the name
    r.last().h.onTranscript('Hey Marcus', false)
    r.audio.feed(3, 10) // "make the text bigger" while the session connects
    expect(r.audio.open).toBe(true) // local-only capture continues for the handoff
    const pcm = r.spotter.takePreroll()!
    expect(pcm.length).toBe((15 + 10) * 1600) // 1.5 s lead (incl. the name) + the 1 s said after it
    expect(pcm[0]).toBe(1)
    expect(pcm[pcm.length - 1]).toBe(3)
    expect(pcm.includes(2)).toBe(true)
    expect(r.audio.open).toBe(false)
    expect(r.spotter.takePreroll()).toBeNull()
  })

  it('pause("live") then resume("live") hands the mic over and back', async () => {
    const r = rig()
    await r.spotter.start()
    r.last().h.onTranscript('Hey Marcus', false)
    r.spotter.pause('live')
    r.spotter.takePreroll()
    expect(r.audio.open).toBe(false)
    expect(r.engines).toHaveLength(1)
    r.spotter.resume('live')
    await vi.advanceTimersByTimeAsync(0)
    expect(r.engines).toHaveLength(2)
    expect(r.audio.open).toBe(true)
    expect(r.spotter.getStatus().listening).toBe(true)
  })

  it('a wake nobody picked up (no pause("live") within 15 s) goes back to listening', async () => {
    const r = rig()
    await r.spotter.start()
    r.last().h.onTranscript('Hey Marcus', false)
    expect(r.spotter.getStatus().listening).toBe(false)
    await vi.advanceTimersByTimeAsync(15_100)
    expect(r.spotter.getStatus().listening).toBe(true)
  })

  it('TTS pause stops cloud streaming but keeps the mic warm; resume reconnects', async () => {
    const r = rig()
    await r.spotter.start()
    r.spotter.pause('tts')
    expect(r.engines[0]!.stopped).toBe(true)
    expect(r.audio.open).toBe(true)
    expect(r.spotter.getStatus()).toMatchObject({ state: 'paused', pausedFor: ['tts'] })
    r.spotter.resume('tts')
    await vi.advanceTimersByTimeAsync(0)
    expect(r.engines).toHaveLength(2)
    expect(r.spotter.getStatus().listening).toBe(true)
    expect(r.audio.starts).toBe(1)
  })

  it('honours wakeEnabled, pushToTalkOnly and mute: no engine, mic released', async () => {
    const r = rig({ settings: { wakeEnabled: false } })
    await r.spotter.start()
    expect(r.engines).toHaveLength(0)
    expect(r.audio.starts).toBe(0)
    expect(r.spotter.getStatus()).toMatchObject({ state: 'paused', pausedFor: ['disabled'] })

    r.spotter.setSettings({ wakeEnabled: true })
    await vi.advanceTimersByTimeAsync(0)
    expect(r.spotter.getStatus().listening).toBe(true)

    r.spotter.setSettings({ pushToTalkOnly: true })
    expect(r.spotter.getStatus()).toMatchObject({ listening: false, pausedFor: ['push-to-talk-only'] })
    expect(r.audio.open).toBe(false)

    r.spotter.setSettings({ pushToTalkOnly: false, micMuted: true })
    expect(r.spotter.getStatus()).toMatchObject({ listening: false, pausedFor: ['muted'] })
    expect(r.audio.open).toBe(false)

    r.spotter.setSettings({ micMuted: false })
    await vi.advanceTimersByTimeAsync(0)
    expect(r.spotter.getStatus().listening).toBe(true)
  })

  it('repeated identical setSettings calls (the dock sends one per state update) never retrigger a connection', async () => {
    const r = rig({ failStarts: 99 })
    await r.spotter.start()
    await vi.advanceTimersByTimeAsync(60_000)
    expect(r.spotter.getStatus().state).toBe('unavailable')
    const attempts = r.engines.length
    for (let i = 0; i < 20; i++) r.spotter.setSettings({ wakeEnabled: true, pushToTalkOnly: false, micMuted: false })
    await vi.advanceTimersByTimeAsync(0) // (the 20 s background recovery is a separate, deliberate retry)
    expect(r.engines.length).toBe(attempts)
    // A genuine change (mute then unmute) is allowed to try again.
    r.spotter.setSettings({ micMuted: true })
    r.spotter.setSettings({ micMuted: false })
    await vi.advanceTimersByTimeAsync(0)
    expect(r.engines.length).toBeGreaterThan(attempts)
  })

  it('reconnects with backoff after a dropped stream, and keeps hearing the name afterwards', async () => {
    const r = rig()
    await r.spotter.start()
    r.last().h.onError(new Error('socket closed'), false)
    expect(r.spotter.getStatus()).toMatchObject({ state: 'reconnecting', listening: false })
    await vi.advanceTimersByTimeAsync(600)
    expect(r.engines).toHaveLength(2)
    expect(r.spotter.getStatus().listening).toBe(true)
    r.last().h.onTranscript('hi marcus', false)
    expect(r.wakes).toHaveLength(1)
  })

  it('gives up visibly after repeated failures (unavailable) so the UI can point at the button/hotkey', async () => {
    const r = rig({ failStarts: 99 })
    await r.spotter.start()
    await vi.advanceTimersByTimeAsync(60_000)
    const s = r.spotter.getStatus()
    expect(s.state).toBe('unavailable')
    expect(s.detail).toMatch(/button or the keyboard shortcut/)
    expect(r.audio.open).toBe(false)
  })

  it('never puts raw API or IPC error text in the user-facing status (plain English only)', async () => {
    const raw = `Error invoking remote method 'wake:token': ApiError: {"error":{"code":500,"status":"INTERNAL"}}`
    const audio = new FakeAudio()
    const spotter = createWakeSpotter({
      personas: PERSONA_LIST,
      createAudioSource: () => audio,
      createEngine: (h) => {
        const e = new FakeEngine(h, new Error(raw), false)
        return e
      },
      onWake: () => undefined,
    })
    const seen: WakeStatus[] = []
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const s2 = createWakeSpotter({
      personas: PERSONA_LIST,
      createAudioSource: () => new FakeAudio(),
      createEngine: (h) => new FakeEngine(h, new Error(raw), false),
      onStatus: (st) => seen.push(st),
      onWake: () => undefined,
    })
    await s2.start()
    await vi.advanceTimersByTimeAsync(60_000)
    const details = seen.map((x) => x.detail).filter(Boolean) as string[]
    expect(details.length).toBeGreaterThan(0)
    for (const d of details) {
      expect(d).not.toMatch(/ApiError|invoking remote|wake:token|500|\{|Error:/)
    }
    expect(s2.getStatus().detail).toBe('Voice activation is unavailable right now. Use the button or the keyboard shortcut.')
    expect(warn).toHaveBeenCalled() // the raw error is kept for the console only
    warn.mockRestore()
    spotter.dispose()
    s2.dispose()
  })

  it('recovers by itself once the network is back (no restart), without reopening the mic while it is down', async () => {
    let net = false
    const audio = new FakeAudio()
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const engines: FakeEngine[] = []
    const spotter = createWakeSpotter({
      personas: PERSONA_LIST,
      createAudioSource: () => audio,
      getToken: async () => {
        if (!net) throw new Error('fetch failed')
        return { token: 't' }
      },
      createEngine: (h) => {
        const e = new FakeEngine(h, net ? null : new Error('fetch failed'), true)
        engines.push(e)
        return e
      },
      onWake: () => undefined,
    })
    await spotter.start()
    await vi.advanceTimersByTimeAsync(60_000)
    expect(spotter.getStatus().state).toBe('unavailable')
    const micOpens = audio.starts
    await vi.advanceTimersByTimeAsync(120_000) // network still down: probes only, mic stays closed
    expect(audio.starts).toBe(micOpens)
    expect(audio.open).toBe(false)
    net = true
    await vi.advanceTimersByTimeAsync(25_000)
    expect(spotter.getStatus()).toMatchObject({ state: 'listening', listening: true })
    expect(spotter.getStatus().detail).toBeUndefined()
    expect(audio.open).toBe(true)
    warn.mockRestore()
    spotter.dispose()
  })

  it('microphone permission denied is unavailable immediately, with a clear reason', async () => {
    const r = rig()
    r.audio.failWith = Object.assign(new Error('denied'), { name: 'NotAllowedError' })
    await r.spotter.start()
    expect(r.spotter.getStatus()).toMatchObject({ state: 'unavailable' })
    expect(r.spotter.getStatus().detail).toMatch(/microphone permission/)
  })

  it('rotates to a fresh stream before the 10-minute cap without a deaf gap', async () => {
    const r = rig({ maxSessionMs: 10_000 })
    await r.spotter.start()
    const old = r.last()
    await vi.advanceTimersByTimeAsync(10_100)
    expect(r.engines).toHaveLength(2)
    expect(old.stopped).toBe(true)
    expect(r.engines[1]!.stopped).toBe(false)
    expect(r.spotter.getStatus().listening).toBe(true)
    r.audio.feed(1)
    expect(r.engines[1]!.sent).toHaveLength(1)
    r.engines[1]!.h.onTranscript('Hey Amelia', false)
    expect(r.wakes[0]?.personaId).toBe('amelia')
  })

  it('a rotation that never gets ready is abandoned, the old stream keeps listening, and rotation is retried', async () => {
    const audio = new FakeAudio()
    const engines: FakeEngine[] = []
    const spotter = createWakeSpotter({
      personas: PERSONA_LIST,
      createAudioSource: () => audio,
      maxSessionMs: 10_000,
      createEngine: (h) => {
        const e = new FakeEngine(h, null, engines.length === 0) // only the first engine becomes ready
        engines.push(e)
        return e
      },
      onWake: () => undefined,
    })
    await spotter.start()
    await vi.advanceTimersByTimeAsync(10_100)
    expect(engines).toHaveLength(2)
    await vi.advanceTimersByTimeAsync(8_100)
    expect(engines[1]!.stopped).toBe(true)
    expect(engines[0]!.stopped).toBe(false)
    expect(spotter.getStatus().listening).toBe(true)
    spotter.dispose()
  })

  it('does not rotate in the middle of an utterance', async () => {
    const r = rig({ maxSessionMs: 10_000 })
    await r.spotter.start()
    await vi.advanceTimersByTimeAsync(9_900)
    r.last().h.onTranscript('so I was thinking', false)
    await vi.advanceTimersByTimeAsync(300)
    expect(r.engines).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(2_500)
    expect(r.engines).toHaveLength(2)
  })

  it('stop() and dispose() release the mic and the engine and are idempotent', async () => {
    const r = rig()
    await r.spotter.start()
    r.spotter.dispose()
    r.spotter.dispose()
    expect(r.audio.open).toBe(false)
    expect(r.last().stopped).toBe(true)
    await r.spotter.start()
    expect(r.engines).toHaveLength(1)
  })

  it('works without a token source only if an engine is injected (fails closed otherwise)', async () => {
    const s = createWakeSpotter({ personas: PERSONA_LIST, createAudioSource: () => new FakeAudio(), onWake: () => undefined })
    await s.start()
    expect(s.getStatus().state).toBe('unavailable')
    s.dispose()
  })
})
