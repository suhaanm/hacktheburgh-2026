import { describe, expect, it } from 'vitest'
import { createContentKeeper, createCueSignals, TYPING_WINDOW_S } from './cue-glue'
import { createHttpEngine } from './cue/source'

const rig = (over: { bundle?: string | null; secure?: 'on' | 'off' | 'unknown'; locked?: boolean | null; idle?: number | null; strict?: boolean; list?: string[]; away?: number } = {}) => {
  const state = { bundle: over.bundle === undefined ? 'com.apple.finder' : over.bundle, secure: over.secure ?? 'off', locked: over.locked ?? false, idle: over.idle === undefined ? 10 : over.idle, strict: over.strict ?? true }
  const timers: Array<() => void> = []
  const s = createCueSignals({
    frontmost: { read: async () => state.bundle },
    console: { read: async () => ({ secureInput: state.secure, locked: state.locked }) },
    deny: () => ({ strict: state.strict, workerList: over.list ?? [] }),
    idleSeconds: () => state.idle,
    awaySeconds: () => over.away ?? 60,
    timers: { setInterval: (fn) => (timers.push(fn), timers.length), clearInterval: () => void timers.splice(0) },
  })
  return { s, state, timers }
}

describe('Cue signals', () => {
  it('quietS is the seconds since the last input, to a tenth (the engine holds with reason flow under 2): never a hold time', async () => {
    const { s, state } = rig({ idle: 7.349 })
    expect(s.quietS()).toBe(7.3)
    state.idle = 0.04
    expect(s.quietS()).toBe(0)
    state.idle = null
    expect(s.quietS()).toBeNull()
    state.idle = Number.NaN
    expect(s.quietS()).toBeNull()
  })

  it('typingNow is input in the last 1.5 s', () => {
    const { s, state } = rig()
    state.idle = TYPING_WINDOW_S - 0.1
    expect(s.typingNow()).toBe(true)
    state.idle = TYPING_WINDOW_S
    expect(s.typingNow()).toBe(false)
    state.idle = null
    expect(s.typingNow()).toBe(false)
  })

  it('suppressed: secure input first, then a denied app, then (strict) unknown; null for an ordinary app', async () => {
    const a = rig()
    await a.s.refresh()
    expect(a.s.suppressed()).toBeNull()
    const sec = rig({ secure: 'on', bundle: 'com.1password.1password' })
    await sec.s.refresh()
    expect(sec.s.suppressed()).toBe('secure_input')
    const pw = rig({ bundle: 'com.1password.1password' })
    await pw.s.refresh()
    expect(pw.s.suppressed()).toBe('app_denied')
    const mine = rig({ bundle: 'com.example.mine', list: ['com.example.mine'] })
    await mine.s.refresh()
    expect(mine.s.suppressed()).toBe('app_denied')
    const msg = rig({ bundle: 'com.tinyspeck.slackmacgap' })
    await msg.s.refresh()
    expect(msg.s.suppressed()).toBe('app_denied')
    const unknownApp = rig({ bundle: null })
    await unknownApp.s.refresh()
    expect(unknownApp.s.suppressed()).toBe('app_unknown')
    const unknownSecure = rig({ secure: 'unknown' })
    await unknownSecure.s.refresh()
    expect(unknownSecure.s.suppressed()).toBe('secure_input_unknown')
    const lax = rig({ secure: 'unknown', bundle: null, strict: false })
    await lax.s.refresh()
    expect(lax.s.suppressed()).toBeNull()
  })

  it('a probe that throws is a reason to stay away', async () => {
    const s = createCueSignals({ frontmost: { read: async () => { throw new Error('x') } }, console: { read: async () => ({ secureInput: 'off', locked: false }) }, deny: () => ({ strict: true, workerList: [] }), idleSeconds: () => 1, awaySeconds: () => 60 })
    await s.refresh()
    expect(s.suppressed()).toBe('probe_failed')
  })

  it('away: locked, or idle for awaySeconds (never under 3 s)', async () => {
    const a = rig({ idle: 59 })
    await a.s.refresh()
    expect(a.s.away()).toBe(false)
    a.state.idle = 60
    expect(a.s.away()).toBe(true)
    const l = rig({ idle: 1, locked: true })
    await l.s.refresh()
    expect(l.s.away()).toBe(true)
    const tiny = rig({ idle: 2, away: 0 })
    await tiny.s.refresh()
    expect(tiny.s.away()).toBe(false)
  })

  it('start polls on its own and stop clears the reason (no timer left)', async () => {
    const { s, timers } = rig({ secure: 'on' })
    s.start()
    s.start()
    expect(timers).toHaveLength(1)
    await new Promise((r) => setTimeout(r, 0)) // start() already began a probe round
    expect(s.suppressed()).toBe('secure_input')
    s.stop()
    expect(timers).toHaveLength(0)
    expect(s.suppressed()).toBeNull()
  })
})

describe('what GET /cue/next receives from those signals', () => {
  it('quiet_s, denied=1, away=1 and typing=1 each mean what the engine reads them as', async () => {
    const urls: string[] = []
    const eng = createHttpEngine({ baseUrl: 'http://127.0.0.1:7700', person: () => 'p_demo01', fetchImpl: (async (u: string) => (urls.push(u), new Response('{}', { status: 200 }))) as unknown as typeof fetch })
    await eng.next({ quietS: 7.3, denied: true, away: true, typing: true })
    const q = new URL(urls[0]!).searchParams
    expect(q.get('quiet_s')).toBe('7.3')
    expect(q.get('denied')).toBe('1')
    expect(q.get('away')).toBe('1')
    expect(q.get('typing')).toBe('1')
    await eng.next({ quietS: 4000_000 })
    expect(new URL(urls[1]!).searchParams.get('quiet_s')).toBe('86400') // clamped, never a "hold" of any length
    await eng.next({})
    const none = new URL(urls[2]!).searchParams
    for (const k of ['quiet_s', 'denied', 'away', 'typing']) expect(none.has(k)).toBe(false)
  })
})

describe('content keeper', () => {
  it('keeps the latest boxes for the ttl, then null; an answer without content does not erase them', () => {
    let t = 1000
    const k = createContentKeeper({ ttlMs: 4000, now: () => t })
    expect(k.get()).toBeNull()
    k.set([{ x: 1, y: 2, w: 3, h: 4 }])
    expect(k.get()).toEqual([{ x: 1, y: 2, w: 3, h: 4 }])
    t += 3000
    k.set([])
    expect(k.get()).toHaveLength(1)
    t += 1500
    expect(k.get()).toBeNull()
    k.set([{ x: 5, y: 6, w: 7, h: 8 }])
    k.clear()
    expect(k.get()).toBeNull()
  })
})
