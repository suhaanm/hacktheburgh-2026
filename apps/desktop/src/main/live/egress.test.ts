import { describe, expect, it } from 'vitest'
import { LiveEgress, type LiveFrame } from './egress'
import { createMemoryLiveLedger } from './ledger'
import { SessionMeter, pricesFromEnv } from './meter'
import { chunks32ms, openVerdict, tonePcm, waitFor } from './live.test-util'
import type { GateVerdict } from './gates'

function setup(over: { audio?: GateVerdict; frames?: GateVerdict; killed?: boolean; cap?: boolean; preTurn?: boolean } = {}) {
  const sent: any[] = []
  const state = { audio: over.audio ?? openVerdict(), frames: over.frames ?? openVerdict(), killed: over.killed ?? false, cap: over.cap ?? false, conn: true }
  const ledger = createMemoryLiveLedger()
  const blocked: string[] = []
  const meter = new SessionMeter(pricesFromEnv({}))
  const eg = new LiveEgress({
    conn: { send: (m) => (state.conn ? (sent.push(m), true) : false) },
    gates: { audio: () => state.audio, frames: async () => state.frames },
    ledger,
    meter,
    model: 'm1',
    killed: () => state.killed,
    capReached: () => state.cap,
    // preTurn: the turn's row was announced at the key press, so audio goes straight out
    ...(over.preTurn ? { firstTurn: { ref: 'e_000000000000' } } : {}),
    onBlocked: (k, r) => void blocked.push(`${k}:${r}`),
  })
  return { eg, sent, state, ledger, blocked, meter }
}

const frame = (n = 100, capturedAt?: number): LiveFrame & { buf: Buffer } => {
  const buf = Buffer.alloc(n, 7)
  return { jpeg: buf, buf, width: 800, height: 450, ...(capturedAt !== undefined ? { capturedAt } : {}), release: () => buf.fill(0) }
}

describe('audio through the choke point', () => {
  it('goes only while the gate is open, the kill switch is off and the cap has room; refused chunks are dropped, never replayed', async () => {
    const t = setup({ preTurn: true })
    const [c1, c2, c3, c4] = chunks32ms(tonePcm(0.2))
    expect(t.eg.audio(c1!)).toBe('sent')
    t.state.audio = openVerdict({ open: false, reason: 'secure_input' })
    expect(t.eg.audio(c2!)).toBe('blocked')
    t.state.audio = openVerdict()
    t.state.cap = true
    expect(t.eg.audio(c3!)).toBe('cap')
    t.state.cap = false
    t.state.killed = true
    expect(t.eg.audio(c4!)).toBe('blocked')
    t.state.killed = false
    expect(t.sent).toHaveLength(1)
    expect(t.blocked).toEqual(['audio:secure_input'])
    t.eg.close()
    expect(t.eg.audio(c1!)).toBe('closed')
    expect(t.sent).toHaveLength(1)
  })
  it('counts what it sent in the meter', () => {
    const t = setup({ preTurn: true })
    for (const c of chunks32ms(tonePcm(1))) t.eg.audio(c)
    expect(t.meter.audioInSeconds).toBeCloseTo(1, 1)
  })
  it('a closed connection is not a send', () => {
    const t = setup({ preTurn: true })
    t.state.conn = false
    expect(t.eg.audio(chunks32ms(tonePcm(0.05))[0]!)).toBe('closed')
  })
  it('with an audio ledger, nothing leaves until the turn is announced, and control messages keep their place in line', async () => {
    const t = setup()
    const order: string[] = []
    t.ledger.announceAudio = async (x) => {
      order.push('announce')
      await new Promise((r) => setTimeout(r, 20))
      return { allowed: true, reason: null, ref: 'e_000000000001' }
    }
    const chunks = chunks32ms(tonePcm(0.1))
    for (const c of chunks) t.eg.audio(c)
    t.eg.control({ realtimeInput: { audioStreamEnd: true } })
    expect(t.sent).toHaveLength(0) // all of it waits behind the announcement
    await waitFor(() => t.sent.length === chunks.length + 1)
    expect(t.sent[t.sent.length - 1]).toEqual({ realtimeInput: { audioStreamEnd: true } }) // the stream end follows the audio
    expect(order).toEqual(['announce'])
  })
  it('a refused turn sends nothing, drops what was queued, and reports why once', async () => {
    const t = setup()
    t.ledger.refuse('denylisted_app')
    const chunks = chunks32ms(tonePcm(0.1))
    for (const c of chunks) t.eg.audio(c)
    await waitFor(() => t.blocked.length > 0)
    expect(t.sent).toHaveLength(0)
    expect(t.eg.audio(chunks[0]!)).toBe('blocked') // the rest of that turn is refused too
    expect(t.blocked).toEqual(['audio:denylisted_app'])
  })
  it('completes the turn row with seconds and bytes when the turn ends, and starts a new row for the next turn', async () => {
    const t = setup()
    for (const c of chunks32ms(tonePcm(0.5))) t.eg.audio(c)
    await waitFor(() => t.sent.length > 10)
    t.eg.endTurn()
    await waitFor(() => t.ledger.audioResults.length === 1)
    expect(t.ledger.audioResults[0]!.result.seconds).toBeCloseTo(0.5, 1)
    for (const c of chunks32ms(tonePcm(0.1))) t.eg.audio(c)
    await waitFor(() => t.ledger.audioAnnounced.length === 2)
  })
  it('the control path (our own text, tool results) needs an open session and a live kill switch, nothing more', () => {
    const t = setup()
    expect(t.eg.control({ a: 1 })).toBe('sent')
    t.state.killed = true
    expect(t.eg.control({ a: 2 })).toBe('blocked')
    t.state.killed = false
    t.eg.close()
    expect(t.eg.control({ a: 3 })).toBe('closed')
  })
})

describe('frames through the choke point', () => {
  it('announce first, send only if allowed, complete the row, and zero the bytes afterwards', async () => {
    const t = setup()
    const f = frame(5000)
    expect(await t.eg.frames([f])).toBe('sent')
    expect(t.ledger.announced).toEqual([{ count: 1, bytes: 5000, sha8: expect.stringMatching(/^[0-9a-f]{16}$/), width: 800, height: 450, model: 'm1', gate: { consent: true, denylisted_app: false, secure_input: false, unattended: false } }])
    expect(t.sent).toHaveLength(1)
    expect(t.sent[0]!.realtimeInput.video.mimeType).toBe('image/jpeg')
    expect(t.ledger.results).toHaveLength(1)
    expect(t.ledger.results[0]!.result.ok).toBe(true)
    expect(f.buf.every((b) => b === 0)).toBe(true)
    expect(t.meter.frames).toBe(1)
  })
  it('writes the ledger row before the first byte leaves', async () => {
    const t = setup()
    let sentAtAnnounce = -1
    const orig = t.ledger.announce.bind(t.ledger)
    t.ledger.announce = async (b) => {
      sentAtAnnounce = t.sent.length
      return orig(b)
    }
    await t.eg.frames([frame()])
    expect(sentAtAnnounce).toBe(0)
  })
  it.each([
    ['a closed gate', { frames: openVerdict({ open: false, reason: 'denylisted_app' }) }, 'blocked'],
    ['the kill switch', { killed: true }, 'blocked'],
    ['a reached cap', { cap: true }, 'cap'],
  ] as const)('sends nothing on %s, and still zeroes the frame', async (_l, over, result) => {
    const t = setup(over as never)
    const f = frame()
    expect(await t.eg.frames([f])).toBe(result)
    expect(t.sent).toHaveLength(0)
    expect(t.ledger.announced).toHaveLength(0)
    expect(f.buf.every((b) => b === 0)).toBe(true)
  })
  it('sends nothing when the ledger refuses, and says why', async () => {
    const t = setup()
    t.ledger.refuse('unattended')
    const f = frame()
    expect(await t.eg.frames([f])).toBe('ledger_refused')
    expect(t.sent).toHaveLength(0)
    expect(t.blocked).toEqual(['frames:unattended'])
    expect(f.buf.every((b) => b === 0)).toBe(true)
  })
  it('does not send after the session closed while the ledger was being asked', async () => {
    const t = setup()
    const orig = t.ledger.announce.bind(t.ledger)
    t.ledger.announce = async (b) => {
      t.eg.close()
      return orig(b)
    }
    const f = frame()
    expect(await t.eg.frames([f])).toBe('closed')
    expect(t.sent).toHaveLength(0)
    expect(f.buf.every((b) => b === 0)).toBe(true)
  })
  it('a batch is one row: count, total bytes, and the hash of the first frame', async () => {
    const t = setup()
    await t.eg.frames([frame(100), frame(200), frame(300)])
    expect(t.ledger.announced[0]).toMatchObject({ count: 3, bytes: 600, width: 800, height: 450 })
    expect(t.sent).toHaveLength(3)
  })
  it('drops a frame that is older than a few seconds when it would be sent, instead of re-sending it later', async () => {
    const t = setup()
    const f = frame(100, Date.now() - 10_000)
    expect(await t.eg.frames([f])).toBe('stale')
    expect(t.sent).toHaveLength(0)
    expect(t.ledger.announced).toHaveLength(0) // not even announced
    expect(f.buf.every((b) => b === 0)).toBe(true)
    expect(await t.eg.frames([frame(100, Date.now() - 500)])).toBe('sent') // a fresh one goes
  })
  it('a frame that went stale while the ledger was being asked is dropped and the row says it was not sent', async () => {
    const t = setup()
    const orig = t.ledger.announce.bind(t.ledger)
    t.ledger.announce = async (b) => {
      await new Promise((r) => setTimeout(r, 30))
      return orig(b)
    }
    const f = frame(100, Date.now() - 3990)
    expect(await t.eg.frames([f])).toBe('stale')
    expect(t.sent).toHaveLength(0)
    expect(t.ledger.results).toHaveLength(1)
    expect(t.ledger.results[0]!.result.ok).toBe(false)
  })
  it('an empty batch is nothing', async () => {
    const t = setup()
    expect(await t.eg.frames([])).toBe('sent')
    expect(t.ledger.announced).toHaveLength(0)
  })
})
