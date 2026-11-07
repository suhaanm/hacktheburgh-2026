// The awareness controller (REQ-5 AWR-1 to AWR-3). One object the main process creates once:
//
//   const awareness = createAwareness({ ... })        // src/main/awareness/electron.ts builds the real adapters
//   awareness.start()                                  // a no-op unless UNDERSTUDY_X_AWARENESS (or UNDERSTUDY_X) is set AND awarenessEnabled is on
//   awareness.hotkey()                                 // the worker pressed the shortcut
//   awareness.getAwarenessState() / awareness.setConsent({ trigger: true, periodic: false })   // for the consent card and the Privacy screen
//
// With the flag off, or awarenessEnabled false, NO timer is created, nothing is sampled and nothing is captured (tests assert it).
// Sub-parts start and stop with the settings: the cursor sampler and the frontmost poll while the layer is on; the stuck reader while
// triggered glances are consented; the one-second periodic check while the periodic glance is consented.
import { appKindFor, decideApp, describeDenylist } from './denylist'
import { awarenessFlagOn } from './flags'
import { createAwarenessSink, windowEvent, type AwarenessSink, type Identity, type PostFn } from './events'
import { createGlancer, configFromSettings, createMemoryLedger, type GlanceOutcome, type Glancer, type LedgerPort, type MemoryLedger, type PowerState } from './glance'
import { LoopWatcher, StopTracker } from './loop'
import { createCursorSampler, unknownClicks, type ClickSource, type CursorSampler, type ZoneAt } from './cursor'
import { createStuckReader, type StuckReader, type StuckReading } from './stuck-reader'
import { CONSENT_TEXT, CONSENT_VERSION, consentFor, consentPatch, type AwarenessSettings, type AwarenessSettingsStore, type ConsentChoice } from './settings'
import { StuckDetector, periodicDue } from './triggers'
import { UsageMeter, parseLedgerUsage } from './usage'
import type { ConsoleProbe, FrontmostSource, ScreenShareProbe } from './probes'
import type { FrameSource } from './capture'
import { realTimers, type AppKindOrUnknown, type Clock, type GlancePort, type SkipReason, type Timers, type TriggerReason } from './types'

export interface PowerLike {
  getSystemIdleTime(): number
  getCurrentThermalState?(): 'unknown' | 'nominal' | 'fair' | 'serious' | 'critical'
  on(event: 'lock-screen' | 'unlock-screen' | 'suspend' | 'resume', listener: () => void): unknown
  removeListener(event: 'lock-screen' | 'unlock-screen' | 'suspend' | 'resume', listener: () => void): unknown
}

export interface AwarenessDeps {
  settings: AwarenessSettingsStore
  engineUrl: string
  identity: () => Identity
  env?: Record<string, string | undefined>
  getCursorPoint: () => { x: number; y: number }
  power: PowerLike
  getJson: (url: string) => Promise<unknown | null>
  post: PostFn
  frontmost: FrontmostSource
  console: ConsoleProbe
  screenShare?: ScreenShareProbe | null
  frames: FrameSource
  port: GlancePort
  ledger?: MemoryLedger & LedgerPort
  killed?: () => boolean
  // True while a task is in progress (the coach poller's onTask). Periodic glances only run then.
  workSession?: () => boolean
  zoneAt?: ZoneAt | null
  clicks?: ClickSource
  timers?: Timers
  now?: Clock
  log?: (scope: string, ...args: unknown[]) => void
}

export interface AwarenessState {
  flagOn: boolean
  running: boolean
  enabled: boolean
  consent: { trigger: boolean; periodic: boolean; recordedVersion: number; currentVersion: number; at: string }
  consentText: string
  strict: boolean
  paused: boolean
  pausedUntilMs: number
  periodicIntervalSec: number
  denylist: string[]
  denyDefaults: ReturnType<typeof describeDenylist>
  usage: { callsLastHour: number; callsToday: number; usdToday: number; dailyUsd: number; maxPerHour: number; ledgerCalls: number }
  last: {
    skip: { reason: SkipReason; trigger: TriggerReason; at: number } | null
    glance: { trigger: TriggerReason; at: number; app_kind: string | null; task_phase: string | null; blocker: string | null; confidence: number } | null
  }
  sources: { frontmost: string; secureInput: string; clicks: string; screenShare: string; screenCapture: 'fake' | 'desktop'; stuck: string }
  queued: number
}

export interface Awareness {
  start(): void
  stop(): void
  dispose(): void
  hotkey(): Promise<GlanceOutcome>
  getAwarenessState(): AwarenessState
  /** The consent card's call (trusted). `trigger: false` withdraws consent for everything. */
  setConsent(choice: ConsentChoice): AwarenessState
  pause(ms?: number): AwarenessState
  resume(): AwarenessState
  // For tests and the Privacy screen.
  glancer(): Glancer
  ledger(): MemoryLedger & LedgerPort
}

export function createAwareness(deps: AwarenessDeps): Awareness {
  const env = deps.env ?? process.env
  const timers = deps.timers ?? realTimers
  const now = deps.now ?? Date.now
  const log = deps.log ?? (() => undefined)
  const flagOn = (): boolean => awarenessFlagOn(env)
  const settings = deps.settings
  const usage = new UsageMeter(now)
  const ledger = deps.ledger ?? createMemoryLedger()
  const sink: AwarenessSink = createAwarenessSink({ engineUrl: deps.engineUrl, post: deps.post, log })

  let started = false
  let locked = false
  let asleep = false
  let currentBundle: string | null = null
  let lastAttemptAt = 0
  let sessionStartedAt: number | null = null
  let lastSkip: AwarenessState['last']['skip'] = null
  let lastGlance: AwarenessState['last']['glance'] = null
  let stuckReading: StuckReading | null = null
  let seeded = false

  const power: PowerState = {
    locked: () => locked,
    asleep: () => asleep,
    idleSeconds: () => {
      try {
        const v = deps.power.getSystemIdleTime()
        return Number.isFinite(v) && v >= 0 ? v : null
      } catch {
        return null
      }
    },
    thermal: () => {
      try {
        return deps.power.getCurrentThermalState?.() ?? 'unknown'
      } catch {
        return 'unknown'
      }
    },
  }

  const glancer = createGlancer({
    settings: () => settings.get(),
    flagOn,
    now,
    usage,
    ledger,
    frames: deps.frames,
    port: deps.port,
    frontmost: deps.frontmost,
    console: deps.console,
    screenShare: deps.screenShare ?? null,
    power,
    killed: deps.killed,
    workSession: deps.workSession,
    identity: deps.identity,
    emit: (e) => sink.emit(e),
    onOutcome: (o) => {
      if (o.ok) lastGlance = { trigger: o.reason, at: now(), app_kind: o.result.app_kind, task_phase: o.result.task_phase, blocker: o.result.blocker, confidence: o.result.confidence }
      else lastSkip = { reason: o.skip, trigger: o.reason, at: now() }
    },
  })

  const stuck = new StuckDetector()
  const loops = new LoopWatcher(now)
  const stops = new StopTracker()

  const request = async (reason: TriggerReason): Promise<GlanceOutcome> => {
    lastAttemptAt = now()
    return glancer.request(reason)
  }

  // ---- parts
  const onWindow: Parameters<typeof createCursorSampler>[0]['onWindow'] = (f, span) => {
    const s = settings.get()
    if (!flagOn() || !s.awarenessEnabled || deps.killed?.() || s.glancePausedUntilMs > now()) return
    const kind: AppKindOrUnknown = appKindFor(currentBundle)
    // A denied app (or an unreadable one in strict mode) is not observed at all: no window event, no loop signal.
    const verdict = decideApp(currentBundle, kind, { strict: s.glanceStrict, workerList: s.glanceDenylist })
    if (verdict.verdict === 'deny' || (verdict.verdict === 'unknown' && s.glanceStrict)) {
      stops.reset()
      return
    }
    const idle = power.idleSeconds()
    if (!locked && !asleep && !(idle !== null && idle >= 30 && f.idle_gap_s >= f.window_s * 0.9)) {
      sink.emit(windowEvent(deps.identity(), f, { t: new Date(span.t0), appKind: kind, sysIdleS: idle }))
    }
    const stop = stops.observe({ dwell_s: f.dwell_s, anchor: f.dwell_anchor, zone: f.dwell_zone, appKind: kind })
    if (stop && consentFor(s, 'trigger') && loops.push(stop)) void request('loop')
  }

  const sampler: CursorSampler = createCursorSampler({ getPoint: deps.getCursorPoint, now, timers, zoneAt: deps.zoneAt ?? null, clicks: deps.clicks ?? unknownClicks, onWindow })
  let frontHandle: unknown = null
  let periodicHandle: unknown = null
  const reader: StuckReader = createStuckReader({
    engineUrl: deps.engineUrl,
    person: () => deps.identity().person,
    getJson: deps.getJson,
    now,
    timers,
    onReading: (r, t) => {
      stuckReading = r
      if (stuck.observe(r ? r.p : null, t) && consentFor(settings.get(), 'trigger')) void request('stuck')
    },
  })

  const pollFront = (): void => {
    void deps.frontmost.read().then((b) => {
      currentBundle = b
    })
  }
  const periodicTick = (): void => {
    const s = settings.get()
    if (!consentFor(s, 'periodic') || !(deps.workSession?.() ?? false)) return
    const last = Math.max(usage.snapshot(now()).lastGlanceAt ?? 0, lastAttemptAt) || null
    if (periodicDue(last, now(), configFromSettings(s).periodicIntervalMs, sessionStartedAt)) void request('periodic')
  }

  const onLock = (): void => void (locked = true)
  const onUnlock = (): void => void (locked = false)
  const onSuspend = (): void => void (asleep = true)
  const onResume = (): void => void (asleep = false)

  const reconcile = (): void => {
    const s = settings.get()
    const layerOn = started && flagOn() && s.awarenessEnabled
    if (layerOn) {
      if (!sampler.running()) sampler.start()
      if (frontHandle === null) {
        pollFront()
        frontHandle = timers.setInterval(pollFront, 2000)
      }
    } else {
      sampler.stop()
      if (frontHandle !== null) timers.clearInterval(frontHandle)
      frontHandle = null
      currentBundle = null
      stops.reset()
    }
    if (layerOn && consentFor(s, 'trigger')) reader.start()
    else {
      reader.stop()
      stuck.reset()
      loops.clear()
      stuckReading = null
    }
    if (layerOn && consentFor(s, 'periodic')) {
      if (periodicHandle === null) {
        sessionStartedAt = now()
        periodicHandle = timers.setInterval(periodicTick, 1000)
      }
    } else {
      if (periodicHandle !== null) timers.clearInterval(periodicHandle)
      periodicHandle = null
      sessionStartedAt = null
    }
  }

  const unsubscribeSettings = settings.onChange(() => reconcile())

  const state = (): AwarenessState => {
    const s: AwarenessSettings = settings.get()
    const snap = usage.snapshot(now())
    const cfg = configFromSettings(s)
    return {
      flagOn: flagOn(),
      running: sampler.running(),
      enabled: s.awarenessEnabled,
      consent: { trigger: consentFor(s, 'trigger'), periodic: consentFor(s, 'periodic'), recordedVersion: s.glanceConsentVersion, currentVersion: CONSENT_VERSION, at: s.glanceConsentAt },
      consentText: CONSENT_TEXT,
      strict: s.glanceStrict,
      paused: s.glancePausedUntilMs > now(),
      pausedUntilMs: s.glancePausedUntilMs,
      periodicIntervalSec: Math.round(cfg.periodicIntervalMs / 1000),
      denylist: [...s.glanceDenylist],
      denyDefaults: describeDenylist(),
      usage: { callsLastHour: snap.callsLastHour, callsToday: snap.callsToday, usdToday: Math.round(snap.usdToday * 10000) / 10000, dailyUsd: s.glanceDailyUsd, maxPerHour: s.glanceMaxPerHour, ledgerCalls: ledger.count() },
      last: { skip: lastSkip, glance: lastGlance },
      sources: {
        frontmost: 'lsappinfo (bundle id only; window titles are never read)',
        secureInput: 'ioreg IOConsoleUsers (the "on" form is documented, not yet seen on this Mac)',
        clicks: deps.clicks && deps.clicks !== unknownClicks ? 'provided' : 'unavailable (needs Accessibility, not requested)',
        screenShare: deps.screenShare ? 'heuristic (Zoom share helper, screensharingd)' : 'not checked',
        screenCapture: deps.frames.kind,
        stuck: stuckReading ? `${stuckReading.source} (GET /coach/next?dry=1)` : 'no reading',
      },
      queued: sink.pending(),
    }
  }

  return {
    start() {
      if (started) return
      started = true
      deps.power.on('lock-screen', onLock)
      deps.power.on('unlock-screen', onUnlock)
      deps.power.on('suspend', onSuspend)
      deps.power.on('resume', onResume)
      reconcile()
      // Seed the caps from the engine's ledger once, so a restart does not hand back a day's budget (best effort: needs the privacy layer on).
      if (!seeded && flagOn() && settings.get().awarenessEnabled) {
        seeded = true
        void deps.getJson(`${deps.engineUrl}/privacy/ledger?limit=500`).then((json) => {
          if (json !== null) usage.seed(parseLedgerUsage(json))
        })
      }
      if (flagOn()) log('awareness', `started (layer ${settings.get().awarenessEnabled ? 'on' : 'off in settings'})`)
    },
    stop() {
      started = false
      reconcile()
    },
    dispose() {
      started = false
      reconcile()
      unsubscribeSettings()
      deps.power.removeListener('lock-screen', onLock)
      deps.power.removeListener('unlock-screen', onUnlock)
      deps.power.removeListener('suspend', onSuspend)
      deps.power.removeListener('resume', onResume)
      sink.dispose()
    },
    hotkey: () => request('hotkey'),
    getAwarenessState: state,
    setConsent(choice) {
      settings.patch(consentPatch(choice, new Date(now())), { trusted: true })
      return state()
    },
    pause(ms) {
      settings.pauseFor(ms)
      return state()
    },
    resume() {
      settings.resume()
      return state()
    },
    glancer: () => glancer,
    ledger: () => ledger,
  }
}
