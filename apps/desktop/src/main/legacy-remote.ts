// LEGACY REMOTE PATHS: one switch, one gate, one ledger row per request (REQ-7, owner decision D38, review finding H6).
//
// The old Alongside TypeScript code can send a screenshot, a frame, a file's text or audio to OpenAI or Gemini from this app:
//   main/model-port/openai.ts                 the model port's only network code (grounder, verifier, scam analyst, lesson architect,
//                                             act-for-me and the coach agents all reach the network through it)
//   main/gemini/client.ts                     the Gemini Interactions call path (file extraction)
//   main/files/embed.ts and extract.ts        file text to the embedding and reading models
//   main/live-auth.ts                         the ephemeral token for the wake-word spotter, whose microphone stream starts in a renderer
// None of them is on the Understudy demo path (coach, cue, awareness, agent runs and dashboards use the engine, the agent service and
// the main-process Live and glance code, which have their own gates and ledger rows). They are kept so the old features still work for
// the owner who wants them, and they are DEFAULT OFF:
//
//     UNDERSTUDY_LEGACY_REMOTE=1      the ONE flag. Unset (or anything but "1"): none of the paths above can make a network request.
//                                     The check happens before any client is built, so nothing is opened and nothing is queued.
//
// With the flag ON, every request still has to pass `authorize()` first, which:
//   1. applies the same gates as the privacy ImageGate (services/engine/understudy_engine/privacy/image.py), computed here from the same
//      probes the awareness layer uses: consent, denylisted frontmost app, macOS secure input, unattended (the worker is away).
//      Precedence: unattended, secure input, denylisted app, no consent. These calls carry source `real_screen`, so an unattended
//      call is ALWAYS refused (there is no sandbox exception: nothing here can tell a sandbox page from the worker's own screen).
//      Consent: an image needs the worker's glance consent (the awareness consent card); audio needs the voice consent; file text and
//      plain text rely on this flag, which is the owner's launch-time opt-in. Unknown frontmost app or secure-input state counts as a
//      block for images and audio when the worker keeps strict mode on (the default).
//   2. announces the request to the engine BEFORE sending it: POST /privacy/ledger/direct with metadata only (kind, purpose, provider,
//      model, bytes, count, source, the four gate booleans; never content). The engine applies the gate again. The request is made only
//      when the reply is 200 with `allowed: true` and a ledger id. A refusal (200, allowed false), a 503 (ledger unwritable), a network
//      failure, a 404 (privacy extension off) or anything unreadable means NO request. Fail closed.
//   3. the caller reports the outcome (latency, ok, bytes, tokens) to POST /privacy/ledger/direct/result through the ticket.
//
// What this cannot do: audio and microphone streams that start in a renderer are gated only at the token (a row says a wake session was
// authorised, not how much sound followed). The wake spotter is off unless UNDERSTUDY_FLAG_WAKE=1 as well.
import { isLoopbackUrl } from './engine/endpoints'
import { appKindFor, decideApp } from './awareness/denylist'
import type { ConsoleProbe, FrontmostSource } from './awareness/probes'

export const LEGACY_REMOTE_FLAG = 'UNDERSTUDY_LEGACY_REMOTE'

type Env = Record<string, string | undefined>

export const legacyRemoteOn = (env: Env = process.env): boolean => env[LEGACY_REMOTE_FLAG] === '1'

export type LegacyKind = 'image' | 'audio' | 'file_text' | 'text'
export type LegacyProvider = 'openai' | 'gemini'

/** What is known about one request before it leaves: metadata only, never content. */
export interface LegacyCall {
  kind: LegacyKind
  // A short dotted id (letters, digits and underscores), e.g. legacy.port_vision. Build one with purposeId().
  purpose: string
  provider: LegacyProvider
  // The model id the request names (read from the environment by the caller).
  model: string
  bytes: number
  // Items in the request: images, chunks, files or 1.
  count: number
  // Always real_screen unless the caller can prove a sandbox; there is no such caller today.
  source?: 'real_screen' | 'sandbox'
}

export type LegacyRefusal = 'flag_off' | 'killed' | 'unattended' | 'secure_input' | 'denylisted_app' | 'no_consent' | 'ledger_unavailable' | 'bad_call'

const PLAIN: Record<LegacyRefusal, string> = {
  flag_off: 'The old cloud helpers are switched off on this Mac.',
  killed: 'Everything is stopped, so nothing was sent.',
  unattended: 'You are away, so nothing was sent.',
  secure_input: 'A password field has focus, so nothing was sent.',
  denylisted_app: 'An app on the skip list is in front, so nothing was sent.',
  no_consent: 'You have not agreed to this being sent, so nothing was sent.',
  ledger_unavailable: 'The privacy ledger could not be written, so nothing was sent.',
  bad_call: 'That request could not be described to the privacy ledger, so nothing was sent.',
}

export class LegacyRemoteBlocked extends Error {
  constructor(public readonly reason: LegacyRefusal) {
    super(`legacy remote call refused: ${reason}`)
    this.name = 'LegacyRemoteBlocked'
  }
  get userMessage(): string {
    return PLAIN[this.reason]
  }
}

export interface LegacyOutcome {
  ok: boolean
  latencyMs: number
  bytes?: number
  inputTokens?: number
  outputTokens?: number
}

export interface LegacyTicket {
  /** Report how the request ended (best effort; never throws). */
  finish(o: LegacyOutcome): void
}

export interface LegacyRemoteGate {
  /** Resolves with a ticket only when the request may be made. Throws LegacyRemoteBlocked otherwise. */
  authorize(call: LegacyCall): Promise<LegacyTicket>
}

export interface GateBooleans {
  consent: boolean
  denylisted_app: boolean
  secure_input: boolean
  unattended: boolean
}

const NOOP_TICKET: LegacyTicket = { finish: () => undefined }

/** A gate that allows everything and writes nothing. Tests only (named so it cannot be picked up by accident). */
export const ALLOW_ALL_FOR_TESTS: LegacyRemoteGate = { authorize: async () => NOOP_TICKET }

// ------------------------------------------------------------------------------------------------ helpers for callers
const PURPOSE_RE = /^[a-z][a-z0-9_]{1,30}(?:\.[a-z][a-z0-9_]{1,30}){0,2}$/
const PROVIDER_RE = /^[a-z][a-z0-9_-]{1,23}$/
const MODEL_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$/
const REASONS = new Set<LegacyRefusal>(['unattended', 'secure_input', 'denylisted_app', 'no_consent'])

/** `legacy.<name>` with the name squeezed into the ledger's purpose alphabet (a call name such as "grounder.primary" works). */
export function purposeId(name: string): string {
  const s = name.toLowerCase().replace(/[^a-z0-9_]+/g, '_').replace(/^_+|_+$/g, '').replace(/^[0-9]+/, '').slice(0, 30)
  return `legacy.${s.length >= 2 ? s : 'call'}`
}

const utf8 = (s: string | undefined): number => (s ? Buffer.byteLength(s, 'utf8') : 0)
/** Decoded size of a base64 string (no allocation). */
export const base64Bytes = (b64: string): number => Math.max(0, Math.floor((b64.length * 3) / 4) - (b64.endsWith('==') ? 2 : b64.endsWith('=') ? 1 : 0))

/** The metadata of a model-port completion: images count as image bytes, everything else as text bytes. */
export function measureCompletion(req: { text: string; system?: string; images?: ReadonlyArray<{ jpegBase64: string }> }): Pick<LegacyCall, 'kind' | 'bytes' | 'count'> {
  const images = req.images ?? []
  const text = utf8(req.text) + utf8(req.system)
  if (images.length === 0) return { kind: 'text', bytes: text, count: 1 }
  return { kind: 'image', bytes: text + images.reduce((n, i) => n + base64Bytes(i.jpegBase64), 0), count: images.length }
}

// ------------------------------------------------------------------------------------------------ the gate
export interface LegacyGateOptions {
  env?: Env
  // The engine (loopback only).
  engineUrl: string
  // The four booleans for this request. Throws or rejects mean "closed" (fail closed).
  gates: (call: LegacyCall) => Promise<GateBooleans>
  killed?: () => boolean
  fetchImpl?: typeof fetch
  timeoutMs?: number
  log?: (scope: string, ...args: unknown[]) => void
}

/** The precedence of privacy/image.py for real_screen: unattended, secure input, denylisted app, then consent. */
export function localReason(g: GateBooleans): LegacyRefusal | null {
  if (g.unattended) return 'unattended'
  if (g.secure_input) return 'secure_input'
  if (g.denylisted_app) return 'denylisted_app'
  if (!g.consent) return 'no_consent'
  return null
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)

export function createLegacyRemoteGate(o: LegacyGateOptions): LegacyRemoteGate {
  const env = o.env ?? process.env
  if (!isLoopbackUrl(o.engineUrl)) throw new Error('the ledger service must be on this machine (127.0.0.1)')
  const base = o.engineUrl.replace(/\/+$/, '')
  const doFetch = o.fetchImpl ?? ((i, init) => fetch(i, init))
  const log = o.log ?? (() => undefined)

  async function post(path: string, body: unknown): Promise<{ status: number; json: unknown } | null> {
    const ctl = new AbortController()
    const timer = setTimeout(() => ctl.abort(), o.timeoutMs ?? 2500)
    try {
      // The main process, no Origin header, the worker actor: the only caller the engine's report routes accept.
      const res = await doFetch(`${base}${path}`, { method: 'POST', headers: { 'content-type': 'application/json', 'x-understudy-actor': 'worker' }, body: JSON.stringify(body), signal: ctl.signal })
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
    async authorize(call) {
      if (!legacyRemoteOn(env)) throw new LegacyRemoteBlocked('flag_off') // before anything else: no probe, no request
      if (o.killed?.()) throw new LegacyRemoteBlocked('killed')
      const source = call.source ?? 'real_screen'
      const valid =
        PURPOSE_RE.test(call.purpose) &&
        PROVIDER_RE.test(call.provider) &&
        MODEL_RE.test(call.model) &&
        Number.isInteger(call.bytes) &&
        call.bytes >= 0 &&
        Number.isInteger(call.count) &&
        call.count >= 1
      if (!valid) throw new LegacyRemoteBlocked('bad_call')
      let gate: GateBooleans
      try {
        gate = await o.gates(call)
      } catch {
        gate = { consent: false, denylisted_app: false, secure_input: false, unattended: true } // an unreadable state is a closed gate
      }
      const local = localReason(gate)
      // Announce before sending. A closed gate is announced too so the refusal is on the ledger (the engine writes one blocked row).
      const r = await post('/privacy/ledger/direct', {
        kind: call.kind,
        purpose: call.purpose,
        provider: call.provider,
        model: call.model,
        bytes: call.bytes,
        count: call.count,
        source,
        gate: { consent: gate.consent, denylisted_app: gate.denylisted_app, secure_input: gate.secure_input, unattended: gate.unattended },
      })
      if (local) throw new LegacyRemoteBlocked(local)
      if (!r || r.status !== 200 || !isObj(r.json)) throw new LegacyRemoteBlocked('ledger_unavailable') // 503, 404 (extension off), 422, no engine
      if (r.json.allowed !== true) {
        const why = typeof r.json.reason === 'string' && REASONS.has(r.json.reason as LegacyRefusal) ? (r.json.reason as LegacyRefusal) : 'ledger_unavailable'
        throw new LegacyRemoteBlocked(why)
      }
      const ref = typeof r.json.ledger_id === 'string' && /^e_[0-9a-f]{12,32}$/.test(r.json.ledger_id) ? r.json.ledger_id : null
      if (!ref) throw new LegacyRemoteBlocked('ledger_unavailable')
      return {
        finish(out) {
          void post('/privacy/ledger/direct/result', {
            ref,
            ok: out.ok,
            latency_ms: Math.max(0, Math.min(3_600_000, Math.round(out.latencyMs))),
            ...(out.bytes !== undefined ? { bytes: Math.max(0, Math.round(out.bytes)) } : {}),
            ...(out.inputTokens !== undefined ? { input_tokens: Math.max(0, Math.round(out.inputTokens)) } : {}),
            ...(out.outputTokens !== undefined ? { output_tokens: Math.max(0, Math.round(out.outputTokens)) } : {}),
          }).catch(() => log('legacy-remote', 'result report failed'))
        },
      }
    },
  }
}

// ------------------------------------------------------------------------------------------------ the four booleans
export interface LegacyGateSources {
  frontmost: FrontmostSource
  console: ConsoleProbe
  // The awareness denylist options (strict mode and the worker's own list).
  deny: () => { strict: boolean; workerList: readonly string[] }
  // The worker's consent for this kind (awareness glance consent for images, voice consent for audio; true for text kinds: the flag).
  consent: (kind: LegacyKind) => boolean
  // Seconds since the last keyboard or mouse input (null when unreadable: counts as unattended).
  idleSeconds: () => number | null
  // The worker is "away" after this many idle seconds (settings.awaySeconds, the same rule as the old agency's autonomous mode).
  awaySeconds: () => number
}

export function legacyGateReader(src: LegacyGateSources): (call: LegacyCall) => Promise<GateBooleans> {
  return async (call) => {
    const [bundleId, cons] = await Promise.all([src.frontmost.read(), src.console.read()])
    const deny = src.deny()
    const app = decideApp(bundleId, appKindFor(bundleId), { strict: deny.strict, workerList: deny.workerList })
    // Images and audio follow the frames rule: unknown means closed when strict. Text kinds are blocked only by a definite answer.
    const strictUnknown = (call.kind === 'image' || call.kind === 'audio') && deny.strict
    const idle = src.idleSeconds()
    return {
      consent: src.consent(call.kind),
      denylisted_app: app.verdict === 'deny' || (app.verdict === 'unknown' && strictUnknown),
      secure_input: cons.secureInput === 'on' || (cons.secureInput === 'unknown' && strictUnknown),
      unattended: idle === null || idle >= Math.max(3, src.awaySeconds()),
    }
  }
}

// ------------------------------------------------------------------------------------------------ the process-wide gate
// The legacy modules are plain functions with no dependency injection reaching them, so the main process configures one gate here and
// they read it. Unconfigured, it is CLOSED: with the flag off it says flag_off; with the flag on but no gate wired it says
// ledger_unavailable. Nothing can slip through by forgetting to configure it.
let configured: LegacyRemoteGate | null = null

export function configureLegacyRemote(gate: LegacyRemoteGate | null): void {
  configured = gate
}

const CLOSED: LegacyRemoteGate = {
  async authorize() {
    throw new LegacyRemoteBlocked(legacyRemoteOn() ? 'ledger_unavailable' : 'flag_off')
  },
}

export function legacyRemote(): LegacyRemoteGate {
  return configured ?? CLOSED
}

/**
 * The call every legacy module makes before it opens a connection. The flag is checked FIRST, against the environment the module was
 * given, so a process without UNDERSTUDY_LEGACY_REMOTE=1 never reaches the gate, a probe or the engine. Resolves with a ticket; throws
 * LegacyRemoteBlocked otherwise.
 */
export async function authorizeLegacy(call: LegacyCall, o: { env?: Env; gate?: LegacyRemoteGate } = {}): Promise<LegacyTicket> {
  if (!legacyRemoteOn(o.env ?? process.env)) throw new LegacyRemoteBlocked('flag_off')
  return (o.gate ?? legacyRemote()).authorize(call)
}
