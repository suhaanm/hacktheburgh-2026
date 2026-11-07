// When may a glance happen? (AWR-2, AWR-3.) Deterministic code only; no model decides, and a model's output never reaches this file.
//
// Candidates (why we might look):
//   stuck     the engine's stuck probability (GET /coach/next, p_stuck) at or over a threshold for two readings in a row
//   loop      a loop signature (see loop.ts: same stop 4 times, or a 2 to 4 cycle 3 times)
//   hotkey    the worker pressed the shortcut
//   periodic  the worker opted in; every glanceIntervalSec (default 30, never under 15) while a work session is on
//
// Gates (whether we may): evaluateGates() returns the FIRST reason not to, in the order of SKIP_REASONS, or null. Unknown signals
// (a probe that could not run) are skipped, not guessed, EXCEPT the two the worker's strict mode turns into "no": secure input and the
// frontmost app. Signals this layer cannot read at all, and so does not gate on: macOS Low Power Mode (Electron has no API for it).
import { decideApp, type AppVerdict } from './denylist'
import type { UsageSnapshot } from './usage'
import type { AppKindOrUnknown, SecureInputState, SkipReason, TriggerReason } from './types'

export const MIN_PERIODIC_SEC = 15
export const DEFAULT_PERIODIC_SEC = 30

export interface TriggerConfig {
  stuckThreshold: number
  stuckConsecutive: number
  // After a stuck trigger, no new stuck trigger until the reading drops under the threshold or this long has passed.
  stuckRearmMs: number
  minGapMs: number
  maxPerHour: number
  dailyUsd: number
  // The most one call is expected to cost; a call that could take the day past the cap is not made.
  estCostUsd: number
  periodicIntervalMs: number
  // Seconds of no input after which nobody is there to be helped.
  idleLimitS: number
  strict: boolean
  workerDenylist: readonly string[]
}

export const DEFAULT_TRIGGER_CONFIG: TriggerConfig = {
  stuckThreshold: 0.7,
  stuckConsecutive: 2,
  stuckRearmMs: 120_000,
  minGapMs: 10_000,
  maxPerHour: 60,
  dailyUsd: 0.5,
  estCostUsd: 0.002,
  periodicIntervalMs: DEFAULT_PERIODIC_SEC * 1000,
  idleLimitS: 60,
  strict: true,
  workerDenylist: [],
}

export function clampPeriodicMs(sec: number): number {
  const s = Number.isFinite(sec) ? sec : DEFAULT_PERIODIC_SEC
  return Math.max(MIN_PERIODIC_SEC, s) * 1000
}

// ------------------------------------------------------------------------------------------------ candidates
/**
 * Stuck: true once per episode, when `consecutive` readings in a row are at or over the threshold. An unreadable reading (null)
 * breaks the chain. It re-arms when a reading falls under the threshold, or after `rearmMs` of staying over it.
 */
export class StuckDetector {
  private streak = 0
  private armed = true
  private firedAt = 0

  constructor(
    private readonly threshold = DEFAULT_TRIGGER_CONFIG.stuckThreshold,
    private readonly consecutive = DEFAULT_TRIGGER_CONFIG.stuckConsecutive,
    private readonly rearmMs = DEFAULT_TRIGGER_CONFIG.stuckRearmMs,
  ) {}

  observe(p: number | null, nowMs: number): boolean {
    if (p === null || !Number.isFinite(p)) {
      this.streak = 0
      return false
    }
    if (p < this.threshold) {
      this.streak = 0
      this.armed = true
      return false
    }
    if (!this.armed && nowMs - this.firedAt >= this.rearmMs) {
      this.armed = true
      this.streak = 0
    }
    this.streak++
    if (this.armed && this.streak >= this.consecutive) {
      this.armed = false
      this.firedAt = nowMs
      return true
    }
    return false
  }

  reset(): void {
    this.streak = 0
    this.armed = true
  }
}

/** Is a periodic glance due? Measured from the last glance of any kind, so a triggered glance resets the clock. */
export function periodicDue(lastGlanceAt: number | null, nowMs: number, intervalMs: number, sessionStartedAt: number | null): boolean {
  const from = lastGlanceAt ?? sessionStartedAt
  if (from === null) return false
  return nowMs - from >= intervalMs
}

// ------------------------------------------------------------------------------------------------ gates
export interface GateInputs {
  nowMs: number
  layerOn: boolean // the flag AND awarenessEnabled
  consent: { trigger: boolean; periodic: boolean } // already checked against the current consent text
  killed: boolean
  pausedUntilMs: number
  locked: boolean
  asleep: boolean
  idleS: number | null
  screenShare: boolean | null
  thermal: 'nominal' | 'fair' | 'serious' | 'critical' | 'unknown'
  secureInput: SecureInputState
  bundleId: string | null
  appKind: AppKindOrUnknown | null
  workSession: boolean
}

export function evaluateGates(reason: TriggerReason, g: GateInputs, usage: UsageSnapshot, cfg: TriggerConfig): { skip: SkipReason | null; app: AppVerdict } {
  const app = decideApp(g.bundleId, g.appKind, { strict: cfg.strict, workerList: cfg.workerDenylist })
  const skip = ((): SkipReason | null => {
    if (!g.layerOn) return 'layer_off'
    if (reason === 'periodic' ? !g.consent.periodic || !g.consent.trigger : !g.consent.trigger) return 'no_consent'
    if (g.killed) return 'killed'
    if (g.pausedUntilMs > g.nowMs) return 'paused'
    if (g.locked) return 'locked'
    if (g.asleep) return 'asleep'
    if (g.idleS !== null && g.idleS >= cfg.idleLimitS) return 'idle'
    if (g.screenShare === true) return 'screen_share'
    if (g.thermal === 'serious' || g.thermal === 'critical') return 'thermal'
    if (g.secureInput === 'on') return 'secure_input'
    if (g.secureInput === 'unknown' && cfg.strict) return 'secure_input_unknown'
    if (app.verdict === 'deny') return 'app_denied'
    if (app.verdict === 'unknown' && cfg.strict) return 'app_unknown'
    if (reason === 'periodic' && !g.workSession) return 'no_work_session'
    if (usage.lastGlanceAt !== null && g.nowMs - usage.lastGlanceAt < cfg.minGapMs) return 'too_soon'
    if (usage.callsLastHour >= cfg.maxPerHour) return 'hourly_cap'
    if (cfg.dailyUsd <= 0 || usage.usdToday + cfg.estCostUsd > cfg.dailyUsd) return 'daily_cap'
    return null
  })()
  return { skip, app }
}

/** The gate flags the service needs (the agent service builds its ImageGate from these; it never trusts the model, and neither do we). */
export function gatesForService(g: Pick<GateInputs, 'secureInput'>, app: AppVerdict, cfg: Pick<TriggerConfig, 'strict'>, consent: boolean): {
  consent: boolean
  denylisted_app: boolean
  secure_input: boolean
  unattended: boolean
} {
  return {
    consent,
    denylisted_app: app.verdict === 'deny' || (app.verdict === 'unknown' && cfg.strict),
    secure_input: g.secureInput === 'on' || (g.secureInput === 'unknown' && cfg.strict),
    unattended: false, // the desktop glance path is never unattended; unattended runs never use real-screen glances
  }
}
