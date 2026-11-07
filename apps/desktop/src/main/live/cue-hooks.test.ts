import { describe, expect, it } from 'vitest'
import { createCueSpeaker, createCueVoice } from './cue-hooks'
import { OTHER_OPTION_ID } from '../cue/voice'
import { isLoopbackUrl } from '../engine/endpoints'
import type { ClipPlayer } from './ports'

const options = [{ id: 'read_case', label: 'Read the household record' }, { id: 'calc_a', label: 'Run calculator A' }, { id: 'cliff_a', label: 'Check cliff edges' }]

const mgr = (heard: string | null, allowed = true) => {
  const calls = { listen: 0, timeout: 0 }
  return { calls, m: { voiceAllowed: () => allowed, listen: async (ms: number) => (calls.listen++, (calls.timeout = ms), heard) } }
}

describe('CueVoice.listenOnce', () => {
  it.each([
    ['the second one', 'calc_a'],
    ['number two', 'calc_a'],
    ['2', 'calc_a'],
    ['the last one', 'cliff_a'],
    ['read the household record', 'read_case'],
    ['something else', OTHER_OPTION_ID],
    ['none of those', OTHER_OPTION_ID],
  ])('turns "%s" into %s', async (said, id) => {
    expect(await createCueVoice({ manager: mgr(said).m }).listenOnce(options)).toBe(id)
  })
  it.each([[null], [''], ['banana'], ['um']])('is null for %j (silence, no match or ambiguous: never a guess)', async (said) => {
    expect(await createCueVoice({ manager: mgr(said as string | null).m }).listenOnce(options)).toBeNull()
  })
  it('never listens when voice is not allowed or the worker switched Cue voice off, and never throws', async () => {
    const a = mgr('the first one', false)
    expect(await createCueVoice({ manager: a.m }).listenOnce(options)).toBeNull()
    expect(a.calls.listen).toBe(0)
    const b = mgr('the first one')
    expect(await createCueVoice({ manager: b.m, cueVoiceOn: () => false }).listenOnce(options)).toBeNull()
    expect(b.calls.listen).toBe(0)
    expect(await createCueVoice({ manager: b.m }).listenOnce([])).toBeNull()
    const boom = { voiceAllowed: () => true, listen: async () => { throw new Error('mic exploded') } }
    expect(await createCueVoice({ manager: boom }).listenOnce(options)).toBeNull()
  })
  it('passes the listening window to the manager (default six seconds)', async () => {
    const a = mgr('first')
    await createCueVoice({ manager: a.m }).listenOnce(options)
    expect(a.calls.timeout).toBe(6000)
    await createCueVoice({ manager: a.m }).listenOnce(options, { timeoutMs: 3000 })
    expect(a.calls.timeout).toBe(3000)
  })
})

// ------------------------------------------------------------------------------------------------ the speaker
const ENV = { UNDERSTUDY_X_LIVE: '1', UNDERSTUDY_FLAG_VOICE: '1', UNDERSTUDY_VOICE: '1' }

function speakerRig(over: { env?: Record<string, string>; busy?: () => boolean; response?: { status?: number; source?: string; mime?: string; bytes?: number } | 'throw' } = {}) {
  const played: Array<{ bytes: number; mime: string }> = []
  const calls: Array<{ url: string; body: any }> = []
  let stopped = 0
  const clip: ClipPlayer = { play: async (b, m) => void played.push({ bytes: b.length, mime: m }), stop: () => void (stopped += 1) }
  const r = over.response ?? {}
  const f = (async (url: string, init: RequestInit) => {
    calls.push({ url: String(url), body: JSON.parse(String(init.body)) })
    if (r === 'throw') throw new TypeError('down')
    const headers = new Map([['x-voice-source', r.source ?? 'cache'], ['content-type', r.mime ?? 'audio/mpeg']])
    return { ok: (r.status ?? 200) < 400, status: r.status ?? 200, headers: { get: (k: string) => headers.get(k.toLowerCase()) ?? null }, arrayBuffer: async () => new Uint8Array(r.bytes ?? 500).buffer } as unknown as Response
  }) as unknown as typeof fetch
  const sp = createCueSpeaker({ env: over.env ?? ENV, agentUrl: 'http://127.0.0.1:7710', isLoopback: isLoopbackUrl, clip, fetchImpl: f, liveBusy: over.busy ?? (() => false) })
  return { sp, played, calls, stops: () => stopped }
}

describe('CueSpeaker.say', () => {
  it('asks the agent for a fixed line BY ID (never text) and plays what comes back', async () => {
    const t = speakerRig()
    await t.sp.say('whisper.read_case')
    expect(t.calls).toEqual([{ url: 'http://127.0.0.1:7710/voice/speak', body: { line_id: 'whisper.read_case' } }])
    expect(t.played).toEqual([{ bytes: 500, mime: 'audio/mpeg' }])
  })
  it.each([
    ['a sentence', 'Next, read the household record'],
    ['a path', '../../etc/passwd'],
    ['an empty id', ''],
    ['an id with capitals', 'Whisper.Read_case'],
    ['a very long id', `a.${'x'.repeat(100)}`],
  ])('does not speak %s: only line ids reach the agent', async (_l, id) => {
    const t = speakerRig()
    await t.sp.say(id)
    expect(t.calls).toEqual([])
    expect(t.played).toEqual([])
  })
  it('registerLine keeps no text on the wire: only the id is ever sent', async () => {
    const t = speakerRig()
    t.sp.registerLine('whisper.calc_a', 'Next, Run calculator A')
    t.sp.registerLine('not a line id', 'Zebulon Quillfeather')
    await t.sp.say('whisper.calc_a')
    expect(JSON.stringify(t.calls)).not.toContain('Run calculator')
    expect(JSON.stringify(t.calls)).not.toContain('Zebulon')
  })
  it.each([
    // D48: the Live experiment and the feature flag are on unless set to 0; spoken lines also need UNDERSTUDY_VOICE=1 (an explicit build flag).
    ['the Live flag off', { UNDERSTUDY_X_LIVE: '0', UNDERSTUDY_FLAG_VOICE: '1', UNDERSTUDY_VOICE: '1' }],
    ['the voice flag off', { UNDERSTUDY_X_LIVE: '1', UNDERSTUDY_FLAG_VOICE: '0', UNDERSTUDY_VOICE: '1' }],
    ['the build voice flag unset', { UNDERSTUDY_X_LIVE: '1', UNDERSTUDY_FLAG_VOICE: '1' }],
  ])('is silent with %s', async (_l, env) => {
    const t = speakerRig({ env })
    await t.sp.say('coach.almost')
    expect(t.calls).toEqual([])
  })
  it('is silent when the worker switched Cue voice off', async () => {
    const played: number[] = []
    const sp = createCueSpeaker({ env: ENV, agentUrl: 'http://127.0.0.1:7710', isLoopback: isLoopbackUrl, clip: { play: async () => void played.push(1), stop: () => undefined }, liveBusy: () => false, cueVoiceOn: () => false, fetchImpl: (async () => { throw new Error('no') }) as never })
    await sp.say('coach.almost')
    expect(played).toEqual([])
  })
  it('never overlaps a Gemini conversation: refuses while one is open, and drops a clip that arrives after one opened', async () => {
    const busy = speakerRig({ busy: () => true })
    await busy.sp.say('coach.almost')
    expect(busy.calls).toEqual([])
    let live = false
    const late = speakerRig({ busy: () => live })
    const p = late.sp.say('coach.almost')
    live = true // the worker pressed the talk key while the clip was on its way
    await p
    expect(late.played).toEqual([])
  })
  it('a stop (the talk key went down) cuts the clip now and cancels one in flight', async () => {
    const t = speakerRig()
    const p = t.sp.say('coach.almost')
    t.sp.stop()
    await p
    expect(t.stops()).toBe(1)
    expect(t.played).toEqual([])
  })
  it.each([
    ['silence from a disabled voice', { source: 'disabled' }],
    ['mock silence', { source: 'mock' }],
    ['a timeout', { source: 'timeout' }],
    ['an error', { source: 'error' }],
    ['a personal-data refusal', { source: 'personal_data' }],
    ['a 422', { status: 422 }],
    ['a body that is not audio', { mime: 'application/json' }],
    ['an empty body', { bytes: 0 }],
    ['a network failure', 'throw' as const],
  ])('plays nothing for %s and never throws', async (_l, response) => {
    const t = speakerRig({ response: response as never })
    await expect(t.sp.say('coach.almost')).resolves.toBeUndefined()
    expect(t.played).toEqual([])
  })
  it('only talks to the agent on this machine', () => {
    expect(() => createCueSpeaker({ env: ENV, agentUrl: 'https://example.com', isLoopback: isLoopbackUrl, clip: { play: async () => undefined, stop: () => undefined }, liveBusy: () => false })).toThrow(/this machine/)
  })
})
