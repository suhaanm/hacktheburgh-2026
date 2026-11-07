// Understudy's additions to the Alongside main process, in one place: the engine client, desk signals, coach telemetry, the
// kill switch, the HUD (kill pill and proposal toast) and the morning queue link. index.ts calls these two functions.
import { powerMonitor, screen, shell } from 'electron'
import type { Services } from '../shared/contracts'
import type { SessionEndReason } from '../shared/protocol'
import type { Bus } from './bus'
import type { ConfirmBroker } from './confirm'
import type { ServiceContext } from './context'
import { getAgency } from './agency'
import { createChipDriver, type ChipDriver } from './coach-chip'
import { createCoachBrain, type CoachBrain } from './coach-brain'
import { createCoachPoller, type CoachPoller } from './coach-poller'
import { createDomCoach, type DomCoach } from './dom-ground/dom-coach'
import { createDomGrounder, type DomGrounder } from './dom-ground/dom-grounder'
import { startExtServer, type ExtServer } from './dom-ground/ext-server'
import { parseCalibration } from './dom-ground/rect-map'
import { createProposalScheduler, fileProposalStore, type ProposalScheduler } from './proposals'
import { isKilled } from './kill-flag'
import { createCaptureConsent, type CaptureConsent } from './engine/capture-consent'
import { createCoachTracker, wireCoachBus, type CoachTracker } from './engine/coach-events'
import { createEngineClient, type EngineClient } from './engine/client'
import { installDeskSignals, type DeskSignals } from './engine/desk-signals'
import { dashboardUrl, endpointsFromEnv, type Endpoints } from './engine/endpoints'
import { loadIdentity, saveIdentity } from './engine/identity'
import { registerHud, type HudHandle } from './hud'
import { createHudModel, type HudModel } from './hud-model'
import { createKillSwitch, type KillSwitch } from './kill-switch'

export interface UnderstudyCore {
  endpoints: Endpoints
  engine: EngineClient
  coach: CoachTracker
  // Opt-in for desk events: on only while the memory file says "Capture: times only" (or UNDERSTUDY_DESK_EVENTS=1).
  capture: CaptureConsent
  dispose(): void
}

/** Before createServices: the engine client and the coach tracker the overlay is wrapped with. */
export function createUnderstudyCore(ctx: ServiceContext): UnderstudyCore {
  const endpoints = endpointsFromEnv()
  const identity = loadIdentity({ userDataDir: ctx.userDataDir })
  const engine = createEngineClient({ endpoints, identity, log: ctx.log })
  // One read of GET /memory at startup and every few minutes: the person id, the role and the capture preference. Fail closed.
  const capture = createCaptureConsent({
    engine,
    log: ctx.log,
    onMemory: (info) => {
      if (info.person) engine.setPerson(info.person)
      if (info.role) engine.setRole(info.role)
      if (info.person || info.role) saveIdentity(ctx.userDataDir, engine.identity)
    },
  })
  // Coach telemetry is capture too: it is sent only while consent is on (fail closed). The worker's explicit answer to a prompt goes to
  // /coach/feedback separately, whatever the preference says.
  const coach = createCoachTracker({ emit: (e) => capture.allowed() && engine.emit(e), level: () => `l${ctx.state.get().level}` })
  ctx.coach = coach
  const offBus = wireCoachBus(ctx.bus, coach)
  return {
    endpoints,
    engine,
    coach,
    capture,
    dispose() {
      capture.dispose()
      offBus()
      coach.dispose()
      void engine.flush().finally(() => engine.dispose())
    },
  }
}

export interface UnderstudyShell {
  kill: KillSwitch
  ring: DomCoach
  domGrounder: DomGrounder
  extServer(): ExtServer | null
  chip: ChipDriver
  coachPoller: CoachPoller
  coachBrain: CoachBrain
  proposals: ProposalScheduler
  hud: HudHandle
  hudModel: HudModel
  desk(): DeskSignals | null
  openQueue(): void
  dispose(): void
}

export interface UnderstudyDeps {
  ctx: ServiceContext
  core: UnderstudyCore
  services: Services
  confirm: ConfirmBroker
  bus: Bus
  stopSession(reason: SessionEndReason): void
  headless: boolean
  noOverlay: boolean
}

/** After the services, the session and the confirm broker exist: the kill switch, the HUD and the desk signals. */
export function registerUnderstudy(deps: UnderstudyDeps): UnderstudyShell {
  const { ctx, core, services } = deps
  const openUrl = (url: string): void => void shell.openExternal(url).catch(() => undefined)
  const openQueue = (): void => openUrl(dashboardUrl(core.endpoints, 'queue'))

  // ---- DOM-first grounding: the extension asks this server what to measure, the ring is drawn from what it measures ----
  const domGrounder = createDomGrounder({ log: ctx.log })
  const display = () => {
    const d = screen.getPrimaryDisplay()
    return { bounds: d.bounds, scaleFactor: d.scaleFactor }
  }
  let brain: CoachBrain | null = null
  const ring = createDomCoach({
    grounder: domGrounder,
    overlay: services.overlay,
    display,
    tracker: ctx.coach,
    calibration: parseCalibration(process.env.UNDERSTUDY_RING_OFFSET),
    onEnd: (e) => brain?.onPromptEnd(e), // the worker's response to a brain decision goes to POST /coach/feedback
    log: ctx.log,
  })
  let extServer: ExtServer | null = null
  void startExtServer({
    grounder: domGrounder,
    port: core.endpoints.extension.port,
    onRing: (req) => {
      if (isKilled()) return // stopped: nothing is drawn until Resume
      ring.point(req.target, { label: req.label, step: req.step })
    },
    onClear: () => ring.clear('user'),
    log: ctx.log,
  }).then((srv) => {
    extServer = srv
  })

  const kill = createKillSwitch({
    stopCoach: () => {
      ring.clear('stop')
      domGrounder.cancelAll()
    },
    stopSession: (r) => deps.stopSession(r),
    stopAgency: () => getAgency()?.stop(),
    stopShowtime: () => deps.bus.emit('showtime:request', { source: 'hotkey', stop: true }),
    cancelConfirm: () => deps.confirm.cancel(),
    agents: () => services.agents.list(),
    cancelAgent: (id) => services.agents.cancel(id),
    overlay: { clear: (ids) => services.overlay.clear(ids), caption: (s, t, f) => services.overlay.caption(s, t, f) },
    engine: core.engine,
    log: ctx.log,
  })

  let hudPush = (): void => undefined
  let proposals: ProposalScheduler | null = null
  const hudModel = createHudModel({
    kill,
    endpoints: core.endpoints,
    openExternal: openUrl,
    // 'look' already opened the dashboard. The scheduler remembers the choice and sends declines to the engine (a decline is a label).
    onProposalChoice: (id, choice) => proposals?.choice(id, choice),
    push: () => hudPush(),
    log: ctx.log,
  })
  const hud = registerHud({ model: hudModel, log: ctx.log, disabled: deps.headless || deps.noOverlay })
  hudPush = hud.push

  // ---- the coach chip and the engine's coach state ----
  const localLevel = (): { level: 1 | 2 | 3 | 4; streakClean: number } => {
    const level = ctx.state.get().level
    try {
      const snap = services.learner.snapshot()
      const active = ctx.state.get().skill?.id
      const recent = Object.entries(snap.skills).sort((a, b) => (b[1].lastSeen ?? 0) - (a[1].lastSeen ?? 0))[0]?.[0]
      const skill = (snap.skills as Record<string, { streakClean: number } | undefined>)[active ?? recent ?? '']
      return { level, streakClean: skill?.streakClean ?? 0 }
    } catch {
      return { level, streakClean: 0 }
    }
  }
  const chip = createChipDriver({ overlay: services.overlay, local: localLevel, killed: isKilled, log: ctx.log })
  let lastEpisodeEnd: number | null = null
  let engineTask: { step: number; stepsTotal: number } | null = null
  const offLevel = deps.bus.on('level:changed', () => chip.refresh())
  const offOverlay = deps.bus.on('overlay:ready', () => chip.refresh(true)) // the overlay page (re)loaded: draw the chip again
  const offStep = deps.bus.on('lesson:step', (e) => {
    if (e.phase === 'done' || e.phase === 'aborted') {
      lastEpisodeEnd = Date.now()
      chip.refresh()
    }
  })
  const offEnd = deps.bus.on('session:ended', () => {
    lastEpisodeEnd = Date.now()
    chip.refresh()
  })
  const coachPoller = createCoachPoller({
    engine: core.engine,
    chip,
    onTask: (task) => {
      if (engineTask && !task) lastEpisodeEnd = Date.now() // the engine's task ended
      engineTask = task ? { step: task.step, stepsTotal: task.stepsTotal } : null
    },
    log: ctx.log,
  })
  // The coach brain: while a task is in progress, GET /coach/next about every 2 s; annotate and nudge become a ring on the named zone.
  brain = createCoachBrain({ engine: core.engine, state: () => coachPoller.lastState(), ring, killed: isKilled, log: ctx.log })
  const coachBrain = brain
  const chipTimer = setInterval(() => chip.refresh(), 15_000)
  chipTimer.unref?.()

  // ---- proposal toasts: a calm card at a natural break, never mid-task ----
  proposals = createProposalScheduler({
    engine: core.engine,
    hud: hudModel,
    store: fileProposalStore(ctx.userDataDir),
    signals: {
      idleSeconds: () => {
        try {
          return powerMonitor.getSystemIdleTime()
        } catch {
          return 0
        }
      },
      lessonActive: () => ctx.state.get().skill !== undefined,
      confirmPending: () => ctx.state.get().pendingConfirm !== undefined,
      killed: isKilled,
      locked: () => desk?.state().locked === true || desk?.state().asleep === true,
      task: () => engineTask,
      lastEpisodeEndAt: () => lastEpisodeEnd,
      lastCoachDecisionAt: () => coachBrain.lastActiveDecisionAt(),
    },
    log: ctx.log,
  })

  // Morning queue count for the HUD: a quiet poll, best effort.
  const pollQueue = (): void => void core.engine.pendingQueue().then((n) => hudModel.setQueuePending(n))
  pollQueue()
  const queueTimer = setInterval(pollQueue, 30_000)
  queueTimer.unref?.()

  // Idle, lock, unlock, sleep and resume (CAP-5). Times only, and only while the worker has opted in: the signals are installed
  // when consent turns on and removed (with any unsent events) the moment it turns off.
  let desk: DeskSignals | null = null
  const applyCapture = (): void => {
    if (core.capture.allowed()) desk ??= installDeskSignals({ powerMonitor, emit: (e) => core.engine.emit(e) })
    else {
      desk?.dispose()
      desk = null
    }
  }
  const offCapture = core.capture.subscribe(applyCapture)
  applyCapture()
  chip.refresh()

  return {
    kill,
    ring,
    domGrounder,
    extServer: () => extServer,
    chip,
    coachPoller,
    coachBrain,
    proposals,
    hud,
    hudModel,
    desk: () => desk,
    openQueue,
    dispose() {
      clearInterval(queueTimer)
      clearInterval(chipTimer)
      offLevel()
      offOverlay()
      offStep()
      offEnd()
      coachPoller.dispose()
      coachBrain.dispose()
      proposals?.dispose()
      ring.dispose()
      domGrounder.cancelAll()
      void extServer?.close()
      offCapture()
      desk?.dispose()
      hudModel.dispose()
      hud.dispose()
    },
  }
}
