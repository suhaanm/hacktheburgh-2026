// The glance (AWR-2, AWR-3): trigger -> gates -> one frame -> GlancePort -> strict parse -> awareness event.
//
// What this file guarantees, each with a test:
//   - nothing is captured unless every gate passes (the gates are triggers.evaluateGates: code, never a model);
//   - the frame lives in memory for this one call and is zeroed in a finally, whatever happens; nothing is written to disk or logged;
//   - the model's answer is parsed by parseGlanceResult (closed schema); an unknown enum is dropped, never trusted;
//   - the call is recorded in a ledger BEFORE it is sent (if the ledger cannot take it, nothing is sent);
//   - the service is told the gate flags it must enforce again (consent, denylisted app, secure input, unattended = false);
//   - only the closed result and the trigger reason become an event: no image, no hash of it, no text.
// The model call itself is behind GlancePort. The real port is an HTTP POST to the agent service's /glance route, on this machine.
import { randomUUID } from 'node:crypto'
import { captureFrame, CaptureError, type FrameSource } from './capture'
import { glanceEvent, type AwarenessEvent, type Identity } from './events'
import { parseGlanceResult } from './glance-result'
import { consentFor, type AwarenessSettings } from './settings'
import { DEFAULT_TRIGGER_CONFIG, clampPeriodicMs, evaluateGates, gatesForService, type GateInputs, type TriggerConfig } from './triggers'
import type { ConsoleProbe, FrontmostSource, ScreenShareProbe } from './probes'
import { appKindFor } from './denylist'
import type { UsageMeter } from './usage'
import { fin, isObj, type AppKindOrUnknown, type Clock, type GlancePort, type GlancePortRequest, type GlancePortResponse, type GlanceResult, type SkipReason, type TriggerReason } from './types'

// ------------------------------------------------------------------------------------------------ ledger port
// A line per call, written before the call (phase 'sent') and completed after it (phase 'done'). Fields are numbers, a short hash prefix of
// the JPEG and fixed enums: never the image. The durable, user-visible ledger is the engine's privacy ledger (the /glance route writes the
// authoritative line through the egress guard); this port keeps the local record that feeds the menu-bar count and the Privacy screen,
// and may also mirror to the engine when it offers an endpoint for it.
export interface LedgerEntry {
  kind: 'image'
  phase: 'sent' | 'done'
  call_id: string
  trigger: TriggerReason
  bytes: number
  sha256_prefix: string
  model: string | null
  latency_ms: number | null
  cost_est: number | null
  outcome: 'pending' | 'ok' | 'blocked' | 'error' | 'rejected'
  at: number
}

export interface LedgerPort {
  /** ok:false means the line could not be recorded; the caller then does not send. */
  record(entry: LedgerEntry): Promise<{ ok: boolean }>
  /** Calls and dollars since a time, so the caps survive a restart. null when the ledger cannot say. */
  usageSince?(sinceMs: number): Promise<Array<{ at: number; usd: number }> | null>
}

export interface MemoryLedger extends LedgerPort {
  entries(): readonly LedgerEntry[]
  /** Completed calls only, newest last. */
  done(): readonly LedgerEntry[]
  count(): number
}

export function createMemoryLedger(cap = 200): MemoryLedger {
  let list: LedgerEntry[] = []
  return {
    async record(e) {
      list.push({ ...e })
      if (list.length > cap) list = list.slice(-cap)
      return { ok: true }
    },
    async usageSince(sinceMs) {
      return list.filter((e) => e.phase === 'done' && e.at >= sinceMs).map((e) => ({ at: e.at, usd: e.cost_est ?? 0 }))
    },
    entries: () => list,
    done: () => list.filter((e) => e.phase === 'done'),
    count: () => list.filter((e) => e.phase === 'done').length,
  }
}

// ------------------------------------------------------------------------------------------------ http port
const MODEL_RE = /^[A-Za-z0-9._:/-]{1,80}$/
const BLOCK_RE = /^[a-z0-9_]{1,40}$/

export function parsePortResponse(json: unknown): GlancePortResponse {
  if (!isObj(json)) return { ok: false, blocked_reason: 'bad_response' }
  const body = isObj(json.data) ? json.data : json
  return {
    ok: body.ok === true,
    ...(typeof body.blocked_reason === 'string' && BLOCK_RE.test(body.blocked_reason) ? { blocked_reason: body.blocked_reason } : {}),
    ...(body.result !== undefined ? { result: body.result } : {}),
    ...(typeof body.model === 'string' && MODEL_RE.test(body.model) ? { model: body.model } : {}),
    ...(fin(body.latency_ms) && body.latency_ms >= 0 ? { latency_ms: body.latency_ms } : {}),
    ...(fin(body.cost_usd_est) && body.cost_usd_est >= 0 ? { cost_usd_est: body.cost_usd_est } : {}),
  }
}

export interface HttpGlancePortOptions {
  agentUrl: string
  fetchImpl?: typeof fetch
  timeoutMs?: number
  isLoopback: (url: string) => boolean
}

/**
 * POST {agent}/glance with { frame_b64, gates, trigger, app_kind, width, height } (schema: GlanceHttpRequest) and expect
 * { ok, blocked_reason?, result?, model?, latency_ms?, cost_usd_est? } (GlanceHttpResponse). Loopback only. Nothing is logged here: not the
 * body, not the base64, and the errors it throws say nothing but that the service did not answer.
 */
export function createHttpGlancePort(opts: HttpGlancePortOptions): GlancePort {
  if (!opts.isLoopback(opts.agentUrl)) throw new Error('the glance service must be on this machine (127.0.0.1)')
  const doFetch = opts.fetchImpl ?? ((i, init) => fetch(i, init))
  return {
    async glance(req: GlancePortRequest) {
      const ctl = new AbortController()
      const timer = setTimeout(() => ctl.abort(), opts.timeoutMs ?? 20_000)
      try {
        const body = JSON.stringify({ frame_b64: req.frame.jpeg.toString('base64'), gates: req.gates, trigger: req.trigger, app_kind: req.appKind, width: req.frame.width, height: req.frame.height })
        let res: Response
        try {
          res = await doFetch(`${opts.agentUrl.replace(/\/+$/, '')}/glance`, { method: 'POST', headers: { 'content-type': 'application/json' }, body, signal: ctl.signal })
        } catch {
          throw new Error('the glance service did not answer')
        }
        let json: unknown = null
        try {
          json = await res.json()
        } catch {
          json = null
        }
        if (res.status >= 500) throw new Error('the glance service failed')
        if (res.status >= 400) return { ok: false, blocked_reason: `http_${res.status}` }
        return parsePortResponse(json)
      } finally {
        clearTimeout(timer)
      }
    },
  }
}

// ------------------------------------------------------------------------------------------------ orchestrator
export type GlanceOutcome = { ok: true; reason: TriggerReason; result: GlanceResult; event: AwarenessEvent } | { ok: false; reason: TriggerReason; skip: SkipReason; detail?: string }

export interface PowerState {
  locked(): boolean
  asleep(): boolean
  idleSeconds(): number | null
  thermal(): GateInputs['thermal']
}

export interface GlancerDeps {
  settings: () => AwarenessSettings
  flagOn: () => boolean
  now?: Clock
  usage: UsageMeter
  ledger: LedgerPort
  frames: FrameSource
  port: GlancePort
  frontmost: FrontmostSource
  console: ConsoleProbe
  screenShare?: ScreenShareProbe | null
  power: PowerState
  killed?: () => boolean
  workSession?: () => boolean
  identity: () => Identity
  emit: (e: AwarenessEvent) => unknown
  onOutcome?: (o: GlanceOutcome) => void
  id?: () => string
}

export interface Glancer {
  request(reason: TriggerReason): Promise<GlanceOutcome>
  busy(): boolean
}

export function configFromSettings(s: AwarenessSettings): TriggerConfig {
  return {
    ...DEFAULT_TRIGGER_CONFIG,
    strict: s.glanceStrict,
    workerDenylist: s.glanceDenylist,
    dailyUsd: s.glanceDailyUsd,
    maxPerHour: s.glanceMaxPerHour,
    periodicIntervalMs: clampPeriodicMs(s.glanceIntervalSec),
  }
}

export function createGlancer(deps: GlancerDeps): Glancer {
  const now = deps.now ?? Date.now
  const newId = deps.id ?? (() => `c_${randomUUID().replace(/-/g, '').slice(0, 16)}`)
  let busy = false

  const finish = (o: GlanceOutcome): GlanceOutcome => {
    try {
      deps.onOutcome?.(o)
    } catch {
      // observers never break a glance
    }
    return o
  }
  const skip = (reason: TriggerReason, why: SkipReason, detail?: string): GlanceOutcome => finish({ ok: false, reason, skip: why, ...(detail ? { detail } : {}) })

  async function request(reason: TriggerReason): Promise<GlanceOutcome> {
    const s = deps.settings()
    const layerOn = deps.flagOn() && s.awarenessEnabled
    // Cheap exits first: with the layer off or no consent not a single probe runs and nothing is captured.
    if (!layerOn) return skip(reason, 'layer_off')
    const consent = { trigger: consentFor(s, 'trigger'), periodic: consentFor(s, 'periodic') }
    if (reason === 'periodic' ? !consent.periodic || !consent.trigger : !consent.trigger) return skip(reason, 'no_consent')
    if (busy) return skip(reason, 'too_soon', 'a glance is already running')
    busy = true
    try {
      const cfg = configFromSettings(s)
      const [bundleId, cons, share] = await Promise.all([deps.frontmost.read(), deps.console.read(), deps.screenShare ? deps.screenShare.read() : Promise.resolve(null)])
      const appKind: AppKindOrUnknown = appKindFor(bundleId)
      const t = now()
      const gateIn: GateInputs = {
        nowMs: t,
        layerOn,
        consent,
        killed: deps.killed?.() ?? false,
        pausedUntilMs: s.glancePausedUntilMs,
        locked: deps.power.locked() || cons.locked === true,
        asleep: deps.power.asleep(),
        idleS: deps.power.idleSeconds(),
        screenShare: share,
        thermal: deps.power.thermal(),
        secureInput: cons.secureInput,
        bundleId,
        appKind,
        workSession: deps.workSession?.() ?? false,
      }
      const verdict = evaluateGates(reason, gateIn, deps.usage.snapshot(t), cfg)
      if (verdict.skip) return skip(reason, verdict.skip)

      let frame
      try {
        frame = await captureFrame(deps.frames)
      } catch (err) {
        return skip(reason, 'capture_failed', err instanceof CaptureError ? err.code : 'error')
      }
      const callId = newId()
      try {
        const sent = await deps.ledger.record({ kind: 'image', phase: 'sent', call_id: callId, trigger: reason, bytes: frame.bytes, sha256_prefix: frame.sha256_prefix, model: null, latency_ms: null, cost_est: null, outcome: 'pending', at: now() })
        if (!sent.ok) return skip(reason, 'ledger_unavailable')

        const gates = gatesForService(gateIn, verdict.app, cfg, consent.trigger)
        const t0 = now()
        let resp: GlancePortResponse
        try {
          resp = await deps.port.glance({ frame, gates, trigger: reason, appKind })
        } catch {
          deps.usage.record(0, now())
          await deps.ledger.record({ kind: 'image', phase: 'done', call_id: callId, trigger: reason, bytes: frame.bytes, sha256_prefix: frame.sha256_prefix, model: null, latency_ms: now() - t0, cost_est: 0, outcome: 'error', at: now() }).catch(() => undefined)
          return skip(reason, 'port_failed')
        }
        const latency = resp.latency_ms ?? now() - t0
        const cost = resp.ok ? resp.cost_usd_est ?? cfg.estCostUsd : 0
        deps.usage.record(cost, now())
        const parsed = resp.ok ? parseGlanceResult(resp.result) : null
        const outcome: LedgerEntry['outcome'] = !resp.ok ? 'blocked' : parsed ? 'ok' : 'rejected'
        await deps.ledger.record({ kind: 'image', phase: 'done', call_id: callId, trigger: reason, bytes: frame.bytes, sha256_prefix: frame.sha256_prefix, model: resp.model ?? null, latency_ms: Math.round(latency), cost_est: cost, outcome, at: now() }).catch(() => undefined)
        if (!resp.ok) return skip(reason, 'port_blocked', resp.blocked_reason)
        if (!parsed) return skip(reason, 'port_failed', 'the answer was not in the closed schema')
        const event = glanceEvent(deps.identity(), reason, parsed, new Date(now()))
        deps.emit(event)
        return finish({ ok: true, reason, result: parsed, event })
      } finally {
        frame.release() // the JPEG is zeroed whatever happened above
      }
    } finally {
      busy = false
    }
  }

  return { request, busy: () => busy }
}
