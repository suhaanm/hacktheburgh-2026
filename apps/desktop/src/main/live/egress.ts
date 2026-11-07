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

export type SendResult = 'sent' | 'closed' | 'blocked' | 'ledger_refused' | 'cap'

/** One screen frame in memory. `release()` zeroes the bytes. */
export interface LiveFrame {
  jpeg: Buffer
  width: number
  height: number
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
}

export class LiveEgress {
  private isOpen = true
  readonly counts = { audioChunks: 0, audioBlocked: 0, frameBatches: 0, framesSent: 0, framesBlocked: 0 }

  constructor(private readonly d: EgressDeps) {}

  close(): void {
    this.isOpen = false
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
    if (!this.d.conn.send(msg.audio(b64))) return 'closed'
    this.counts.audioChunks += 1
    this.d.meter.addAudioIn(pcmSeconds(b64, 16000))
    return 'sent'
  }

  /** Silence (no device content) after the last word, so the server's end-of-speech detector fires. Gated like audio. */
  silence(ms: number): SendResult {
    return this.audio(silenceBase64(ms))
  }

  /** A control message we built from our own code: audioStreamEnd, activity markers, our own text, a tool result. */
  control(message: object): SendResult {
    if (!this.isOpen) return 'closed'
    if (this.d.killed?.()) return 'blocked'
    return this.d.conn.send(message) ? 'sent' : 'closed'
  }

  /** A batch of frames. The ledger row is written before the first byte is sent. The buffers are zeroed afterwards, always. */
  async frames(batch: readonly LiveFrame[]): Promise<SendResult> {
    try {
      if (batch.length === 0) return 'sent'
      if (!this.isOpen) return 'closed'
      if (this.d.killed?.()) return 'blocked'
      if (this.d.capReached?.()) return 'cap'
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
      if (ok) for (const f of batch) ok = this.d.conn.send(msg.video(f.jpeg.toString('base64'))) && ok
      await this.d.ledger.result(ans.ref, { ok, latency_ms: this.now() - t0, cost_estimate_usd: this.d.meter.frameCost(batch.length) }).catch(() => undefined)
      if (!ok) return 'closed'
      this.counts.frameBatches += 1
      this.counts.framesSent += batch.length
      this.d.meter.addFrames(batch.length, bytes)
      return 'sent'
    } finally {
      for (const f of batch) f.release()
    }
  }
}
