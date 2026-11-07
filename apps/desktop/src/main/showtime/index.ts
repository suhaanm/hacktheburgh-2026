// Showtime wiring (electron side): the real stage window, driver, IPC handlers and the bus / Stop hooks.
import path from 'node:path'
import { app, BrowserWindow, ipcMain, screen } from 'electron'
import type { IpcMainEvent, IpcMainInvokeEvent } from 'electron'
import { IPC } from '../../shared/ipc'
import type { Services } from '../../shared/contracts'
import type { ShowtimeStartOptions } from '../../shared/showtime'
import type { ConfirmBroker } from '../confirm'
import type { ServiceContext } from '../context'
import type { SessionController } from '../session'
import type { Dispatch } from '../tools/dispatcher'
import type { Windows } from '../windows'
import { createDriver } from './driver'
import { bindShowtimeBus, createShowtime, dockStopBox, type Showtime } from './service'
import { openStageWindow } from './stage-window'
import { createDirector, isDirectorMode, registerDirectorShortcuts, stageFromWindow } from './director'
import { setToolIntercept } from '../tools/dispatcher'
import { electronStageSource, setStageTruthSource, stageTruthEnabled } from './stage-truth'

export interface RegisterShowtimeDeps {
  ctx: ServiceContext
  services: Services
  windows: Windows
  dispatch: Dispatch
  confirm: ConfirmBroker
  session: SessionController
}

const ModeOk = (m: unknown): m is 'scripted' | 'live' => m === 'scripted' || m === 'live'

export function registerShowtime(deps: RegisterShowtimeDeps): Showtime {
  const { ctx, services, windows, dispatch, confirm, session } = deps
  const log = (msg: string): void => ctx.log('showtime', msg)
  const assetsDir = process.env.ALONGSIDE_SHOWTIME_ASSETS || path.join(app.getAppPath(), 'assets/showtime')

  // The panel is hidden by default, but the tour shows the real dock (captions, level chip, Stop). It is shown for
  // the tour only (showDock is not persisted) and goes back to hidden when the tour and its hand-over are over.
  let panelShownByTour = false
  const syncPanel = (s: { running: boolean; handover: boolean }): void => {
    if (s.running && !windows.isDockVisible()) {
      windows.showDock()
      panelShownByTour = true
    } else if (!s.running && !s.handover && panelShownByTour) {
      panelShownByTour = false
      if (!ctx.settings.get().showDock) windows.hideDock()
    }
  }

  const showtime = createShowtime({
    ctx,
    assetsDir,
    log,
    // Frontmost app, so macOS hides its menu bar and Dock behind the practice desktop (the panel and overlay sit above it).
    openStage: async () => {
      const stage = await openStageWindow({ log })
      app.focus({ steal: true })
      return stage
    },
    publish: (s) => {
      syncPanel(s)
      windows.broadcast(IPC.showtimeUpdate, s)
    },
    stopSession: () => session.stop('replaced'),
    reloadLearner: async () => {
      await services.learner.load()
    },
    hasFiles: () => services.files !== undefined,
    makeDriver: ({ stage, narrator, mode, settingsBaseline }) =>
      createDriver({
        ctx,
        services,
        dispatch,
        confirm,
        stage,
        narrator,
        mode,
        settingsBaseline,
        dockStopBox: async () => {
          const d = screen.getPrimaryDisplay()
          return dockStopBox(d.bounds, d.workArea)
        },
        log,
      }),
  })

  const guard = (event: IpcMainEvent | IpcMainInvokeEvent): void => {
    if (!windows.owns(event.sender.id)) throw new Error('IPC from an unknown sender')
  }
  const sanitize = (raw: unknown): ShowtimeStartOptions => {
    const o = (typeof raw === 'object' && raw !== null ? raw : {}) as Record<string, unknown>
    return { ...(typeof o.full === 'boolean' ? { full: o.full } : {}), ...(ModeOk(o.mode) ? { mode: o.mode } : {}) }
  }
  ipcMain.handle(IPC.showtimeStart, async (event, opts) => {
    guard(event)
    await showtime.start(sanitize(opts))
  })
  ipcMain.handle(IPC.showtimeStop, async (event) => {
    guard(event)
    await showtime.stop()
  })
  ipcMain.handle(IPC.showtimeNext, (event) => {
    guard(event)
    showtime.next()
  })
  ipcMain.handle(IPC.showtimePrev, (event) => {
    guard(event)
    showtime.prev()
  })
  ipcMain.handle(IPC.showtimePause, (event) => {
    guard(event)
    showtime.pause()
  })
  ipcMain.handle(IPC.showtimeState, (event) => {
    guard(event)
    return showtime.state()
  })

  // Interactive demo (scripts/start-demo.sh --interactive): no tour, just the practice desktop, fullscreen and frontmost
  // so the assistant can see it and the S / G / Shift+R / F keys reach it. The window closes with the app.
  // DEMO DIRECTOR (start-demo.sh --interactive only): always-on session, guaranteed shortcuts, instant exact scam check.
  let stageWin: BrowserWindow | null = null
  const director =
    process.env.ALONGSIDE_STAGE_ONLY === '1' && isDirectorMode()
      ? createDirector({
          bus: ctx.bus,
          state: ctx.state,
          settings: ctx.settings,
          services,
          dispatch,
          showView: (view) => ctx.sendDock(IPC.showtimeCue, { type: 'view', view }),
          stopSession: (reason) => session.stop(reason),
          stage: () => (stageWin && !stageWin.isDestroyed() ? stageFromWindow(() => stageWin) : null),
          log: (msg) => ctx.log('director', msg),
          // The dock renderer reads this flag in its idle-timeout rule (renderer/dock/controller.ts).
          setNoIdle: () => {
            for (const w of BrowserWindow.getAllWindows()) {
              if (w.isDestroyed() || w.getTitle() === 'Practice desktop' || !w.webContents.getURL().includes('dock')) continue
              void w.webContents.executeJavaScript("try{localStorage.setItem('alongside.noIdle','1')}catch(e){}", true).catch(() => undefined)
            }
          },
        })
      : null
  if (director) {
    setToolIntercept((name, args) => director.intercept(name, args))
    void registerDirectorShortcuts(director, (msg) => ctx.log('director', msg)).then((off) => app.once('will-quit', off))
    app.once('will-quit', () => director.dispose())
  }

  if (process.env.ALONGSIDE_STAGE_ONLY === '1') {
    setTimeout(() => {
      void openStageWindow({ log, exitButton: true, seedScam: true })
        .then(() => {
          app.focus({ steal: true })
          const win = BrowserWindow.getAllWindows().find((w) => w.getTitle() === 'Practice desktop')
          win?.focus()
          stageWin = win ?? null
          director?.onStageOpen()
          // The page's own <title> ('Practice Desktop') replaces the window title, so match case-insensitively.
          const find = (): BrowserWindow | null => BrowserWindow.getAllWindows().find((w) => !w.isDestroyed() && w.getTitle().toLowerCase() === 'practice desktop') ?? null
          if (stageTruthEnabled()) setStageTruthSource(electronStageSource(find))
          // The Exit demo button closes this window: that ends the interactive demo the same way Stop does.
          win?.once('closed', () => {
            log('practice desktop closed from its Exit button: quitting')
            app.quit()
          })
          log('practice desktop open for the interactive demo')
        })
        .catch((err: unknown) => log(`practice desktop could not open: ${err instanceof Error ? err.message : String(err)}`))
    }, 2500)
  }

  bindShowtimeBus(ctx.bus, showtime, log)
  // Hands-free launch for the demo and for headless smoke runs: ALONGSIDE_SHOWTIME_AUTOSTART=1 starts the tour once the windows are up.
  if (process.env.ALONGSIDE_SHOWTIME_AUTOSTART === '1') setTimeout(() => ctx.bus.emit('showtime:request', { source: 'cli' }), 3000)

  return showtime
}
