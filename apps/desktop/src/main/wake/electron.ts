// The real ports of Hey Knack: the helper binary, the child process, the macOS lock and sleep events, the attention layer's quiet states, the card
// window and the loopback agent route. The only wake file that imports Electron (besides the card window and preload); no test imports it.
//
// Wiring (src/main/index.ts, one call after Live and the attention layer exist):
//
//   const wake = registerWake({ userDataDir, bus, live, attentionSignals, hudAgentActing, killed, kill, settings, endpoints, userDataDir, log })
//   // wake.controller.status() / subscribe() for the menu bar and Settings; app.on('will-quit', () => wake.dispose())
//
// Nothing runs here until the app launches on the owner's machine: the helper is started by the controller only when no guard says dormant, and
// the app starts and runs normally when the binary is absent or a permission is refused (the controller shows one plain line).
import { spawn } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { app, ipcMain, powerMonitor } from 'electron'
import type { VoiceLock } from '../attention/lock'
import { createVoiceLock } from '../attention/lock'
import type { AttentionSignals } from '../attention/signals'
import { createConsoleProbe, createScreenShareProbe } from '../awareness/probes'
import { isLoopbackUrl, type Endpoints } from '../engine/endpoints'
import { dataDirPath, readServiceToken } from '../kill-file'
import type { LiveRegistration } from '../live'
import { createCardWindow } from './card-window'
import { makeChimeWav } from './chime'
import { createWakeController, type WakeController } from './controller'
import type { ContextHub } from './context-source'
import { createDesktopRunPort } from './desktop-run'
import { experimentOn } from '../feature-flags'
import { createHelperSupervisor, type ChildLike } from './helper'
import { readRung } from './rung'
import { WakeSettingsStore } from './settings'

export const WAKE_IPC = {
  state: 'wake:state', // invoke -> WakeStatus
  set: 'wake:set', // invoke { listen: boolean } -> WakeStatus
  context: 'wake:context', // invoke { insight?, routine? } -> boolean (accepted)
  status: 'wake:status', // event (main -> windows that listen)
} as const

export interface RegisterWakeOptions {
  userDataDir: string
  live: LiveRegistration
  endpoints: Pick<Endpoints, 'agent'>
  /** The attention layer's signals (locked, screen sharing, on call, in meeting, dnd). Absent: only the probes below are used. */
  attentionSignals?: (() => AttentionSignals) | null
  /** The one-voice lock of the attention layer. Absent: a private lock. */
  lock?: VoiceLock | null
  /** The main settings: Cue's quiet-until and the menu's pause-until. */
  mainSettings: { get(): { cueQuietUntil: number | null; pausedUntil: number | null } }
  agentActing: () => boolean
  killed: () => boolean
  /** Windows that may call the IPC (our own). */
  owns: (webContentsId: number) => boolean
  /** The context hub: the shell may report the top Home insight and the running routine (ids and counts) through `wake:context`. */
  context?: ContextHub | null
  env?: Record<string, string | undefined>
  log?: (scope: string, ...args: unknown[]) => void
}

export interface WakeRegistration {
  controller: WakeController
  settings: WakeSettingsStore
  /** Where the helper binary is expected (for the plain line and the build instructions). */
  helperPath: () => string | null
  dispose(): void
}

export function resolveHelperPath(exists: (p: string) => boolean = fs.existsSync): string | null {
  const candidates = [path.join(process.resourcesPath ?? '', 'knack-wake'), path.join(app.getAppPath(), 'resources', 'knack-wake')]
  return candidates.find((c) => exists(c)) ?? null
}

export function registerWake(o: RegisterWakeOptions): WakeRegistration {
  const env = o.env ?? process.env
  const log = o.log ?? (() => undefined)
  const settings = new WakeSettingsStore(o.userDataDir)
  const mock = env.UNDERSTUDY_MOCK === '1' || env.ALONGSIDE_MOCK === '1'
  const cards = createCardWindow({ log })
  const lock = o.lock ?? createVoiceLock()

  // ---- what the guards read (all cheap, all cached, none of it content)
  let locked = false
  let asleep = false
  let consoleLocked = false
  let sharing = false
  const consoleProbe = createConsoleProbe()
  const shareProbe = createScreenShareProbe()
  let controllerRef: WakeController | null = null
  const refresh = (): void => controllerRef?.refresh()
  const onLock = (): void => void ((locked = true), refresh())
  const onUnlock = (): void => void ((locked = false), refresh())
  const onSuspend = (): void => void ((asleep = true), refresh())
  const onResume = (): void => void ((asleep = false), refresh())
  powerMonitor.on('lock-screen', onLock)
  powerMonitor.on('unlock-screen', onUnlock)
  powerMonitor.on('suspend', onSuspend)
  powerMonitor.on('resume', onResume)
  const probeTimer = setInterval(() => {
    void consoleProbe.read().then((c) => {
      consoleLocked = c.locked === true
    }, () => undefined)
    void shareProbe.read().then((s) => {
      sharing = s === true
    }, () => undefined)
  }, 10_000)

  const inputs = () => {
    const sig = o.attentionSignals?.() ?? null
    const s = o.mainSettings.get()
    const t = Date.now()
    return {
      flagOn: experimentOn('wake', env),
      isMac: process.platform === 'darwin',
      mock,
      locked: locked || consoleLocked || sig?.locked === true,
      asleep,
      paused: (s.pausedUntil ?? 0) > t,
      killed: o.killed(),
      hardQuiet: { dnd: sig?.dnd === true || (s.cueQuietUntil ?? 0) > t, screenSharing: sig?.screenSharing === true || sharing, onCall: sig?.onCall === true, inMeeting: sig?.inMeeting === true },
      agentActing: o.agentActing(),
      // Not wired: a worker who walks up and says the words after a long idle is exactly who this is for. The guard exists in guards.ts.
      away: false,
    }
  }

  const supervisor = createHelperSupervisor({
    binaryPath: resolveHelperPath(),
    exists: fs.existsSync,
    // Only what the helper needs: no keys, no tokens. stderr is ignored (never captured). stdin is a pipe so that our exit ends it.
    spawn: (file, args) =>
      spawn(file, [...args], { stdio: ['pipe', 'pipe', 'ignore'], env: { HOME: process.env.HOME ?? '', PATH: '/usr/bin:/bin', LANG: process.env.LANG ?? 'en_GB.UTF-8', ...(env.KNACK_WAKE_LOCALE ? { KNACK_WAKE_LOCALE: env.KNACK_WAKE_LOCALE } : {}) } }) as unknown as ChildLike,
    onHeard: () => void controllerRef?.onHeard(),
    onStatus: () => refresh(),
  })

  const manager = o.live.manager
  const controller = createWakeController({
    settings,
    liveSettings: o.live.settings,
    live: { startFromWake: () => manager.startFromWake(), status: () => manager.status(), subscribe: (cb) => manager.subscribe(() => cb()) },
    helper: { start: () => supervisor.start(), stop: () => supervisor.stop(), status: () => supervisor.status(), unblock: () => supervisor.unblock() },
    inputs,
    cards,
    lock,
    rung: () => readRung(dataDirPath(env)),
    desktop: createDesktopRunPort({ agentUrl: o.endpoints.agent, isLoopback: isLoopbackUrl, readToken: () => readServiceToken(env) }),
    chime: () => {
      if (settings.get().wakeChime) void o.live.clips.play(makeChimeWav(), 'audio/wav').catch(() => undefined)
    },
    say: (line) => void o.live.speaker.say(`wake.${line}`),
    log,
  })
  controllerRef = controller

  // The Settings switch and the menu bar read and write through here. Only our own windows may call.
  ipcMain.handle(WAKE_IPC.state, (e) => {
    if (!o.owns(e.sender.id)) throw new Error('wake IPC from an unknown sender')
    return controller.status()
  })
  ipcMain.handle(WAKE_IPC.set, (e, raw: unknown) => {
    if (!o.owns(e.sender.id)) throw new Error('wake IPC from an unknown sender')
    if (typeof raw === 'object' && raw !== null && typeof (raw as { listen?: unknown }).listen === 'boolean') controller.setListen((raw as { listen: boolean }).listen)
    return controller.status()
  })

  // The shell reports ids and counts for the packet. Only our own windows may call; the packet's closed grammar validates again when it is built.
  const isId = (v: unknown): v is string => typeof v === 'string' && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$/.test(v)
  const isCount = (v: unknown): v is number => typeof v === 'number' && Number.isInteger(v) && v >= 0 && v <= 9999
  ipcMain.handle(WAKE_IPC.context, (e, raw: unknown) => {
    if (!o.owns(e.sender.id)) throw new Error('wake IPC from an unknown sender')
    if (!o.context || typeof raw !== 'object' || raw === null) return false
    const c = raw as { insight?: unknown; routine?: unknown }
    let took = false
    if ('insight' in c) {
      const v = c.insight as { id?: unknown; template?: unknown } | null
      if (v === null) (o.context.setInsight(null), (took = true))
      else if (v && isId(v.id) && isId(v.template)) (o.context.setInsight({ id: v.id, template: v.template }), (took = true))
    }
    if ('routine' in c) {
      const v = c.routine as { id?: unknown; step?: unknown; of?: unknown } | null
      if (v === null) (o.context.setRoutine(null), (took = true))
      else if (v && isId(v.id) && isCount(v.step) && isCount(v.of)) (o.context.setRoutine({ id: v.id, step: v.step, of: v.of }), (took = true))
    }
    return took
  })

  controller.start()
  return {
    controller,
    settings,
    helperPath: () => resolveHelperPath(),
    dispose() {
      clearInterval(probeTimer)
      powerMonitor.off('lock-screen', onLock)
      powerMonitor.off('unlock-screen', onUnlock)
      powerMonitor.off('suspend', onSuspend)
      powerMonitor.off('resume', onResume)
      ipcMain.removeHandler(WAKE_IPC.state)
      ipcMain.removeHandler(WAKE_IPC.set)
      ipcMain.removeHandler(WAKE_IPC.context)
      controller.dispose()
      supervisor.stop()
      cards.dispose()
    },
  }
}
