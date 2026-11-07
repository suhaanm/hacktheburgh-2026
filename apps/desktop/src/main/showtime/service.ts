// The Showtime service: owns one tour at a time (stage window, seeded profile, driver, machine) and exposes the
// start/stop/next/prev/pause/state surface used by IPC, the bus (tray, dock button, hotkey) and the debug server.
// No electron imports here: the stage, the driver and the file system are injected, so the whole lifecycle is
// unit-testable with fakes and a fake clock.
import path from 'node:path'
import { readFile } from 'node:fs/promises'
import type { NormBox } from '../../shared/protocol'
import { IDLE_SHOWTIME_STATE, type ShowtimeMode, type ShowtimeStartOptions, type ShowtimeState } from '../../shared/showtime'
import type { Settings } from '../../shared/settings'
import type { Bus } from '../bus'
import type { ServiceContext } from '../context'
import { buildChapters } from './chapters'
import { createMachine, realClock, type Availability, type Clock, type Machine } from './machine'
import { createNarrator, type Narrator } from './narration'
import { restoreProfile, seedProfile } from './seed'
import type { Driver } from './driver'
import type { StageWindow } from './stage-window'
import type { Chapter } from './types'

export interface MakeDriverArgs {
  stage: () => StageWindow | null
  narrator: Narrator
  mode: ShowtimeMode
  settingsBaseline: Settings
}

export interface ShowtimeDeps {
  ctx: Pick<ServiceContext, 'state' | 'bus' | 'settings' | 'userDataDir'>
  // Opens the practice desktop. Rejects when it cannot (the tour then does not start and nothing is changed).
  openStage(): Promise<StageWindow>
  makeDriver(args: MakeDriverArgs): Driver
  // Pushes the state to the dock and the overlay (roadmap strip, badge).
  publish(state: ShowtimeState): void
  // Ends a running Live session before the tour takes over the screen.
  stopSession(): void
  // Reloads what the learner store holds after the profile file was swapped.
  reloadLearner(): Promise<void>
  // Whether the live agency / files dependencies exist in this build (a missing one skips its chapter).
  hasFiles(): boolean
  assetsDir: string
  log: (msg: string) => void
  clock?: Clock
  env?: NodeJS.ProcessEnv
}

export interface Showtime {
  start(opts?: ShowtimeStartOptions): Promise<void>
  stop(): Promise<void>
  next(): void
  prev(): void
  pause(): void
  state(): ShowtimeState
  // True from start until the owner closes the hand-over: what the tray uses to say "Stop the demo walkthrough".
  active(): boolean
  dispose(): Promise<void>
}

const ACTIVE_PHASES = new Set(['connecting', 'live', 'thinking', 'speaking'])

export function createShowtime(deps: ShowtimeDeps): Showtime {
  const { ctx, log } = deps
  const env = deps.env ?? process.env
  let machine: Machine | null = null
  let driver: Driver | null = null
  let stage: StageWindow | null = null
  let starting = false
  let cancelStart = false
  let lastState: ShowtimeState = IDLE_SHOWTIME_STATE
  let finishing: Promise<void> | null = null

  const publish = (s: ShowtimeState): void => {
    lastState = s
    deps.publish(s)
  }
  const idle = (): ShowtimeState => ({ ...IDLE_SHOWTIME_STATE, badge: env.ALONGSIDE_SHOWTIME_BADGE !== '0' })
  const currentState = (): ShowtimeState => machine?.state() ?? lastState
  const active = (): boolean => starting || (machine !== null && (machine.state().running || machine.state().handover))

  async function cleanup(): Promise<void> {
    const d = driver
    const s = stage
    driver = null
    stage = null
    machine = null
    try {
      await d?.teardown()
    } catch (err) {
      log(`teardown: ${err instanceof Error ? err.message : String(err)}`)
    }
    try {
      s?.close()
    } catch (err) {
      log(`stage close: ${err instanceof Error ? err.message : String(err)}`)
    }
    await endProfile()
    publish(idle())
  }

  async function endProfile(): Promise<void> {
    if (!ctx.userDataDir) return
    try {
      const r = await restoreProfile(ctx.userDataDir)
      if (r !== 'nothing') {
        log(`profile ${r}`)
        await deps.reloadLearner()
      }
    } catch (err) {
      log(`profile restore failed: ${err instanceof Error ? err.message : String(err)}`)
    }
  }

  function onFinish(reason: 'complete' | 'stopped'): void {
    if (reason === 'complete') {
      // The tour is over: real profile and settings come back, the app is in normal live mode. The practice desktop
      // stays up for questions until the owner presses Stop.
      const d = driver
      finishing = (async () => {
        try {
          await d?.teardown()
        } catch (err) {
          log(`teardown: ${err instanceof Error ? err.message : String(err)}`)
        }
        await endProfile()
      })()
      return
    }
    finishing = cleanup()
  }

  function probe(mode: ShowtimeMode) {
    return (chapter: Chapter): Availability => {
      if (chapter.requires.includes('agency') && !('agency' in (ctx.settings.get() as unknown as Record<string, unknown>))) {
        return { ok: false, reason: 'agency is not part of this build' }
      }
      if (chapter.requires.includes('files') && mode === 'live' && !deps.hasFiles()) return { ok: false, reason: 'the files service is not part of this build' }
      return { ok: true }
    }
  }

  async function start(opts: ShowtimeStartOptions = {}): Promise<void> {
    if (active()) return
    starting = true
    cancelStart = false
    const mode: ShowtimeMode = opts.mode ?? (env.ALONGSIDE_SHOWTIME_MODE === 'live' ? 'live' : 'scripted')
    const full = opts.full ?? env.ALONGSIDE_SHOWTIME_FULL === '1'
    try {
      if (ACTIVE_PHASES.has(ctx.state.get().phase)) deps.stopSession()
      const baseline = ctx.settings.get()
      if (ctx.userDataDir) {
        try {
          const seed = await readFile(path.join(deps.assetsDir, 'demo-profile.md'), 'utf8')
          const r = await seedProfile(ctx.userDataDir, seed)
          if (r.recovered !== 'nothing') log(`recovered a profile left by a crashed tour (${r.recovered})`)
          await deps.reloadLearner()
        } catch (err) {
          log(`profile seed skipped: ${err instanceof Error ? err.message : String(err)}`)
        }
      }
      let opened: StageWindow
      try {
        opened = await deps.openStage()
      } catch (err) {
        log(`practice desktop could not open: ${err instanceof Error ? err.message : String(err)}`)
        await endProfile()
        return
      }
      stage = opened
      if (cancelStart) {
        await cleanup()
        return
      }
      const narrator = createNarrator(path.join(deps.assetsDir, 'clips'), log)
      driver = deps.makeDriver({ stage: () => stage, narrator, mode, settingsBaseline: baseline })
      const d = driver
      machine = createMachine({
        chapters: buildChapters({ full }),
        exec: (action) => d.exec(action),
        probe: probe(mode),
        onState: publish,
        onFinish,
        onError: (err, action) => log(`action ${action.type} failed: ${err instanceof Error ? err.message : String(err)}`),
        clock: deps.clock ?? realClock,
        mode,
        full,
        badge: env.ALONGSIDE_SHOWTIME_BADGE !== '0',
      })
      log(`starting (${mode}${full ? ', full' : ''})`)
      await machine.start()
    } finally {
      starting = false
    }
  }

  return {
    start,
    async stop() {
      if (starting) cancelStart = true
      if (!machine) return
      machine.stop()
      await finishing
    },
    next: () => machine?.next(),
    prev: () => machine?.prev(),
    pause: () => machine?.togglePause(),
    state: currentState,
    active,
    async dispose() {
      cancelStart = true
      machine?.stop()
      await finishing
    },
  }
}

// Tray item, dock button, hotkey and CLI all arrive as one bus event; the dock's Stop button (session:ended 'stop')
// ends the tour too, so the owner always has one way out.
export function bindShowtimeBus(bus: Pick<Bus, 'on'>, showtime: Showtime, log: (msg: string) => void): () => void {
  const offRequest = bus.on('showtime:request', (e) => {
    if (e.stop) void showtime.stop()
    else void showtime.start({ ...(e.full !== undefined ? { full: e.full } : {}) }).catch((err: unknown) => log(`start failed: ${err instanceof Error ? err.message : String(err)}`))
  })
  const offEnded = bus.on('session:ended', ({ reason }) => {
    if (reason === 'stop' && showtime.active()) void showtime.stop()
  })
  return () => {
    offRequest()
    offEnded()
  }
}

// Where the dock's Stop button is, in the 0..1000 screen space the overlay uses. The dock is expanded for the
// "you're in control" chapter: bottom-right of the work area (16 px margin, as windows.ts) with Stop in the footer.
export function dockStopBox(display: { x: number; y: number; width: number; height: number }, workArea: { x: number; y: number; width: number; height: number }): NormBox {
  const margin = 16
  const right = workArea.x + workArea.width - margin
  const bottom = workArea.y + workArea.height - margin
  const box = { x0: right - 16 - 112, x1: right - 16, y0: bottom - 12 - 52, y1: bottom - 12 }
  const nx = (x: number): number => Math.min(1000, Math.max(0, ((x - display.x) / display.width) * 1000))
  const ny = (y: number): number => Math.min(1000, Math.max(0, ((y - display.y) / display.height) * 1000))
  return { xmin: nx(box.x0), ymin: ny(box.y0), xmax: nx(box.x1), ymax: ny(box.y1) }
}
