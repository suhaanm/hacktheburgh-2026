import { describe, expect, it } from 'vitest'
import { createBridgeIpc, type BridgeIpc } from './bridge-ipc'
import { LIVE_IPC } from './ipc-channels'
import { MicError } from './ports'
import { createLivePreloadApi } from './preload-api'

function rig(o: { micTimeoutMs?: number; clipTimeoutMs?: number } = {}) {
  const sent: Array<[string, unknown[]]> = []
  const handlers = new Map<string, (...a: unknown[]) => void>()
  const ipc: BridgeIpc = { send: (c, ...a) => void sent.push([c, a]), on: (c, l) => (handlers.set(c, l), () => void handlers.delete(c)) }
  const b = createBridgeIpc(ipc, o)
  return { b, sent, from: (c: string, ...a: unknown[]) => handlers.get(c)?.(...a), handlers }
}

describe('the microphone', () => {
  it('asks the renderer to open it, waits for the answer, and forwards only validated chunks while it is meant to be open', async () => {
    const t = rig()
    const got: Array<[string, number]> = []
    const p = t.b.audio.startMic((b, l) => void got.push([b, l]))
    expect(t.sent[0]![0]).toBe(LIVE_IPC.micStart)
    const reqId = (t.sent[0]![1][0] as { reqId: number }).reqId
    t.from(LIVE_IPC.micResult, { reqId, ok: true })
    await p
    t.from(LIVE_IPC.micChunk, 'AAAA', 0.4)
    t.from(LIVE_IPC.micChunk, 'AAAA', 7) // level clamped
    t.from(LIVE_IPC.micChunk, 'AAAA', 'x') // level not a number: 0
    t.from(LIVE_IPC.micChunk, 12345, 0.1) // not a string
    t.from(LIVE_IPC.micChunk, '', 0.1)
    t.from(LIVE_IPC.micChunk, 'not base64 !!!', 0.1)
    t.from(LIVE_IPC.micChunk, 'A'.repeat(20_000), 0.1) // too large to be a microphone chunk
    expect(got).toEqual([['AAAA', 0.4], ['AAAA', 1], ['AAAA', 0]])
  })
  it('drops chunks that arrive when the microphone is not meant to be open', async () => {
    const t = rig()
    const got: string[] = []
    t.from(LIVE_IPC.micChunk, 'AAAA', 0.4) // before any start
    const p = t.b.audio.startMic((b) => void got.push(b))
    t.from(LIVE_IPC.micResult, { reqId: (t.sent[0]![1][0] as { reqId: number }).reqId, ok: true })
    await p
    t.b.audio.stopMic()
    expect(t.sent[t.sent.length - 1]![0]).toBe(LIVE_IPC.micStop)
    t.from(LIVE_IPC.micChunk, 'AAAA', 0.4) // a late chunk after stop
    expect(got).toEqual([])
  })
  it('maps a refusal to a MicError with the right code, and an unanswered request to a device error', async () => {
    const t = rig({ micTimeoutMs: 20 })
    const p = t.b.audio.startMic(() => undefined)
    t.from(LIVE_IPC.micResult, { reqId: (t.sent[0]![1][0] as { reqId: number }).reqId, ok: false, code: 'permission' })
    await expect(p).rejects.toMatchObject({ code: 'permission' })
    await expect(p).rejects.toBeInstanceOf(MicError)
    await expect(t.b.audio.startMic(() => undefined)).rejects.toMatchObject({ code: 'device' })
  })
  it('ignores an answer for a request it did not make', async () => {
    const t = rig({ micTimeoutMs: 30 })
    const p = t.b.audio.startMic(() => undefined)
    t.from(LIVE_IPC.micResult, { reqId: 9999, ok: true })
    await expect(p).rejects.toMatchObject({ code: 'device' })
  })
})

describe('playback and clips', () => {
  it('sends model audio, tracks whether it is playing, and reports the queue draining', () => {
    const t = rig()
    let idle = 0
    t.b.audio.onPlaybackIdle(() => void idle++)
    t.b.audio.play('AAAA')
    t.b.audio.play('') // nothing
    expect(t.b.audio.isPlaying()).toBe(true)
    expect(t.sent.filter(([c]) => c === LIVE_IPC.play)).toHaveLength(1)
    t.from(LIVE_IPC.playbackIdle)
    expect(idle).toBe(1)
    expect(t.b.audio.isPlaying()).toBe(false)
    t.b.audio.play('AAAA')
    t.b.audio.flush()
    expect(t.b.audio.isPlaying()).toBe(false)
  })
  it('plays a clip and resolves when the renderer says it ended; refuses odd clips; stop resolves it', async () => {
    const t = rig({ clipTimeoutMs: 1000 })
    const p = t.b.clips.play(new Uint8Array([1, 2, 3]), 'audio/mpeg')
    const msg = t.sent[0]!
    expect(msg[0]).toBe(LIVE_IPC.clipPlay)
    t.from(LIVE_IPC.clipDone, { reqId: (msg[1][0] as { reqId: number }).reqId, ok: true })
    await p
    await t.b.clips.play(new Uint8Array(0), 'audio/mpeg')
    await t.b.clips.play(new Uint8Array([1]), 'text/html')
    await t.b.clips.play(new Uint8Array(3_000_000), 'audio/mpeg')
    expect(t.sent.filter(([c]) => c === LIVE_IPC.clipPlay)).toHaveLength(1)
    const q = t.b.clips.play(new Uint8Array([1]), 'audio/wav')
    t.b.clips.stop()
    await q
    expect(t.sent[t.sent.length - 1]![0]).toBe(LIVE_IPC.clipStop)
  })
  it('dispose removes every listener', () => {
    const t = rig()
    expect(t.handlers.size).toBe(4)
    t.b.dispose()
    expect(t.handlers.size).toBe(0)
  })
})

describe('the preload api', () => {
  it('forwards main messages to callbacks and renderer messages to ipc.send, and nothing else', () => {
    const listeners = new Map<string, (e: unknown, ...a: unknown[]) => void>()
    const sent: Array<[string, unknown[]]> = []
    const api = createLivePreloadApi({ on: (c, l) => void listeners.set(c, l), off: (c) => void listeners.delete(c), send: (c, ...a) => void sent.push([c, a]) })
    const got: unknown[] = []
    const off = api.onPlay((b) => void got.push(b))
    listeners.get(LIVE_IPC.play)!({}, 'AAAA')
    expect(got).toEqual(['AAAA'])
    off()
    expect(listeners.has(LIVE_IPC.play)).toBe(false)
    api.micChunk('AAAA', 0.2)
    api.playbackIdle()
    expect(sent).toEqual([[LIVE_IPC.micChunk, ['AAAA', 0.2]], [LIVE_IPC.playbackIdle, []]])
    expect(Object.keys(api).sort()).toEqual(['clipDone', 'micChunk', 'micResult', 'onClipPlay', 'onClipStop', 'onFlush', 'onMicStart', 'onMicStop', 'onPlay', 'playbackIdle'])
  })
})
