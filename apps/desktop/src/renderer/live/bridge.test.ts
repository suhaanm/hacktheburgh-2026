import { describe, expect, it } from 'vitest'
import { startLiveBridge } from './bridge'
import type { LiveRendererApi } from '../../main/live/preload-api'
import type { AudioInput, AudioOutput } from './types'

function rig(over: { micFails?: 'permission' | 'device' | null } = {}) {
  const h: Record<string, (...a: any[]) => void> = {}
  const out = { micResult: [] as any[], chunks: [] as Array<[string, number]>, idle: 0, clipDone: [] as any[] }
  const api: LiveRendererApi = {
    onMicStart: (cb) => ((h.micStart = cb), () => delete h.micStart),
    onMicStop: (cb) => ((h.micStop = cb), () => delete h.micStop),
    onPlay: (cb) => ((h.play = cb), () => delete h.play),
    onFlush: (cb) => ((h.flush = cb), () => delete h.flush),
    onClipPlay: (cb) => ((h.clipPlay = cb), () => delete h.clipPlay),
    onClipStop: (cb) => ((h.clipStop = cb), () => delete h.clipStop),
    micResult: (r) => void out.micResult.push(r),
    micChunk: (b, l) => void out.chunks.push([b, l]),
    playbackIdle: () => void out.idle++,
    clipDone: (r) => void out.clipDone.push(r),
  }
  const log = { micStarts: 0, micStops: 0, played: [] as string[], flushes: 0, closes: 0, clips: 0, clipStops: 0 }
  let emit: ((b: string, l: number) => void) | null = null
  let idleCb: (() => void) | null = null
  const mic: AudioInput = {
    start: async (cb) => {
      if (over.micFails) throw Object.assign(new Error(over.micFails === 'permission' ? 'denied' : 'no device'), { name: over.micFails === 'permission' ? 'NotAllowedError' : 'NotFoundError' })
      log.micStarts++
      emit = cb
    },
    stop: () => void log.micStops++,
  }
  const player: AudioOutput = {
    init: async () => undefined,
    play: (b) => void log.played.push(b),
    flush: () => void log.flushes++,
    level: () => 0,
    isPlaying: () => false,
    onIdle: (cb) => ((idleCb = cb), () => undefined),
    close: () => void log.closes++,
  }
  let clipResolve: ((ok: boolean) => void) | null = null
  const stop = startLiveBridge(api, {
    createMic: () => mic,
    createPlayer: () => player,
    playClip: () => ({ done: new Promise<boolean>((r) => (clipResolve = r)), stop: () => void log.clipStops++ }),
  })
  void log.clips
  return { h, out, log, stop, feed: (b: string, l = 0.2) => emit?.(b, l), drain: () => idleCb?.(), endClip: (ok = true) => clipResolve?.(ok) }
}

const tick = (): Promise<void> => new Promise((r) => setTimeout(r, 0))

describe('the renderer bridge', () => {
  it('does nothing without a bridge (the flag-off build)', () => {
    expect(startLiveBridge(undefined)()).toBeUndefined()
  })
  it('opens the microphone only when main says so, forwards chunks to main, and reports the result', async () => {
    const t = rig()
    expect(t.log.micStarts).toBe(0)
    t.h.micStart!({ reqId: 7 })
    await tick()
    expect(t.out.micResult).toEqual([{ reqId: 7, ok: true }])
    t.feed('AAAA', 0.3)
    expect(t.out.chunks).toEqual([['AAAA', 0.3]])
    t.h.micStop!()
    expect(t.log.micStops).toBe(1)
  })
  it.each([['permission', 'permission'], ['device', 'device']] as const)('reports a %s failure with its code and holds no microphone afterwards', async (fail, code) => {
    const t = rig({ micFails: fail })
    t.h.micStart!({ reqId: 1 })
    await tick()
    expect(t.out.micResult).toEqual([{ reqId: 1, ok: false, code }])
    expect(t.log.micStops).toBeGreaterThan(0)
  })
  it('plays model audio, flushes on command, and tells main when the queue drains', async () => {
    const t = rig()
    t.h.play!('AAAA')
    await tick()
    expect(t.log.played).toEqual(['AAAA'])
    t.h.flush!()
    expect(t.log.flushes).toBe(1)
    t.drain()
    expect(t.out.idle).toBe(1)
  })
  it('plays a clip, tells main when it ended, and can be stopped', async () => {
    const t = rig()
    t.h.clipPlay!({ reqId: 3, mime: 'audio/mpeg', bytes: new ArrayBuffer(4) })
    t.endClip(true)
    await tick()
    expect(t.out.clipDone).toEqual([{ reqId: 3, ok: true }])
    t.h.clipPlay!({ reqId: 4, mime: 'audio/mpeg', bytes: new ArrayBuffer(4) })
    t.h.clipStop!()
    expect(t.log.clipStops).toBe(1)
  })
  it('stopping the bridge releases the microphone and the player and removes its handlers', async () => {
    const t = rig()
    t.h.micStart!({ reqId: 1 })
    t.h.play!('AAAA')
    await tick()
    t.stop()
    expect(t.log.micStops).toBeGreaterThan(0)
    expect(t.log.closes).toBe(1)
    expect(Object.keys(t.h)).toEqual([])
  })
})
