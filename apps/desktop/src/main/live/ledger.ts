// The ledger port for live frames: one row per batch, written BEFORE the frames are sent, completed after. The authoritative ledger is the
// engine's privacy ledger (POST /privacy/ledger/live, then /live/result); it applies the same gate again, so a batch the engine refuses
// is never sent. A row holds: count, total bytes, the first 16 hex characters of the first frame's SHA-256, width and height of that
// frame, the model id, the four gate booleans, then latency, ok, tokens and a cost estimate. Never the image, never audio, never a transcript.
//
// Fail closed: if the engine is not reachable, the privacy extension is off (404), or the ledger cannot be written (503), the answer is
// "not allowed" and the frames stay home. The conversation itself carries on by voice alone.
import { createHash } from 'node:crypto'
import type { GateBooleans } from './gates'

export interface LiveBatch {
  count: number
  bytes: number
  sha8: string
  width: number
  height: number
  model: string
  gate: GateBooleans
}

export interface BatchResult {
  ok: boolean
  latency_ms: number
  input_tokens?: number
  output_tokens?: number
  cost_estimate_usd?: number
}

export type LedgerRefusal = 'unattended' | 'secure_input' | 'denylisted_app' | 'no_consent' | 'ledger_unavailable'

export interface LedgerAnswer {
  allowed: boolean
  reason: LedgerRefusal | null
  ref: string | null
}

// One worker turn of audio (one talk-key press): announced before the first chunk is sent, completed when the turn ends. No content.
export interface AudioTurn {
  model: string
  gate: GateBooleans
  turn: 'converse' | 'transcribe'
}

export interface AudioTurnResult {
  ok: boolean
  seconds: number
  bytes: number
  latency_ms?: number
  cost_estimate_usd?: number
}

export interface LiveLedgerPort {
  announce(b: LiveBatch): Promise<LedgerAnswer>
  result(ref: string, r: BatchResult): Promise<void>
  /** Required: audio is ledgered per turn before it is sent. A route that is missing is `ledger_unavailable` (fail closed), never a pass-through. */
  announceAudio(t: AudioTurn): Promise<LedgerAnswer>
  audioResult(ref: string, r: AudioTurnResult): Promise<void>
}

/** The first 8 bytes of the SHA-256, as 16 lowercase hex characters: identifies a frame in the ledger without being any of it. */
export const sha8Of = (jpeg: Uint8Array): string => createHash('sha256').update(jpeg).digest('hex').slice(0, 16)

const MODEL_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$/
const REASONS = new Set(['unattended', 'secure_input', 'denylisted_app', 'no_consent'])
const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)

export interface HttpLedgerOptions {
  engineUrl: string
  isLoopback: (url: string) => boolean
  fetchImpl?: typeof fetch
  timeoutMs?: number
}

export function createHttpLiveLedger(o: HttpLedgerOptions): LiveLedgerPort {
  if (!o.isLoopback(o.engineUrl)) throw new Error('the ledger service must be on this machine (127.0.0.1)')
  const base = o.engineUrl.replace(/\/+$/, '')
  const doFetch = o.fetchImpl ?? ((i, init) => fetch(i, init))
  async function post(pathname: string, body: unknown): Promise<{ status: number; json: unknown } | null> {
    const ctl = new AbortController()
    const timer = setTimeout(() => ctl.abort(), o.timeoutMs ?? 2500)
    try {
      const res = await doFetch(`${base}${pathname}`, { method: 'POST', headers: { 'content-type': 'application/json', 'x-understudy-actor': 'worker' }, body: JSON.stringify(body), signal: ctl.signal })
      let json: unknown = null
      try {
        json = await res.json()
      } catch {
        json = null
      }
      return { status: res.status, json }
    } catch {
      return null
    } finally {
      clearTimeout(timer)
    }
  }
  return {
    async announce(b) {
      if (!MODEL_RE.test(b.model)) return { allowed: false, reason: 'ledger_unavailable', ref: null }
      // Exactly the documented fields (any extra one is a 422 on the other side); no latency, so this is an announcement.
      const r = await post('/privacy/ledger/live', {
        count: b.count,
        bytes: b.bytes,
        sha8: b.sha8,
        width: b.width,
        height: b.height,
        model: b.model,
        source: 'real_screen',
        provider: 'gemini',
        gate: { consent: b.gate.consent, denylisted_app: b.gate.denylisted_app, secure_input: b.gate.secure_input, unattended: b.gate.unattended },
      })
      if (!r || r.status !== 200 || !isObj(r.json)) return { allowed: false, reason: 'ledger_unavailable', ref: null }
      const reason = typeof r.json.reason === 'string' && REASONS.has(r.json.reason) ? (r.json.reason as LedgerRefusal) : null
      if (r.json.allowed !== true) return { allowed: false, reason: reason ?? 'ledger_unavailable', ref: null }
      const ref = typeof r.json.ledger_id === 'string' && /^e_[0-9a-f]{12,32}$/.test(r.json.ledger_id) ? r.json.ledger_id : null
      return ref ? { allowed: true, reason: null, ref } : { allowed: false, reason: 'ledger_unavailable', ref: null }
    },
    async announceAudio(t) {
      if (!MODEL_RE.test(t.model)) return { allowed: false, reason: 'ledger_unavailable', ref: null }
      const r = await post('/privacy/ledger/live/audio', {
        model: t.model,
        source: 'real_screen',
        provider: 'gemini',
        gate: { consent: t.gate.consent, denylisted_app: t.gate.denylisted_app, secure_input: t.gate.secure_input, unattended: t.gate.unattended },
        turn: t.turn,
      })
      // No answer, a 404 (an engine without the route, or the privacy extension off), a 503 or anything but a 200: the audio stays home.
      if (!r || r.status !== 200 || !isObj(r.json)) return { allowed: false, reason: 'ledger_unavailable', ref: null }
      const reason = typeof r.json.reason === 'string' && REASONS.has(r.json.reason) ? (r.json.reason as LedgerRefusal) : null
      if (r.json.allowed !== true) return { allowed: false, reason: reason ?? 'ledger_unavailable', ref: null }
      const ref = typeof r.json.ledger_id === 'string' && /^e_[0-9a-f]{12,32}$/.test(r.json.ledger_id) ? r.json.ledger_id : null
      return ref ? { allowed: true, reason: null, ref } : { allowed: false, reason: 'ledger_unavailable', ref: null }
    },
    async audioResult(ref, res) {
      await post('/privacy/ledger/live/audio/result', {
        ref,
        ok: res.ok,
        seconds: Math.round(Math.min(600, Math.max(0, res.seconds)) * 10) / 10,
        bytes: Math.max(0, Math.round(res.bytes)),
        ...(res.latency_ms !== undefined ? { latency_ms: Math.max(0, Math.round(res.latency_ms)) } : {}),
        ...(res.cost_estimate_usd !== undefined ? { cost_estimate_usd: Math.round(res.cost_estimate_usd * 1e6) / 1e6 } : {}),
      })
    },
    async result(ref, res) {
      await post('/privacy/ledger/live/result', {
        ref,
        ok: res.ok,
        latency_ms: Math.max(0, Math.round(res.latency_ms)),
        ...(res.input_tokens !== undefined ? { input_tokens: Math.round(res.input_tokens) } : {}),
        ...(res.output_tokens !== undefined ? { output_tokens: Math.round(res.output_tokens) } : {}),
        ...(res.cost_estimate_usd !== undefined ? { cost_estimate_usd: Math.round(res.cost_estimate_usd * 1e6) / 1e6 } : {}),
      })
    },
  }
}

// ------------------------------------------------------------------------------------------------ in-memory (tests and mock mode)
export interface MemoryLiveLedger extends LiveLedgerPort {
  readonly announced: LiveBatch[]
  readonly results: Array<{ ref: string; result: BatchResult }>
  readonly audioAnnounced: AudioTurn[]
  readonly audioResults: Array<{ ref: string; result: AudioTurnResult }>
  /** Refuse the next batches with this reason (null: allow). */
  refuse(reason: LedgerRefusal | null): void
}

export function createMemoryLiveLedger(): MemoryLiveLedger {
  const announced: LiveBatch[] = []
  const results: Array<{ ref: string; result: BatchResult }> = []
  const audioAnnounced: AudioTurn[] = []
  const audioResults: Array<{ ref: string; result: AudioTurnResult }> = []
  let refusal: LedgerRefusal | null = null
  let n = 0
  return {
    announced,
    results,
    audioAnnounced,
    audioResults,
    refuse: (r) => void (refusal = r),
    async announceAudio(t) {
      audioAnnounced.push({ ...t, gate: { ...t.gate } })
      if (refusal) return { allowed: false, reason: refusal, ref: null }
      n += 1
      return { allowed: true, reason: null, ref: `e_${n.toString(16).padStart(12, '0')}` }
    },
    async audioResult(ref, r) {
      audioResults.push({ ref, result: { ...r } })
    },
    async announce(b) {
      announced.push({ ...b, gate: { ...b.gate } })
      if (refusal) return { allowed: false, reason: refusal, ref: null }
      n += 1
      return { allowed: true, reason: null, ref: `e_${n.toString(16).padStart(12, '0')}` }
    },
    async result(ref, r) {
      results.push({ ref, result: { ...r } })
    },
  }
}
