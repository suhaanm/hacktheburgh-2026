// The Knack shell: the main window, the services it needs, the application menu and Dock icon, and the corner pill. One app: dashboard window + menu-bar
// item + pill, which starts the engine and the agent itself. Two steps, because the window must be up before the slow things happen:
//
//   createKnackShell   at the very start of main: the "Starting Knack…" window appears, the models are chosen (live when a key is present and the boot
//                      check passes, example data otherwise), the services are started, the dashboard loads when they answer.
//   shell.attach       once the kill switch, the desk signals and the agent-service poll exist: the corner pill and the minimise and restore rules.
//
// The decisions are in the pure modules (model-mode, stack, pill-state, shell-rules, pill-visibility, window-bounds, app-menu); this file connects them to
// Electron and has no rules of its own.
import path from 'node:path'
import { app, ipcMain, Menu } from 'electron'
import { APP_NAME, APP_ORIGIN } from '../../shared/brand'
import type { Settings } from '../../shared/settings'
import { KNACK_IPC } from '../../shared/knack'
import { readServiceToken } from '../kill-file'
import { applyStackEnv, applyModeEnv } from './stack-config'
import { registerAppProtocol } from './app-protocol-electron'
import type { Upstream } from './app-protocol'
import { buildAppMenuTemplate, buildDockMenuTemplate } from './app-menu'
import { registerDock } from './dock'
import { createMainWindow, type MainWindow } from './main-window'
import { keyPresent, modelStatus, planModels, type ModelDecision } from './model-mode'
import { createPillController, type PillController } from './pill-controller'
import { ACTING_RUN_STATES, type PillSignals } from './pill-state'
import { createPillWindow, type PillWindow } from './pill-window'
import { pillVisibility } from './pill-visibility'
import { shellPages, uiStateOf } from './shell-pages'
import { INITIAL_MEMO, decideWindow, type ShellAction, type ShellEvent, type ShellMemo } from './shell-rules'
import type { Stack, StackConfig, StackState } from './stack'
import { createRealStack } from './stack-real'
import { createWindowStateStore } from './window-state'

export interface KnackEarlyDeps {
  settings: { get(): Settings; onChange(l: (s: Settings, patch: Partial<Settings>) => void): () => void }
  userDataDir: string
  config: StackConfig
  /** Windows exist and work but are never shown (the hidden check). */
  hidden: boolean
  env: Record<string, string | undefined>
  /** Lists the models the key can use (the desktop model port's boot check); true when it passed. Called once, only when live is wanted and a key exists. */
  bootCheck: () => Promise<boolean>
  /** The kill switch's registered global accelerator, to show on the menu item. */
  killAccelerator: () => string | null
  /** Settings… opens the settings view. */
  openSettings: () => void
  /** Stop Everything from the menus (the kill switch). */
  stopEverything: () => void
  /** The brand glyph file's text, for the starting page. */
  glyphSvg: string
  /** Relaunch the app (the models switch). Default: app.relaunch then app.quit. */
  relaunch?: () => void
  stack?: Stack
  upstream?: Upstream
  log: (...args: unknown[]) => void
  /** Observation hook: every window action the rules chose (the hidden check records them). */
  onAction?: (e: { action: ShellAction; event: ShellEvent['type'] }) => void
}

export interface KnackLateDeps {
  kill: { trigger(source: 'hud'): Promise<unknown>; isKilled(): boolean; subscribe(cb: () => void): () => void }
  /** One look at the desk: a reason to stay away (a denylisted app, a password field, an unreadable state) and whether a presentation or screen share runs. Fails closed. */
  probe: () => Promise<{ suppressed: string | null; presenting: boolean }>
  /** Approvals waiting in the queue (null when the engine cannot be asked). */
  pendingQueue: () => Promise<number | null>
  capturable?: boolean
}

export interface AgentSample {
  /** Parsed GET /health of the agent service, or null when it did not answer. */
  health: unknown
  /** Parsed GET /agents/runs, or null. */
  runs: unknown
}

export interface KnackShell {
  stack: Stack
  mainWindow: MainWindow
  /** Resolves when the models are chosen and this process's environment says so (the desktop model port is built after this). */
  planned: Promise<ModelDecision>
  modelStatus(): { live: boolean | null; text: string }
  attach(late: KnackLateDeps): void
  feedAgentSample(sample: AgentSample): void
  openMain(): void
  info(): KnackInfo
  dispose(): Promise<void>
}

export interface KnackInfo {
  stack: StackState
  model: { live: boolean | null; text: string }
  pill: { kind: string; text: string; visible: boolean; bounds: { x: number; y: number; width: number; height: number } | null; clickThrough: boolean | null }
  window: ReturnType<MainWindow['state']> & { focused: boolean }
  memo: ShellMemo
}

const asObj = (v: unknown): Record<string, unknown> | null => (typeof v === 'object' && v !== null && !Array.isArray(v) ? (v as Record<string, unknown>) : null)

/** GET /agents/runs, as a list or { data: [...] }, to the ids and states the pill needs. */
export function runsOf(raw: unknown): { id: string; state: string }[] {
  const list = Array.isArray(raw) ? raw : (asObj(raw) && Array.isArray(asObj(raw)!.data) ? (asObj(raw)!.data as unknown[]) : [])
  const out: { id: string; state: string }[] = []
  for (const r of list) {
    const o = asObj(r)
    const id = typeof o?.run_id === 'string' ? o.run_id : typeof o?.id === 'string' ? o.id : null
    if (o && id && typeof o.state === 'string') out.push({ id, state: o.state })
  }
  return out
}

export function createKnackShell(deps: KnackEarlyDeps): KnackShell {
  const { config, env, log } = deps
  const hidden = deps.hidden
  const store = createWindowStateStore({ file: path.join(deps.userDataDir, 'knack-window.json') })
  const main = createMainWindow({ store, hidden, devOrigin: config.devUrl ? new URL(config.devUrl).origin : null, log })
  const stack = deps.stack ?? createRealStack(config, (...a) => log('stack', ...a))
  let decision: ModelDecision | null = null
  let mockNow: boolean | null = null
  let memo: ShellMemo = INITIAL_MEMO
  let quitting = false
  let stackStopped = false

  const status = (): { live: boolean | null; text: string } => modelStatus(mockNow, decision)
  const notice = (): string | null => decision?.notice ?? null

  // ---- the app's own address: the dashboard build, the two API prefixes, the starting page
  const unprotocol = registerAppProtocol({
    distRoot: config.distDir,
    ports: config.ports,
    token: () => readServiceToken(env),
    shellAssets: shellPages({ appName: APP_NAME, glyphSvg: deps.glyphSvg }),
    upstream: deps.upstream,
    log,
  })

  // ---- the starting page's two calls
  const ui = (): ReturnType<typeof uiStateOf> => uiStateOf(stack.state(), APP_NAME, notice())
  ipcMain.handle(KNACK_IPC.get, (event) => {
    if (!main.owns(event.sender.id)) throw new Error('shell IPC from an unknown sender')
    return ui()
  })
  ipcMain.on(KNACK_IPC.retry, (event) => {
    if (main.owns(event.sender.id)) void stack.retry()
  })

  const pushUi = (): void => main.pushUiState(ui())
  let dashboardLoaded = false
  const offStack = stack.subscribe((s) => {
    if (s.phase === 'ready') {
      // This app's own environment follows the stack it ended up with: the kill file and the token live in that data directory.
      const dir = stack.dataDir()
      if (dir) applyStackEnv(env, config.ports, dir)
      mockNow = s.mock
      if (!dashboardLoaded) {
        dashboardLoaded = true
        main.loadDashboard(s.dashboard === 'dev-server' && config.devUrl ? `${config.devUrl}/` : `${APP_ORIGIN}/`)
      }
    } else {
      pushUi()
    }
  })

  main.loadStarting()

  // ---- the models, then the services
  const planned = (async (): Promise<ModelDecision> => {
    const d = await planModels({ switchOn: deps.settings.get().useLiveModels, envOverride: env.KNACK_LIVE, hasKey: keyPresent(env), bootCheck: deps.bootCheck })
    decision = d
    stack.setMode(d.mode)
    applyModeEnv(env, config, d.mode)
    log('knack', `models: ${d.mode} (${d.reason})`)
    pushUi()
    void stack.start()
    return d
  })()

  // ---- the application menu, the Dock icon and its menu
  const showMain = (): void => dispatch({ type: 'dock-click' })
  const killAccel = (): string | null => deps.killAccelerator()
  const handlers = { openSettings: deps.openSettings, showWindow: showMain, stopEverything: deps.stopEverything }
  Menu.setApplicationMenu(Menu.buildFromTemplate(buildAppMenuTemplate({ appName: APP_NAME, platform: process.platform, isPackaged: app.isPackaged, killAccelerator: killAccel(), handlers })))
  app.setAboutPanelOptions({ applicationName: APP_NAME, applicationVersion: app.getVersion(), copyright: 'Built for Hack the Burgh XIII' })
  const offDock = registerDock(deps.settings, { dock: app.dock ?? undefined, hidden, log: (...a) => log(...a) })
  app.dock?.setMenu(Menu.buildFromTemplate(buildDockMenuTemplate({ appName: APP_NAME, handlers })))

  // ---- the minimise and restore rules, performed
  const dispatch = (ev: ShellEvent, o: { quiet?: boolean } = {}): void => {
    const d = decideWindow(ev, main.state(), { minimiseWhileWorking: deps.settings.get().minimiseWhileWorking }, memo)
    memo = d.memo
    if (d.action === 'minimise') main.minimise()
    else if (d.action === 'restore') (o.quiet ? main.restoreQuietly() : main.show())
    deps.onAction?.({ action: d.action, event: ev.type })
    if (ev.type === 'dock-click' || ev.type === 'pill-click') late?.acknowledge()
  }
  const onActivate = (): void => dispatch({ type: 'dock-click' }) // the Dock icon (or the app switcher) with no window up
  app.on('activate', onActivate)
  const onSecond = (): void => dispatch({ type: 'dock-click' }) // a second launch brings the first one forward
  app.on('second-instance', onSecond)

  // ---- the pill (attached later)
  let late: { acknowledge(): void; controller: PillController; window: PillWindow; feed(s: AgentSample): void; dispose(): void; render(): void } | null = null

  const attach = (l: KnackLateDeps): void => {
    const controller = createPillController()
    const kill = l.kill
    let reachable = false
    let supervisor: string | null = null
    let runs: { id: string; state: string }[] = []
    let pending: number | null = null
    let probeSeq = 0
    let ticker: ReturnType<typeof setInterval> | null = null

    const pillWin = createPillWindow({
      hidden,
      capturable: l.capturable,
      onAction: (a) => {
        if (a.type === 'stop') void kill.trigger('hud')
        else dispatch({ type: 'pill-click' })
      },
    })

    const signals = (): PillSignals => ({ reachable, supervisor, runs, killed: kill.isKilled() || supervisor === 'killed', pending })

    // What the pill shows, and whether it may be on screen right now (never over a secure input or a denylisted app: probed fresh each time, failing closed).
    const render = (): void => {
      const seq = ++probeSeq
      const st = controller.state()
      pillWin.push(controller.view())
      if (st.kind === 'idle') {
        pillWin.hide()
        if (ticker) clearInterval(ticker)
        ticker = null
        return
      }
      ticker ??= setInterval(render, 1500)
      void l
        .probe()
        .catch(() => ({ suppressed: 'probe_failed', presenting: false }))
        .then((p) => {
          if (seq !== probeSeq) return
          const w = main.state()
          const v = pillVisibility({ kind: controller.state().kind, suppressed: p.suppressed, presenting: p.presenting, knackInFront: w.visible && !w.minimised && main.isFocused(), disabled: false })
          if (v.show) pillWin.show()
          else pillWin.hide()
        })
    }

    controller.subscribe((s, prev) => {
      dispatch({ type: 'pill', from: prev.kind, to: s.kind }, { quiet: true })
      render()
    })
    const offKill = kill.subscribe(() => {
      controller.ingest(signals())
      render()
    })
    const offWin = main.subscribe((e) => {
      if (e === 'focus') {
        dispatch({ type: 'window-shown' })
        controller.acknowledge()
      }
      render()
    })

    const feed = (sample: AgentSample): void => {
      const health = asObj(sample.health)
      reachable = health !== null
      const sup = asObj(health?.supervisor)
      supervisor = typeof sup?.state === 'string' ? sup.state : null
      runs = runsOf(sample.runs)
      const acting = supervisor === 'running' || runs.some((r) => ACTING_RUN_STATES.has(r.state))
      const k = controller.state().kind
      // The queue count is read fresh while a run works or has just ended, so "something new to approve" is measured against the count at the start.
      if (reachable && (acting || k === 'working' || k === 'needs-you')) {
        void l
          .pendingQueue()
          .catch(() => null)
          .then((n) => {
            pending = n
            controller.ingest(signals())
          })
      } else controller.ingest(signals())
    }

    late = {
      acknowledge: () => void controller.acknowledge(),
      controller,
      window: pillWin,
      feed,
      render,
      dispose() {
        offKill()
        offWin()
        if (ticker) clearInterval(ticker)
        controller.dispose()
        pillWin.dispose()
      },
    }
  }

  // ---- the models switch: a change restarts the whole app (the model port is built once, at start)
  const offModelsSwitch = deps.settings.onChange((_s, patch) => {
    if ('useLiveModels' in patch) {
      log('knack', 'the live models switch changed: restarting')
      if (deps.relaunch) deps.relaunch()
      else {
        app.relaunch()
        app.quit()
      }
    }
  })

  // ---- quitting: stop exactly the services this app started, then exit
  const onBeforeQuit = (): void => {
    quitting = true
    main.setQuitting()
  }
  app.on('before-quit', onBeforeQuit)
  const onWillQuit = (event: { preventDefault(): void }): void => {
    if (stackStopped) return
    event.preventDefault()
    if (stackStopped === false && !stopping) {
      stopping = true
      void stack.stop().finally(() => {
        stackStopped = true
        app.exit(0)
      })
    }
  }
  let stopping = false
  app.on('will-quit', onWillQuit)
  const signalQuit = (): void => app.quit()
  for (const sig of ['SIGTERM', 'SIGINT', 'SIGHUP'] as const) process.once(sig, signalQuit)

  return {
    stack,
    mainWindow: main,
    planned,
    modelStatus: status,
    attach,
    feedAgentSample: (s) => late?.feed(s),
    openMain: () => dispatch({ type: 'dock-click' }),
    info: () => ({
      stack: stack.state(),
      model: status(),
      pill: { kind: late?.controller.state().kind ?? 'idle', text: late?.controller.state().text ?? '', visible: late?.window.isVisible() ?? false, bounds: late?.window.bounds() ?? null, clickThrough: late?.window.clickThrough() ?? null },
      window: { ...main.state(), focused: main.isFocused() },
      memo,
    }),
    async dispose() {
      offStack()
      offDock()
      offModelsSwitch()
      app.off('activate', onActivate)
      app.off('second-instance', onSecond)
      app.off('before-quit', onBeforeQuit)
      app.off('will-quit', onWillQuit)
      late?.dispose()
      unprotocol()
      ipcMain.removeHandler(KNACK_IPC.get)
      ipcMain.removeAllListeners(KNACK_IPC.retry)
      await stack.stop()
      main.dispose()
      void quitting
    },
  }
}
