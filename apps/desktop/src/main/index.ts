import path from 'node:path'
import dotenv from 'dotenv'
import { app, systemPreferences } from 'electron'
import { IPC } from '../shared/ipc'
import type { EventArgs, EventChannel } from '../shared/ipc'
import { Bus } from './bus'
import { ConfirmBroker, dismissConfirmOnStepVerified } from './confirm'
import type { ServiceContext } from './context'
import { startDebugServer } from './debug-server'
import { redactingLog } from './gemini/redact'
import { registerHotkeys } from './hotkey'
import { shouldShowDockAtStart } from './panel-rules'
import { registerIpc } from './ipc'
import { registerLoginItem } from './login-item'
import { createPermissions } from './permissions'
import { registerTray } from './tray'
import type { ShellTray } from './tray'
import { createServices } from './services'
import { registerSession } from './session'
import { registerShowtime } from './showtime'
import { restoreProfile } from './showtime/seed'
import { SettingsStore } from './settings'
import { StateStore } from './state'
import { createDispatcher } from './tools/dispatcher'
import { registerToast } from './toast'
import { adoptOwner, createWindows } from './windows'

// The key lives only in REPO/.env; it is never logged or sent to a renderer.
if (process.env.ALONGSIDE_USERDATA) app.setPath('userData', path.resolve(process.env.ALONGSIDE_USERDATA))
dotenv.config({ path: path.join(app.getAppPath(), '.env'), quiet: true })

const flag = (name: string) => process.env[name] === '1'
let shellTray: ShellTray | null = null // SHELL: the menu-bar item keeps the app alive when the dock window is hidden

void app.whenReady().then(async () => {
  const headless = flag('ALONGSIDE_HEADLESS')
  const userDataDir = app.getPath('userData')

  const bus = new Bus()
  const settings = new SettingsStore(userDataDir)
  const state = new StateStore(settings.get())
  // SHELL2: the panel stays hidden unless showDock is on, setup is unfinished, or there is no menu bar item to reopen it. The window still exists and runs (mic, wake spotter, Live session).
  const windows = createWindows({ noOverlay: flag('ALONGSIDE_NO_OVERLAY'), headless, showDockAtStart: shouldShowDockAtStart(settings.get(), headless) })

  const ctx: ServiceContext = {
    state,
    bus,
    settings,
    userDataDir,
    sendOverlay: (cmd) => windows.sendOverlay(IPC.overlayCmd, cmd),
    sendDock: <C extends EventChannel>(channel: C, ...args: EventArgs<C>) => windows.sendDock(channel, ...args),
    log: redactingLog((scope, ...args) => console.log(`[${scope}]`, ...args)), // LIVE: no key/blob/long text in any lane's logs
  }

  // Coalesce bursts of patches into one broadcast per tick.
  let flushQueued = false
  state.subscribe(() => {
    if (flushQueued) return
    flushQueued = true
    setImmediate(() => {
      flushQueued = false
      windows.broadcast(IPC.stateUpdate, state.get())
    })
  })

  // DEMO: a walkthrough that was killed mid-way left the demo profile in place: put the real one back before anything reads it.
  await restoreProfile(userDataDir).catch(() => undefined)
  const services = createServices(ctx)
  if (flag('ALONGSIDE_DEV_STAGE') || flag('ALONGSIDE_RECORD') || process.env.ALONGSIDE_REPLAY) void import('./dev').then((dev) => dev.installDev({ ctx, services })) // QA hooks + record/replay (dev only)
  const confirm = new ConfirmBroker(state)
  dismissConfirmOnStepVerified(bus, confirm) // LIVE: a verified step dismisses a stale approval panel
  const dispatch = createDispatcher(ctx, services, confirm)
  const session = registerSession(ctx, services, confirm)
  const permissions = createPermissions({ log: (...args) => ctx.log('permissions', ...args) })
  registerIpc({ ctx, services, windows, dispatch, confirm, session, permissions })
  const showtime = registerShowtime({ ctx, services, windows, dispatch, confirm, session }) // DEMO: IPC showtime:* + bus showtime:request

  const unregisterHotkeys = registerHotkeys(bus, settings, { state, stop: (r) => session.stop(r), togglePanel: () => shellTray?.togglePanel() })
  // NOTIFY: permission prompts also appear as a toast at the top of the screen (settings.confirmStyle; no window when headless / no overlay).
  const toast = registerToast({ ctx, adoptOwner, disabled: headless || flag('ALONGSIDE_NO_OVERLAY') })
  const unregisterLoginItem = registerLoginItem(settings, { log: (...args) => ctx.log('login-item', ...args) })
  if (!headless) shellTray = registerTray({ bus, state, settings, windows, stop: (r) => session.stop(r), showtimeRunning: () => showtime.active(), log: (...args) => ctx.log('tray', ...args) })
  app.on('will-quit', () => {
    void showtime.dispose()
    shellTray?.dispose()
    toast.dispose()
    unregisterLoginItem()
    permissions.dispose()
    unregisterHotkeys()
    services.agents.dispose?.() // AGENTS hook: dispose on quit
    settings.flush()
  })

  // The debug server has no auth (it serves /shot, /state, /tool, /settings): opt-in only, never by default.
  if (flag('ALONGSIDE_DEBUG')) {
    startDebugServer({ ctx, services, dispatch, session, capture: { overlayPng: windows.overlayPng, dockPng: windows.dockPng }, tray: shellTray ?? undefined })
  }

  if (!headless && !flag('ALONGSIDE_MOCK') && process.platform === 'darwin' && systemPreferences.getMediaAccessStatus('microphone') === 'not-determined') {
    void systemPreferences.askForMediaAccess('microphone')
  }
})

// With a menu-bar item the app keeps running when the dock is hidden; without one there is no way back in, so quit.
app.on('window-all-closed', () => {
  if (!shellTray?.hasTray()) app.quit()
})
