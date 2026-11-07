// The Knack shell: the main window, the services it needs, the application menu and Dock icon, quitting, and the corner column's choreography. One app: dashboard window +
// menu-bar item + corner pill, which starts the engine and the agent itself. Two steps, because the window must be up before the slow things happen:
//
//   createKnackShell   at the very start of main: the "Starting Knack…" window appears, the models are chosen (live when a key is present and the boot check passes,
//                      example data otherwise), the services are started, the dashboard loads when they answer.
//   shell.attach       once the kill switch, the HUD and the agent-service poll exist: events flow into the shell machine (shell-machine.ts), whose effects are performed
//                      here (minimise the window, draw the pill, show a card, count on the menu bar and the Dock).
//
// The decisions are in the pure modules (model-mode, stack, activity, shell-machine, quit-guard, window-state, app-menu); this file connects them to Electron and has no
// rules of its own.
import path from 'node:path'
import { app, BrowserWindow, dialog, ipcMain, Menu } from 'electron'
import { APP_NAME, APP_ORIGIN } from '../../shared/brand'
import type { HudActivity } from '../../shared/hud'
import type { Settings } from '../../shared/settings'
import { KNACK_IPC } from '../../shared/knack'
import type { HudModel } from '../hud-model'
import { readServiceToken } from '../kill-file'
import { applyModeEnv, applyStackEnv } from './stack-config'
import { createActivityTracker, type ActivityTracker } from './activity'
import { registerAppProtocol } from './app-protocol-electron'
import type { Upstream } from './app-protocol'
import { buildAppMenuTemplate, buildDockMenuTemplate } from './app-menu'
import { registerDock } from './dock'
import { createMainWindow, type MainWindow } from './mainwindow'
import { canSwitchModels, keyPresent, modelStatus, planModels, type ModelDecision } from './model-mode'
import type { PillSignals } from './pill-state'
import { createQuitGuard, type QuitGuard } from './quit-guard'
import { INITIAL_SHELL, TIMING, reduce, type Effect, type ShellEvent, type ShellState } from './shell-machine'
import { shellPages, uiStateOf } from './shell-pages'
import type { Stack, StackConfig, StackState } from './stack'
import { createRealStack } from './stack-real'
import { createWindowStateStore } from './window-state'

export type MenubarState = 'working' | 'workingOff' | 'stopped' | 'idle' | 'count' | 'marker'

export interface KnackEarlyDeps {
  settings: { get(): Settings; patch(p: Partial<Settings>, opts?: { trusted?: boolean }): unknown; onChange(l: (s: Settings, patch: Partial<Settings>) => void): () => void }
  userDataDir: string
  config: StackConfig
  /** Windows exist and work but are never shown (the hidden check). */
  hidden: boolean
  env: Record<string, string | undefined>
  /** Lists the models the key can use (the desktop model port's boot check); true when it passed. Called once, only when live is wanted and a key exists. */
  bootCheck: () => Promise<boolean>
  /** The kill switch's registered global accelerator, to show on the menu item. */
  killAccelerator: () => string | null
  /** Stop Everything from the menus (the kill switch). */
  stopEverything: () => void
  /** The brand glyph file's text, for the starting page. */
  glyphSvg: string
  /** Relaunch the app (the models switch). Default: app.relaunch then app.quit. */
  relaunch?: () => void
  stack?: Stack
  upstream?: Upstream
  log: (...args: unknown[]) => void
  /** Observation hook: every effect the machine asked for (the hidden check records them). */
  onEffect?: (e: Effect, event: ShellEvent) => void
  /** The menu bar's state (the tray shows it): working dot, count, stopped square, marker. */
  onMenubar?: (state: MenubarState, count?: number) => void
  /** Called after every event the machine heard, so the tray (and anything else that shows the machine) can look again. */
  onChange?: () => void
  /** Shows a native sheet; default is dialog.showMessageBox. Injectable for the check. */
  showSheet?: (o: { message: string; detail?: string; buttons: readonly [string, string] }) => Promise<'stop_and_quit' | 'keep_working'>
}

export interface KnackLateDeps {
  kill: { trigger(source: 'hud'): Promise<unknown>; isKilled(): boolean; subscribe(cb: () => void): () => void }
  /** The corner column (the HUD model, in corner mode). */
  hud: Pick<HudModel, 'setActivity' | 'setApproval' | 'setHold' | 'setCorner' | 'state'>
  /** One look at the desk: a reason to stay away (a denylisted app, a password field, an unreadable state) and whether a screen is shared. Fails closed. */
  probe: () => Promise<{ suppressed: string | null; presenting: boolean }>
  /** Approvals waiting in the queue (null when the engine cannot be asked). */
  pendingQueue: () => Promise<number | null>
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
  /** An agent of this app is acting on the worker's own screen (the desktop's act-for-me). */
  feedLocalActing(acting: boolean): void
  /** The Dock icon, Activate, Open Knack. */
  openMain(): void
  /** Settings… (the app menu, the menu bar item): open Knack on its Settings (#/settings; the dashboard's own Command-comma opens the same). */
  openSettings(): void
  /** Feeds the machine directly (the dev hook, the hidden check). Returns the machine's state after the event. */
  dispatch(event: ShellEvent): ShellState
  quitGuard(): QuitGuard
  /** What the menu bar item shows: the label of what is running, how many things need the worker, and whether everything is stopped. */
  trayStatus(): { working: string | null; needsYou: number; stopped: boolean }
  info(): KnackInfo
  dispose(): Promise<void>
}

export interface KnackInfo {
  stack: StackState
  model: { live: boolean | null; text: string }
  machine: ShellState
  window: ReturnType<MainWindow['state']> & { bounds: { x: number; y: number; width: number; height: number } | null }
  tracker: string
}

const asObj = (v: unknown): Record<string, unknown> | null => (typeof v === 'object' && v !== null && !Array.isArray(v) ? (v as Record<string, unknown>) : null)

/** GET /agents/runs, as a list or { data: [...] }, to the ids, states and (when listed) children done and in all. */
export function runsOf(raw: unknown): NonNullable<PillSignals['runs']>[number][] {
  const list = Array.isArray(raw) ? raw : (asObj(raw) && Array.isArray(asObj(raw)!.data) ? (asObj(raw)!.data as unknown[]) : [])
  const out: NonNullable<PillSignals['runs']>[number][] = []
  for (const r of list) {
    const o = asObj(r)
    const id = typeof o?.run_id === 'string' ? o.run_id : typeof o?.id === 'string' ? o.id : null
    if (!o || !id || typeof o.state !== 'string') continue
    const kids = Array.isArray(o.children) ? o.children.map(asObj).filter((c): c is Record<string, unknown> => c !== null) : []
    const done = kids.filter((c) => typeof c.state === 'string' && ['done', 'partial'].includes(c.state)).length
    out.push({ id, state: o.state, ...(kids.length > 0 ? { progress: { done, total: kids.length } } : {}) })
  }
  return out
}

/** The fixed words of the card that a blocked run raises. (No model text on a surface.) */
export const APPROVAL_CARD = { title: 'A run is waiting for you', body: 'It needs your approval to go on.', source: 'your run' } as const

export function createKnackShell(deps: KnackEarlyDeps): KnackShell {
  const { config, env, log } = deps
  const store = createWindowStateStore({ file: path.join(deps.userDataDir, 'knack-window.json') })
  const main = createMainWindow({ store, hidden: deps.hidden, devOrigin: config.devUrl ? new URL(config.devUrl).origin : null })
  const stack = deps.stack ?? createRealStack(config, (...a) => log('stack', ...a))
  let decision: ModelDecision | null = null
  let mockNow: boolean | null = null
  let stackStopped = false
  let stopping = false
  let machine: ShellState = { ...INITIAL_SHELL, moveAside: deps.settings.get().moveAsideWhileWorking }
  let late: KnackLateDeps | null = null
  let tracker: ActivityTracker | null = null
  let minimiseTimer: ReturnType<typeof setTimeout> | null = null
  let doneTimers: ReturnType<typeof setTimeout>[] = []
  let dashboardLoaded = false
  const intervals: ReturnType<typeof setInterval>[] = []

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

  // "Use live models" in the dashboard's Settings: only this window's own page (the app's address, or the dev server's in development) may ask.
  const fromOurPage = (e: { sender: { id: number }; senderFrame?: { url: string } | null }): boolean => {
    if (!main.owns(e.sender.id)) return false
    const url = e.senderFrame?.url ?? ''
    return url.startsWith(APP_ORIGIN) || (config.devUrl !== null && url.startsWith(config.devUrl))
  }
  ipcMain.handle(KNACK_IPC.modelsGet, (event) => {
    if (!fromOurPage(event)) throw new Error('shell IPC from an unknown sender')
    return { useLiveModels: deps.settings.get().useLiveModels, keyPresent: keyPresent(env), live: status().live, running: machine.activity === 'working' || machine.activity === 'voice' }
  })
  ipcMain.handle(KNACK_IPC.modelsSet, (event, on: unknown) => {
    if (!fromOurPage(event)) throw new Error('shell IPC from an unknown sender')
    const can = canSwitchModels({ on, hasKey: keyPresent(env), running: machine.activity === 'working' || machine.activity === 'voice' })
    if (!can.ok) return can
    deps.settings.patch({ useLiveModels: on as boolean }, { trusted: true }) // main restarts the app when it changes (below)
    return { ok: true }
  })

  const dashboardBase = (s: StackState): string => (s.phase === 'ready' && s.dashboard === 'dev-server' && config.devUrl ? config.devUrl : APP_ORIGIN)
  const pushUi = (): void => main.pushUiState(ui())
  const offStack = stack.subscribe((s) => {
    if (s.phase === 'ready') {
      // This app's own environment follows the stack it ended up with: the kill file and the token live in that data directory.
      const dir = stack.dataDir()
      if (dir) applyStackEnv(env, config.ports, dir)
      mockNow = s.mock
      if (!dashboardLoaded) {
        dashboardLoaded = true
        main.loadDashboard(`${dashboardBase(s)}/`)
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

  // ---- the machine, and the performer of its effects
  const wasRunning = (): boolean => machine.activity === 'working' || machine.activity === 'voice'
  const needsYouHash = (item?: string): string => `#/needs-you${item ? `?item=${encodeURIComponent(item)}` : ''}`

  const activityOf = (phase: HudActivity['phase'], label: string, over: Partial<HudActivity> = {}): HudActivity => ({ phase, label, step: null, of: null, leaving: false, ...over })
  const clearDoneTimers = (): void => {
    for (const t of doneTimers) clearTimeout(t)
    doneTimers = []
  }

  const perform = (e: Effect, ev: ShellEvent): void => {
    const hud = late?.hud
    deps.onEffect?.(e, ev)
    switch (e.type) {
      case 'minimizeMainAfter':
        if (minimiseTimer) clearTimeout(minimiseTimer)
        minimiseTimer = setTimeout(() => {
          minimiseTimer = null
          // Still a run, and the window is still up and focused (the worker may have moved on in 400 ms): then it steps aside.
          const w = main.state()
          if (machine.activity === 'working' && w.visible && w.focused && machine.moveAside) main.minimise()
        }, e.ms)
        return
      case 'showPill':
        clearDoneTimers()
        hud?.setActivity(activityOf('working', e.label))
        return
      case 'pillLabel': {
        const cur = hud?.state().activity
        if (cur && cur.phase === 'working') hud?.setActivity({ ...cur, label: e.label })
        return
      }
      case 'pillCount': {
        const cur = hud?.state().activity
        if (cur && cur.phase === 'working') hud?.setActivity({ ...cur, step: e.n, of: e.m })
        return
      }
      case 'pillVoice':
        hud?.setActivity(activityOf('voice', e.label))
        return
      case 'pillCheck':
        clearDoneTimers()
        hud?.setActivity(activityOf('done', 'Done'))
        doneTimers.push(
          setTimeout(() => hud?.setActivity(activityOf('done', 'Done', { leaving: true })), e.ms),
          setTimeout(() => hud?.setActivity(null), e.ms + TIMING.fadeMs + 20),
        )
        return
      case 'pillError':
        clearDoneTimers()
        hud?.setActivity(activityOf('error', tracker?.state().text === 'Lost contact' ? 'Lost contact' : 'Something went wrong'))
        return
      case 'hideCornerWindow': {
        const cur = hud?.state().activity
        if (cur && (cur.phase === 'error' || cur.phase === 'voice')) hud?.setActivity(null) // a done check leaves by its own timers (it fades first)
        return
      }
      case 'stoppedCardReplacesPill':
        clearDoneTimers()
        hud?.setActivity(null) // the Stopped card is drawn from the kill state
        return
      case 'cardAbovePill':
        if (e.kind === 'approval') hud?.setApproval({ id: `a_${Date.now().toString(36)}`, ...APPROVAL_CARD })
        return
      case 'closeCard':
        hud?.setApproval(null)
        return
      case 'menubar':
        deps.onMenubar?.(e.state, e.count)
        return
      case 'dockBadge':
        app.dock?.setBadge(e.count > 0 ? String(e.count) : '')
        return
      case 'stopAll':
        if (late && !late.kill.isKilled()) void late.kill.trigger('hud')
        return
      case 'openOrRestoreMain':
        main.show()
        if (dashboardLoaded) main.loadDashboard(`${dashboardBase(stack.state())}/${needsYouHash(e.item)}`)
        return
      case 'openMain':
      case 'restoreMain':
      case 'focusMain':
        main.show()
        return
      case 'holdCards':
        hud?.setHold({ ask: true })
        return
      case 'releaseCards':
        hud?.setHold({ ask: false })
        return
      default:
        return // informational: the window was already hidden or minimised by the worker; the banner is the dashboard's own
    }
  }

  const dispatch = (ev: ShellEvent): ShellState => {
    const r = reduce(machine, ev)
    machine = r.state
    for (const e of r.effects) perform(e, ev)
    deps.onChange?.()
    return machine
  }

  // The app menu, the Dock icon and its menu
  const showMain = (): void => void dispatch({ type: 'menu_open_knack' })
  const openSettings = (): void => {
    dispatch({ type: 'menu_open_knack' })
    if (dashboardLoaded) main.loadDashboard(`${dashboardBase(stack.state())}/#/settings`)
  }
  const handlers = { openSettings, showWindow: showMain, stopEverything: deps.stopEverything }
  Menu.setApplicationMenu(Menu.buildFromTemplate(buildAppMenuTemplate({ appName: APP_NAME, platform: process.platform, isPackaged: app.isPackaged, killAccelerator: deps.killAccelerator(), handlers })))
  app.setAboutPanelOptions({ applicationName: APP_NAME, applicationVersion: app.getVersion(), copyright: 'Built for Hack the Burgh XIII' })
  const offDock = registerDock(deps.settings, { dock: app.dock ?? undefined, hidden: deps.hidden, log: (...a) => log(...a) })
  app.dock?.setMenu(Menu.buildFromTemplate(buildDockMenuTemplate({ appName: APP_NAME, handlers })))

  // The Dock icon (or the app switcher) with no window up, and a second launch, bring the window forward; they never open a second one.
  const onActivate = (): void => void dispatch({ type: 'dock_click_or_activate' })
  app.on('activate', onActivate)
  app.on('second-instance', onActivate)

  // The window's real state, so the machine matches what the worker did with it.
  const offWin = main.subscribe((e) => {
    if (e === 'focus') dispatch({ type: 'window_state', window: 'open', focused: true })
    else if (e === 'blur') dispatch({ type: 'window_state', focused: false })
    else if (e === 'minimize') dispatch({ type: 'window_minimise' })
    else if (e === 'hide') dispatch({ type: 'window_close' })
    else if (e === 'restore' || e === 'show') dispatch({ type: 'window_state', window: 'open' })
    if (e === 'focus') tracker?.acknowledge()
  })

  // The worker's setting for moving aside.
  const offSettings = deps.settings.onChange((_s, patch) => {
    if ('moveAsideWhileWorking' in patch) dispatch({ type: 'settings', moveAside: deps.settings.get().moveAsideWhileWorking })
    // The models switch: a change restarts the whole app (the model port is built once, at start).
    if ('useLiveModels' in patch) {
      log('knack', 'the live models switch changed: restarting')
      if (deps.relaunch) deps.relaunch()
      else {
        app.relaunch()
        app.quit()
      }
    }
  })

  // ---- quitting: ask while something runs; then stop exactly the services this app started, then exit
  const showSheet =
    deps.showSheet ??
    (async (o) => {
      const win = main.state().visible ? BrowserWindow.getFocusedWindow() : null
      const opts = { type: 'question' as const, message: o.message, ...(o.detail ? { detail: o.detail } : {}), buttons: [...o.buttons], defaultId: 1, cancelId: 1, noLink: true }
      const r = win ? await dialog.showMessageBox(win, opts) : await dialog.showMessageBox(opts)
      return r.response === 0 ? ('stop_and_quit' as const) : ('keep_working' as const)
    })
  const guard = createQuitGuard({
    running: () => wasRunning(),
    awayRoutineDueWithin24h: () => false, // the engine does not say yet; the sheet adds its line when it does (row 18)
    ask: showSheet,
    stopAll: () => (late ? late.kill.trigger('hud') : undefined),
    quit: () => app.quit(),
    markQuitting: () => main.setQuitting(),
  })
  app.on('before-quit', guard.onBeforeQuit)
  const onWillQuit = (event: { preventDefault(): void }): void => {
    if (stackStopped) return
    event.preventDefault()
    if (stopping) return
    stopping = true
    void stack.stop().finally(() => {
      stackStopped = true
      app.exit(0)
    })
  }
  app.on('will-quit', onWillQuit)
  const signalQuit = (): void => app.quit()
  for (const sig of ['SIGTERM', 'SIGINT', 'SIGHUP'] as const) process.once(sig, signalQuit)

  // ---- the corner column and the sources of events (attached later)
  let pending: number | null = null
  let reachable = false
  let supervisor: string | null = null
  let runs: PillSignals['runs'] = []
  let localActing = false
  let lastNeeds = -1

  const signals = (): PillSignals => ({ reachable, supervisor, runs, killed: late?.kill.isKilled() === true || supervisor === 'killed', pending, local: localActing })

  const attach = (l: KnackLateDeps): void => {
    late = l
    tracker = createActivityTracker({ emit: (e) => void dispatch(e) })
    l.hud.setCorner({
      review: (id) => void dispatch({ type: 'review_clicked', item: id }),
      later: () => void dispatch({ type: 'card_dismissed' }),
      open: () => {
        dispatch({ type: 'menu_open_knack' })
        dispatch({ type: 'error_acknowledged' })
        tracker?.acknowledge()
      },
      voiceEnd: () => void dispatch({ type: 'voice_end' }),
    })
    // The kill switch (the pill's Stop, the menus, the keys) is one event for the machine.
    let wasKilled = l.kill.isKilled()
    const offKill = l.kill.subscribe(() => {
      const k = l.kill.isKilled()
      if (k !== wasKilled) {
        wasKilled = k
        dispatch({ type: k ? 'kill' : 'resume' })
      }
    })
    // What may not be covered: a password field, a denylisted app, a screen share (and the Ask bar, set by the machine). Probed every 2 s.
    const watch = (): void => {
      void l
        .probe()
        .catch(() => ({ suppressed: 'probe_failed', presenting: false }))
        .then((p) => {
          const secure = p.suppressed !== null
          l.hud.setHold({ secure, share: p.presenting })
          if (secure !== machine.secureInput) dispatch({ type: 'secure_input', on: secure })
        })
    }
    watch()
    intervals.push(setInterval(watch, 2000))
    // The approval count for the menu bar and the Dock badge.
    const count = (): void =>
      void l
        .pendingQueue()
        .then((n) => {
          if (n !== null && n !== lastNeeds) {
            lastNeeds = n
            dispatch({ type: 'needs_you_count', n })
          }
        })
        .catch(() => undefined)
    count()
    intervals.push(setInterval(count, 30_000))
    offLate = (): void => offKill()
  }
  let offLate: (() => void) | null = null

  const ingest = (): void => {
    const k = tracker?.state().kind
    // The queue count is read fresh while a run works or has just ended, so "something new to approve" is measured against the count at the start.
    if (late && reachable && (supervisor === 'running' || runs.some((r) => r.state === 'running') || localActing || k === 'working' || k === 'needs-you')) {
      void late
        .pendingQueue()
        .catch(() => null)
        .then((n) => {
          pending = n
          tracker?.ingest(signals())
        })
    } else tracker?.ingest(signals())
  }

  return {
    stack,
    mainWindow: main,
    planned,
    modelStatus: status,
    attach,
    feedAgentSample(sample) {
      const health = asObj(sample.health)
      reachable = health !== null
      const sup = asObj(health?.supervisor)
      supervisor = typeof sup?.state === 'string' ? sup.state : null
      runs = runsOf(sample.runs)
      ingest()
    },
    feedLocalActing(acting) {
      if (acting === localActing) return
      localActing = acting
      reachable = reachable || acting // an agent of this app acting needs no service to be heard
      ingest()
    },
    openMain: () => void dispatch({ type: 'menu_open_knack' }),
    openSettings,
    dispatch,
    quitGuard: () => guard,
    trayStatus: () => ({
      working: machine.activity === 'working' ? (late?.hud.state().activity?.label ?? 'Starting').toLowerCase() : machine.activity === 'voice' ? 'listening' : null,
      needsYou: machine.needsYou,
      stopped: machine.activity === 'stopped',
    }),
    info: () => ({
      stack: stack.state(),
      model: status(),
      machine,
      window: { ...main.state(), bounds: main.window()?.getBounds() ?? null },
      tracker: tracker?.state().kind ?? 'none',
    }),
    async dispose() {
      offStack()
      offDock()
      offSettings()
      offWin()
      offLate?.()
      for (const i of intervals) clearInterval(i)
      clearDoneTimers()
      if (minimiseTimer) clearTimeout(minimiseTimer)
      app.off('activate', onActivate)
      app.off('second-instance', onActivate)
      app.off('before-quit', guard.onBeforeQuit)
      app.off('will-quit', onWillQuit)
      tracker?.dispose()
      unprotocol()
      ipcMain.removeHandler(KNACK_IPC.get)
      ipcMain.removeHandler(KNACK_IPC.modelsGet)
      ipcMain.removeHandler(KNACK_IPC.modelsSet)
      ipcMain.removeAllListeners(KNACK_IPC.retry)
      await stack.stop()
      main.dispose()
    },
  }
}
