import path from 'node:path'
import dotenv from 'dotenv'
import { app, nativeImage, systemPreferences } from 'electron'
import { IPC } from '../shared/ipc'
import type { EventArgs, EventChannel } from '../shared/ipc'
import { Bus } from './bus'
import { ConfirmBroker, dismissConfirmOnStepVerified } from './confirm'
import type { ServiceContext } from './context'
import { startDebugServer } from './debug-server'
import { redactingLog } from './model-port/redact'
import { createModelPortFromEnv, runBootCheck } from './model-port'
import { experimentOn, featureOn, forcedSettings } from './feature-flags'
import { HELP_LEVEL_LABELS } from '../shared/protocol'
import { appIconPath } from './app-icon'
import { createUnderstudyCore, registerUnderstudy } from './understudy'
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
// Understudy: the repo-level .env holds OPENAI_API_KEY and OPENAI_MODEL_*; the app-level one (Gemini voice key) is still honoured.
// dotenv never overrides a variable that is already set, and nothing is printed (quiet).
dotenv.config({ path: path.join(app.getAppPath(), '.env'), quiet: true })
dotenv.config({ path: path.join(app.getAppPath(), '../../.env'), quiet: true })

const flag = (name: string) => process.env[name] === '1'
let shellTray: ShellTray | null = null // SHELL: the menu-bar item keeps the app alive when the dock window is hidden

void app.whenReady().then(async () => {
  const headless = flag('ALONGSIDE_HEADLESS')
  const userDataDir = app.getPath('userData')
  // The brand mark as the dock icon (macOS), instead of the Electron default.
  if (process.platform === 'darwin') {
    const icon = appIconPath(app.getAppPath(), process.resourcesPath)
    if (icon) app.dock?.setIcon(nativeImage.createFromPath(icon))
  }

  const bus = new Bus()
  const settings = new SettingsStore(userDataDir, { forced: forcedSettings() }) // voice-adjacent settings pinned off by feature flags
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
  // Understudy: every model call goes through this one port (OpenAI, or the mock under UNDERSTUDY_MOCK=1 / ALONGSIDE_MOCK=1).
  ctx.modelPort = createModelPortFromEnv({ log: ctx.log })
  void runBootCheck(ctx.modelPort, ctx.log) // lists the models this key can use; a problem is logged in plain English, never fatal

  // Understudy: engine client, coach telemetry, identity. Must exist before createServices (the overlay is wrapped with it).
  const core = createUnderstudyCore(ctx)

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

  // Understudy: kill switch, HUD (kill pill, proposal toast), desk signals. The shortcut, the tray item and the pill all reach the same switch.
  const understudy = registerUnderstudy({ ctx, core, services, confirm, bus, stopSession: (r) => session.stop(r), headless, noOverlay: flag('ALONGSIDE_NO_OVERLAY') })
  const unregisterHotkeys = registerHotkeys(bus, settings, { state, stop: (r) => session.stop(r), togglePanel: () => shellTray?.togglePanel(), kill: () => void understudy.kill.trigger('hotkey'), raisePanel: () => windows.showDock() })
  // NOTIFY: permission prompts also appear as a toast at the top of the screen (settings.confirmStyle; no window when headless / no overlay).
  const toast = registerToast({ ctx, adoptOwner, disabled: headless || flag('ALONGSIDE_NO_OVERLAY') })
  const unregisterLoginItem = registerLoginItem(settings, { log: (...args) => ctx.log('login-item', ...args) })
  if (!headless) shellTray = registerTray({ bus, state, settings, windows, stop: (r) => session.stop(r), showtimeRunning: () => showtime.active(), kill: { trigger: () => void understudy.kill.trigger('tray'), clear: () => void understudy.kill.clear(), isKilled: () => understudy.kill.isKilled() }, openQueue: understudy.openQueue, captureMode: () => core.capture.mode(), coachLine: () => { const c = understudy.chip.current(); return c ? `Help level ${c.level}: ${HELP_LEVEL_LABELS[c.level]}` : null }, openDashboard: understudy.openDashboard, voiceMenu: () => featureOn('voice'), cueMenu: () => experimentOn('cue'), queueCount: () => understudy.hudModel.state().queuePending, agentActing: () => understudy.hudModel.state().agentActing, log: (...args) => ctx.log('tray', ...args) })
  app.on('will-quit', () => {
    void showtime.dispose()
    shellTray?.dispose()
    toast.dispose()
    unregisterLoginItem()
    permissions.dispose()
    unregisterHotkeys()
    understudy.dispose()
    core.dispose()
    services.agents.dispose?.() // AGENTS hook: dispose on quit
    settings.flush()
  })

  // The debug server has no auth (it serves /shot, /state, /tool, /settings): opt-in only, never by default.
  if (flag('ALONGSIDE_DEBUG')) {
    startDebugServer({ ctx, services, dispatch, session, capture: { overlayPng: windows.overlayPng, overlayText: windows.overlayText, dockPng: windows.dockPng, hudPng: understudy.hud.png, hudPreview: understudy.hud.preview, hudVisible: () => understudy.hud.window()?.isVisible() ?? null }, understudy: { kill: understudy.kill, hud: understudy.hudModel, dom: { status: () => ({ port: understudy.extServer()?.port() ?? null, pending: understudy.domGrounder.pending(), extensionSeenMs: understudy.extServer()?.lastSeenAt() ? Date.now() - (understudy.extServer()?.lastSeenAt() ?? 0) : null, ring: understudy.ring.current(), chip: understudy.chip.current(), capture: core.capture.mode(), coach: understudy.coachBrain.status() }) } }, tray: shellTray ?? undefined })
  }

  // Understudy: the microphone is only needed for voice or the wake word, both off unless their flags are set.
  if (!headless && !flag('ALONGSIDE_MOCK') && !flag('UNDERSTUDY_MOCK') && (featureOn('voice') || featureOn('wake')) && process.platform === 'darwin' && systemPreferences.getMediaAccessStatus('microphone') === 'not-determined') {
    void systemPreferences.askForMediaAccess('microphone')
  }
})

// With a menu-bar item the app keeps running when the dock is hidden; without one there is no way back in, so quit.
app.on('window-all-closed', () => {
  if (!shellTray?.hasTray()) app.quit()
})
