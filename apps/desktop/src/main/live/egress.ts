// The ONE choke point. Everything that leaves this Mac in a voice session (microphone audio, screen frames, the few control messages) is
// sent from here and nowhere else: no other file holds a reference that can write to the socket, and a static test fails if one calls
// `.send(`. Here the gates run every time (consent, the kill switch, a denylisted app, secure input, never unattended: gates.ts), the cost
// caps are checked, a ledger row is written BEFORE any frame is sent and completed after, and the meter counts what went out.
//
//   audio    gated on the cached verdict (refreshed about every 500 ms; a stale verdict counts as closed). Chunks that are refused are dropped,
//            never buffered or replayed later.
//   frames   gated on a fresh verdict, announced to the ledger (the engine applies the same gate), sent only if allowed, then completed.
//            The JPEG buffers are zeroed in a finally, whatever happened. Frames are never written to disk and never logged.
//   control  text we wrote ourselves, tool results (closed JSON from our own code), audioStreamEnd, activity markers. They carry nothing
//            from the device, so they need only an open session and a live kill switch.
import { sha8Of, type LiveLedgerPort } from './ledger'
import type { GateVerdict } from './gates'
import type { SessionMeter } from './meter'
import { msg, pcmSeconds, silenceBase64 } from './wire'

export type SendResult = 'sent' | 'closed' | 'blocked' | 'ledger_refused' | 'cap' | 'stale'

// A frame older than this when it would be sent is dropped, never re-sent later: the model should see the screen as it is, not as it was.
export const FRAME_MAX_AGE_MS = 4000

/** One screen frame in memory. `release()` zeroes the bytes. */
export interface LiveFrame {
  jpeg: Buffer
  width: number
  height: number
  // When it was captured (ms, the same clock as the egress's). Without it the frame is treated as fresh.
  capturedAt?: number
  release(): void
}

export interface EgressDeps {
  conn: { send(m: object): boolean }
  gates: { audio(): GateVerdict; frames(): Promise<GateVerdict> }
  ledger: LiveLedgerPort
  meter: SessionMeter
  model: string
  now?: () => number
  // Something was refused. `reason` is a closed code (see gates.ts GateReason and ledger.ts LedgerRefusal), never content.
  onBlocked?: (kind: 'audio' | 'frames', reason: string) => void
  // The session or day cost cap is reached: nothing more leaves.
  capReached?: () => boolean
  killed?: () => boolean
  // 'transcribe' for Cue's one-answer turn; the audio ledger row says which.
  turnKind?: 'converse' | 'transcribe'
  // The first turn's ledger row was already announced (and allowed) at the key press, before anything was opened: its reference.
  firstTurn?: { ref: string | null }
}

// One worker turn of audio, ledgered: announced before the first chunk leaves, completed when the turn ends.
interface Turn {
  state: 'pending' | 'open' | 'refused'
  ref: string | null
  ops: Array<() => void>
  bytes: number
  seconds: number
  t0: number
  closing: boolean
}

const MAX_QUEUED_OPS = 160

export class LiveEgress {
  private isOpen = true
  private turn: Turn | null = null
  readonly counts = { audioChunks: 0, audioBlocked: 0, audioTurns: 0, frameBatches: 0, framesSent: 0, framesBlocked: 0 }

  constructor(private readonly d: EgressDeps) {
    if (d.firstTurn) {
      this.turn = { state: 'open', ref: d.firstTurn.ref, ops: [], bytes: 0, seconds: 0, t0: (d.now ?? Date.now)(), closing: false }
      this.counts.audioTurns += 1
    }
  }

  close(): void {
    this.isOpen = false
    // A turn in flight is completed in the ledger (what was sent was sent), best effort and without waiting.
    if (this.turn && this.turn.state === 'open') void this.finishTurn(this.turn)
    this.turn = null
  }

  /** The worker's turn is over: the ledger row for it is completed (after anything still queued behind its announcement has gone). */
  endTurn(): void {
    const t = this.turn
    if (!t) return
    if (t.state === 'pending') t.closing = true
    else {
      this.turn = null
      if (t.state === 'open') void this.finishTurn(t)
    }
  }

  private async finishTurn(t: Turn): Promise<void> {
    if (!t.ref) return
    await this.d.ledger.audioResult(t.ref, { ok: true, seconds: t.seconds, bytes: t.bytes, latency_ms: this.now() - t.t0 }).catch(() => undefined)
  }

  private sendAudioNow(b64: string): SendResult {
    if (!this.d.conn.send(msg.audio(b64))) return 'closed'
    this.counts.audioChunks += 1
    const secs = pcmSeconds(b64, 16000)
    this.d.meter.addAudioIn(secs)
    if (this.turn) {
      this.turn.seconds += secs
      this.turn.bytes += Math.floor((b64.length * 3) / 4)
    }
    return 'sent'
  }

  // Starts the turn's ledger row. Chunks and control messages wait behind it, in order; nothing leaves until it is allowed.
  private beginTurn(verdict: GateVerdict): Turn {
    const t: Turn = { state: 'pending', ref: null, ops: [], bytes: 0, seconds: 0, t0: this.now(), closing: false }
    this.turn = t
    this.counts.audioTurns += 1
    void (async () => {
      const ans = await this.d.ledger.announceAudio({ model: this.d.model, gate: verdict.gate, turn: this.d.turnKind ?? 'converse' }).catch(
        () => ({ allowed: false, reason: 'ledger_unavailable' as const, ref: null }),
      )
      if (!ans.allowed) {
        t.state = 'refused'
        t.ops = []
        this.counts.audioBlocked += 1
        this.d.onBlocked?.('audio', ans.reason ?? 'ledger_unavailable')
        return
      }
      t.ref = ans.ref
      t.state = 'open'
      const ops = t.ops
      t.ops = []
      if (this.isOpen && !(this.d.killed?.() ?? false)) for (const op of ops) op()
      if (t.closing) {
        if (this.turn === t) this.turn = null
        void this.finishTurn(t)
      }
    })()
    return t
  }

  get open(): boolean {
    return this.isOpen
  }

  private now(): number {
    return (this.d.now ?? Date.now)()
  }

  /** One base64 PCM16 16 kHz chunk of the worker's voice. */
  audio(b64: string): SendResult {
    if (!this.isOpen) return 'closed'
    if (this.d.killed?.()) return 'blocked'
    if (this.d.capReached?.()) return 'cap'
    const v = this.d.gates.audio()
    if (!v.open) {
      this.counts.audioBlocked += 1
      this.d.onBlocked?.('audio', v.reason ?? 'stale')
      return 'blocked'
    }
    const t = this.turn ?? this.beginTurn(v)
    if (t.state === 'refused') return 'blocked'
    if (t.state === 'pending') {
      // The cap is looked at again when the queue is released: chunks that waited for the ledger do not slip past it.
      if (t.ops.length < MAX_QUEUED_OPS) t.ops.push(() => void (this.d.capReached?.() ? undefined : this.sendAudioNow(b64)))
      return 'sent'
    }
    return this.sendAudioNow(b64)
  }

  /** Silence (no device content) after the last word, so the server's end-of-speech detector fires. Gated like audio. */
  silence(ms: number): SendResult {
    return this.audio(silenceBase64(ms))
  }

  /** A control message we built from our own code: audioStreamEnd, activity markers, our own text, a tool result. */
  control(message: object): SendResult {
    if (!this.isOpen) return 'closed'
    if (this.d.killed?.()) return 'blocked'
    // Behind an announcement that has not been answered, a control message keeps its place in line (the stream end must follow the audio).
    if (this.turn?.state === 'pending') {
      if (this.turn.ops.length < MAX_QUEUED_OPS) this.turn.ops.push(() => void this.d.conn.send(message))
      return 'sent'
    }
    return this.d.conn.send(message) ? 'sent' : 'closed'
  }

  /** A batch of frames. The ledger row is written before the first byte is sent. The buffers are zeroed afterwards, always. */
  async frames(batch: readonly LiveFrame[]): Promise<SendResult> {
    try {
      if (batch.length === 0) return 'sent'
      if (!this.isOpen) return 'closed'
      if (this.d.killed?.()) return 'blocked'
      if (this.d.capReached?.()) return 'cap'
      const fresh = (): boolean => batch.every((f) => f.capturedAt === undefined || this.now() - f.capturedAt <= FRAME_MAX_AGE_MS)
      if (!fresh()) return 'stale'
      const verdict = await this.d.gates.frames()
      if (!verdict.open) {
        this.counts.framesBlocked += batch.length
        this.d.onBlocked?.('frames', verdict.reason ?? 'stale')
        return 'blocked'
      }
      const first = batch[0]!
      const bytes = batch.reduce((n, f) => n + f.jpeg.length, 0)
      const ans = await this.d.ledger.announce({ count: batch.length, bytes, sha8: sha8Of(first.jpeg), width: first.width, height: first.height, model: this.d.model, gate: verdict.gate })
      if (!ans.allowed || !ans.ref) {
        this.counts.framesBlocked += batch.length
        this.d.onBlocked?.('frames', ans.reason ?? 'ledger_unavailable')
        return 'ledger_refused'
      }
      // The awaits above may have outlived the session or the kill switch: check again before anything is sent.
      let ok = this.isOpen && !(this.d.killed?.() ?? false)
      const t0 = this.now()
      // Slow gates or a slow ledger may have made the frame old: then it is dropped (the row says it was not sent), never held for later.
      const stale = ok && !fresh()
      if (stale) ok = false
      if (ok) for (const f of batch) ok = this.d.conn.send(msg.video(f.jpeg.toString('base64'))) && ok
      await this.d.ledger.result(ans.ref, { ok, latency_ms: this.now() - t0, cost_estimate_usd: this.d.meter.frameCost(batch.length) }).catch(() => undefined)
      if (!ok) return stale ? 'stale' : 'closed'
      this.counts.frameBatches += 1
      this.counts.framesSent += batch.length
      this.d.meter.addFrames(batch.length, bytes)
      return 'sent'
    } finally {
      for (const f of batch) f.release()
    }
  }
}
