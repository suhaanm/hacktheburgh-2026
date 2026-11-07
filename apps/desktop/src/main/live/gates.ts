// The gates in front of everything that leaves the device in a voice session (audio and frames): deterministic code, never a model.
// The four booleans are the ones the privacy track's ImageGate takes (consent, denylisted_app, secure_input, unattended), computed from the
// same probes the awareness layer uses (frontmost app by bundle id, macOS secure input, console lock, screen share) and the same denylist.
//
// Order, for a frame, matches `privacy/image.py::gate_reason` for real_screen: unattended ALWAYS blocks, then secure input, then a
// denylisted app, then missing consent. Before them: the kill switch and the worker's pause. After: a locked or shared screen.
//   frames  an unreadable frontmost app or secure-input state counts as a block when the worker is in strict mode (as for glances).
//   audio   only a definite answer blocks: no picture of the screen leaves with a voice, so "unknown" does not stop a spoken question.
import { appKindFor, decideApp } from '../awareness/denylist'
import type { ConsoleProbe, FrontmostSource, ScreenShareProbe } from '../awareness/probes'
import { frameConsent, voiceConsent, type LiveSettings } from './settings'

export type GateKind = 'audio' | 'frames'
export type GateReason = 'killed' | 'paused' | 'unattended' | 'secure_input' | 'denylisted_app' | 'no_consent' | 'locked' | 'screen_share' | 'stale'

export interface GateBooleans {
  consent: boolean
  denylisted_app: boolean
  secure_input: boolean
  unattended: boolean
}

export interface GateVerdict {
  open: boolean
  reason: GateReason | null
  gate: GateBooleans
  at: number
}

export interface GateSources {
  frontmost: FrontmostSource
  console: ConsoleProbe
  screenShare?: ScreenShareProbe | null
  killed: () => boolean
  // True while an agent is acting for the worker, or this is an unattended run. A voice session never runs then.
  unattended: () => boolean
  settings: () => LiveSettings
  deny: () => { strict: boolean; workerList: readonly string[] }
  now?: () => number
}

export interface GateReader {
  read(kind: GateKind): Promise<GateVerdict>
}

export function createGateReader(src: GateSources): GateReader {
  const now = src.now ?? Date.now
  return {
    async read(kind) {
      const t = now()
      const s = src.settings()
      const deny = src.deny()
      const [bundleId, cons, share] = await Promise.all([src.frontmost.read(), src.console.read(), src.screenShare ? src.screenShare.read() : Promise.resolve(null)])
      const app = decideApp(bundleId, appKindFor(bundleId), { strict: deny.strict, workerList: deny.workerList })
      const strictUnknown = kind === 'frames' && deny.strict
      const gate: GateBooleans = {
        consent: kind === 'frames' ? frameConsent(s) : voiceConsent(s),
        denylisted_app: app.verdict === 'deny' || (app.verdict === 'unknown' && strictUnknown),
        secure_input: cons.secureInput === 'on' || (cons.secureInput === 'unknown' && strictUnknown),
        unattended: src.unattended(),
      }
      const reason = ((): GateReason | null => {
        if (src.killed()) return 'killed'
        if (s.livePausedUntilMs > t) return 'paused'
        if (gate.unattended) return 'unattended'
        if (gate.secure_input) return 'secure_input'
        if (gate.denylisted_app) return 'denylisted_app'
        if (!gate.consent) return 'no_consent'
        if (cons.locked === true) return 'locked'
        if (kind === 'frames' && share === true) return 'screen_share'
        return null
      })()
      return { open: reason === null, reason, gate, at: t }
    },
  }
}

export interface Timers {
  setInterval(fn: () => void, ms: number): unknown
  clearInterval(h: unknown): void
}

export const realTimers: Timers = {
  setInterval: (fn, ms) => setInterval(fn, ms),
  clearInterval: (h) => clearInterval(h as ReturnType<typeof setInterval>),
}

export const AUDIO_GATE_MAX_AGE_MS = 3000

/**
 * Audio chunks arrive every 32 ms, far too often to run a probe per chunk, so while a session is open the audio verdict is refreshed
 * about every 500 ms and each chunk reads the latest one. A verdict older than 3 s (the probe is failing or hanging) counts as CLOSED:
 * the check fails shut.
 */
export class GateMonitor {
  private latest: GateVerdict | null = null
  private handle: unknown = null
  private inflight = false

  constructor(
    private readonly reader: GateReader,
    private readonly timers: Timers = realTimers,
    private readonly now: () => number = Date.now,
    private readonly everyMs = 500,
    private readonly onVerdict?: (v: GateVerdict) => void,
  ) {}

  async start(): Promise<GateVerdict> {
    if (this.handle === null) this.handle = this.timers.setInterval(() => void this.refresh(), this.everyMs)
    return this.refresh()
  }

  stop(): void {
    if (this.handle !== null) this.timers.clearInterval(this.handle)
    this.handle = null
    this.latest = null
  }

  async refresh(): Promise<GateVerdict> {
    if (this.inflight && this.latest) return this.latest
    this.inflight = true
    try {
      const v = await this.reader.read('audio')
      this.latest = v
      this.onVerdict?.(v)
      return v
    } catch {
      const stale: GateVerdict = { open: false, reason: 'stale', gate: { consent: false, denylisted_app: false, secure_input: false, unattended: false }, at: this.now() }
      this.latest = stale
      return stale
    } finally {
      this.inflight = false
    }
  }

  /** The verdict for one audio chunk. Closed when there is none yet or it is too old. */
  audio(): GateVerdict {
    const v = this.latest
    if (!v || this.now() - v.at > AUDIO_GATE_MAX_AGE_MS) return { open: false, reason: 'stale', gate: v?.gate ?? { consent: false, denylisted_app: false, secure_input: false, unattended: false }, at: this.now() }
    return v
  }

  /** A fresh, awaited verdict for a frame (frames are rare, so a probe each time is cheap). */
  frames(): Promise<GateVerdict> {
    return this.reader.read('frames')
  }
}
