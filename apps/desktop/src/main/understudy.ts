// Understudy's additions to the Alongside main process, in one place: the engine client, desk signals, coach telemetry, the
// kill switch, the HUD (kill pill and proposal toast) and the morning queue link. index.ts calls these two functions.
import { powerMonitor, shell } from 'electron'
import type { Services } from '../shared/contracts'
import type { SessionEndReason } from '../shared/protocol'
import type { Bus } from './bus'
import type { ConfirmBroker } from './confirm'
import type { ServiceContext } from './context'
import { getAgency } from './agency'
import { createCoachTracker, wireCoachBus, type CoachTracker } from './engine/coach-events'
import { createEngineClient, type EngineClient } from './engine/client'
import { installDeskSignals, type DeskSignals } from './engine/desk-signals'
import { dashboardUrl, endpointsFromEnv, type Endpoints } from './engine/endpoints'
import { loadIdentity } from './engine/identity'
import { registerHud, type HudHandle } from './hud'
import { createHudModel, type HudModel } from './hud-model'
import { createKillSwitch, type KillSwitch } from './kill-switch'

export interface UnderstudyCore {
  endpoints: Endpoints
  engine: EngineClient
  coach: CoachTracker
  dispose(): void
}

/** Before createServices: the engine client and the coach tracker the overlay is wrapped with. */
export function createUnderstudyCore(ctx: ServiceContext): UnderstudyCore {
  const endpoints = endpointsFromEnv()
  const identity = loadIdentity({ userDataDir: ctx.userDataDir })
  const engine = createEngineClient({ endpoints, identity, log: ctx.log })
  const coach = createCoachTracker({ emit: (e) => engine.emit(e), level: () => `l${ctx.state.get().level}` })
  ctx.coach = coach
  void engine.syncRole() // best effort: the role the worker picked in the dashboard's onboarding
  const offBus = wireCoachBus(ctx.bus, coach)
  return {
    endpoints,
    engine,
    coach,
    dispose() {
      offBus()
      coach.dispose()
      void engine.flush().finally(() => engine.dispose())
    },
  }
}

export interface UnderstudyShell {
  kill: KillSwitch
  hud: HudHandle
  hudModel: HudModel
  desk: DeskSignals | null
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

  const kill = createKillSwitch({
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
  const hudModel = createHudModel({
    kill,
    endpoints: core.endpoints,
    openExternal: openUrl,
    onProposalChoice: (id, choice) => {
      // 'look' already opened the dashboard. Declines go to the engine so the proposal is not offered again (a decline is a label).
      if (choice === 'not_now' || choice === 'never') void core.engine.decline(id, choice)
    },
    push: () => hudPush(),
    log: ctx.log,
  })
  const hud = registerHud({ model: hudModel, log: ctx.log, disabled: deps.headless || deps.noOverlay })
  hudPush = hud.push

  // Morning queue count for the HUD: a quiet poll, best effort.
  const pollQueue = (): void => void core.engine.pendingQueue().then((n) => hudModel.setQueuePending(n))
  pollQueue()
  const queueTimer = setInterval(pollQueue, 30_000)
  queueTimer.unref?.()

  // Idle, lock, unlock, sleep and resume (CAP-5). Times only. UNDERSTUDY_DESK_EVENTS=0 switches it off.
  const desk = process.env.UNDERSTUDY_DESK_EVENTS === '0' ? null : installDeskSignals({ powerMonitor, emit: (e) => core.engine.emit(e) })

  return {
    kill,
    hud,
    hudModel,
    desk,
    openQueue,
    dispose() {
      clearInterval(queueTimer)
      desk?.dispose()
      hudModel.dispose()
      hud.dispose()
    },
  }
}
