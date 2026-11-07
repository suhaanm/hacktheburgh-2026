import path from 'node:path'
import dotenv from 'dotenv'
import { app, nativeImage, powerMonitor, shell, systemPreferences } from 'electron'
import { IPC } from '../shared/ipc'
import type { EventArgs, EventChannel } from '../shared/ipc'
import { Bus } from './bus'
import { ConfirmBroker, dismissConfirmOnStepVerified } from './confirm'
import type { ServiceContext } from './context'
import { startDebugServer } from './debug-server'
import { wireAttention } from './attention-wiring'
import { createElectronAwareness } from './awareness/electron'
import { awarenessFlagOn } from './awareness/flags'
import { createConsoleProbe, createFrontmostSource, createScreenShareProbe } from './awareness/probes'
import type { Awareness } from './awareness'
import { applyChoice, cardState, trayAwareness } from './awareness-card'
import { startCue, stopCue, type CueStartContext } from './cue'
import { createContentKeeper, createCueSignals } from './cue-glue'
import { pStuckForTrigger } from './engine/coach-next'
import { isKilled } from './kill-flag'
import { configureLegacyRemote, createLegacyRemoteGate, legacyGateReader, legacyRemoteOn } from './legacy-remote'
import { liveFlagOn } from './live/flags'
import { registerLive } from './live/electron'
import type { LiveRegistration } from './live'
import type { CueSpeaker, CueVoice, LiveCuePort } from './cue/voice'
import { redactingLog } from './model-port/redact'
import { createModelPortFromEnv, runBootCheck } from './model-port'
import { experimentOn, featureOn, forcedSettings } from './feature-flags'
import { isSessionActive } from './tray'
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

  // Understudy: engine client, coach telemetry, identity. Must exist before createServices (the overlay is wrapped with it).
  const core = createUnderstudyCore(ctx)

  // The awareness module is created below (it needs the coach poller); the legacy gate, the consent card and the tray read it through this box.
  const awarenessBox: { a: Awareness | null } = { a: null }

  // LEGACY REMOTE (D38): the old Alongside paths that can send a frame, file text or audio to OpenAI or Gemini are OFF unless
  // UNDERSTUDY_LEGACY_REMOTE=1. With it on, every request is gated like the privacy ImageGate and announced to the engine's ledger first.
  if (legacyRemoteOn()) {
    const frontmost = createFrontmostSource()
    const consoleProbe = createConsoleProbe()
    configureLegacyRemote(
      createLegacyRemoteGate({
        engineUrl: core.endpoints.engine,
        killed: isKilled,
        log: ctx.log,
        gates: legacyGateReader({
          frontmost,
          console: consoleProbe,
          deny: () => ({ strict: awarenessBox.a?.getAwarenessState().strict ?? true, workerList: awarenessBox.a?.getAwarenessState().denylist ?? [] }),
          // Images need the worker's glance consent (the card); the wake word needs its own switch; text kinds rely on the launch flag.
          consent: (kind) => (kind === 'image' ? awarenessBox.a?.getAwarenessState().consent.trigger === true : kind === 'audio' ? settings.get().wakeEnabled === true : true),
          idleSeconds: () => {
            try {
              return powerMonitor.getSystemIdleTime()
            } catch {
              return null
            }
          },
          awaySeconds: () => settings.get().awaySeconds,
        }),
      }),
    )
    void runBootCheck(ctx.modelPort, ctx.log) // lists the models this key can use; a problem is logged in plain English, never fatal
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
  const awarenessFlag = awarenessFlagOn()
  registerIpc({
    ctx,
    services,
    windows,
    dispatch,
    confirm,
    session,
    permissions,
    awareness: { state: () => cardState(awarenessBox.a, awarenessFlag), consent: (raw) => (awarenessBox.a ? applyChoice(awarenessBox.a, raw, awarenessFlag) : cardState(null, false)) },
  })
  const showtime = registerShowtime({ ctx, services, windows, dispatch, confirm, session }) // DEMO: IPC showtime:* + bus showtime:request

  // Understudy: kill switch, HUD (kill pill, proposal toast), desk signals. The shortcut, the tray item and the pill all reach the same switch.
  // ONE coach poll, two readers: the coach brain's GET /coach/next carries p_stuck, which the awareness layer's stuck trigger reads.
  const cueContent = createContentKeeper()
  const understudy = registerUnderstudy({
    ctx,
    core,
    services,
    confirm,
    bus,
    stopSession: (r) => session.stop(r),
    headless,
    noOverlay: flag('ALONGSIDE_NO_OVERLAY'),
    onCoachDecision: (d) => awarenessBox.a?.observeStuck(pStuckForTrigger(d)),
    onPageContent: (rects) => cueContent.set(rects),
  })

  // Awareness (REQ-5, flag UNDERSTUDY_X_AWARENESS): always-on features, triggered and opt-in periodic glances. Real Screen Recording is
  // never requested here; without it the glance reports a plain skip.
  const awareness: Awareness | null = awarenessFlag
    ? createElectronAwareness({ userDataDir, endpoints: core.endpoints, identity: () => core.engine.identity, killed: isKilled, workSession: () => understudy.coachPoller.lastState()?.task != null, log: ctx.log })
    : null
  awarenessBox.a = awareness
  awareness?.start()

  // What Cue reads before it speaks: typing, seconds since the last input, a denylisted app or secure input, away.
  const cueSignals = createCueSignals({
    frontmost: createFrontmostSource(),
    console: createConsoleProbe(),
    deny: () => ({ strict: awareness?.getAwarenessState().strict ?? true, workerList: awareness?.getAwarenessState().denylist ?? [] }),
    idleSeconds: () => {
      try {
        return powerMonitor.getSystemIdleTime()
      } catch {
        return null
      }
    },
    awaySeconds: () => settings.get().awaySeconds,
  })
  const cueOn = experimentOn('cue')
  if (cueOn) cueSignals.start()

  const unregisterHotkeys = registerHotkeys(bus, settings, { look: awareness ? () => void awareness.hotkey() : undefined, state, stop: (r) => session.stop(r), togglePanel: () => shellTray?.togglePanel(), kill: () => void understudy.kill.trigger('hotkey'), raisePanel: () => windows.showDock() })
  // NOTIFY: permission prompts also appear as a toast at the top of the screen (settings.confirmStyle; no window when headless / no overlay).
  const toast = registerToast({ ctx, adoptOwner, disabled: headless || flag('ALONGSIDE_NO_OVERLAY') })
  const unregisterLoginItem = registerLoginItem(settings, { log: (...args) => ctx.log('login-item', ...args) })
  if (!headless) shellTray = registerTray({ bus, state, settings, windows, stop: (r) => session.stop(r), showtimeRunning: () => showtime.active(), kill: { trigger: () => void understudy.kill.trigger('tray'), clear: () => void understudy.kill.clear(), isKilled: () => understudy.kill.isKilled() }, awareness: awareness ? trayAwareness(awareness) : undefined, openQueue: understudy.openQueue, captureMode: () => core.capture.mode(), coachLine: () => { const c = understudy.chip.current(); return c ? `Help level ${c.level}: ${HELP_LEVEL_LABELS[c.level]}` : null }, openDashboard: understudy.openDashboard, voiceMenu: () => featureOn('voice'), cueMenu: () => experimentOn('cue'), queueCount: () => understudy.hudModel.state().queuePending, agentActing: () => understudy.hudModel.state().agentActing, log: (...args) => ctx.log('tray', ...args) })
  // The attention layer (the one-voice router). One call; null with its flag off.
  const screenShare = createScreenShareProbe()
  const attentionWiring = wireAttention({
    endpoints: core.endpoints,
    person: () => core.engine.identity.person,
    settings,
    hudModel: understudy.hudModel,
    openExternal: (url) => void shell.openExternal(url).catch(() => undefined),
    kill: understudy.kill,
    idleSeconds: () => powerMonitor.getSystemIdleTime(),
    probes: { screenSharing: () => screenShare.read() },
    voiceSession: () => isSessionActive(state.get().phase),
    tray: shellTray ?? undefined,
    chip: understudy.chip,
    toast,
    proposals: understudy.proposals,
    log: ctx.log,
  })

  // Cue (the stuck-rescue cards, flag UNDERSTUDY_X_CUE and the worker's own switch). Voice and speaker are late-bound: Live needs Cue's port
  // and Cue needs Live's voice, so Cue gets thin proxies that read the Live registration once it exists.
  const liveBox: { reg: LiveRegistration | null } = { reg: null }
  const cueVoice: CueVoice = { listenOnce: (o, opts) => (liveBox.reg ? liveBox.reg.voice.listenOnce(o, opts) : Promise.resolve(null)) }
  const cueSpeaker: CueSpeaker = {
    say: (id) => liveBox.reg?.speaker.say(id),
    stop: () => liveBox.reg?.speaker.stop?.(),
    registerLine: (id, text) => (liveBox.reg?.speaker as { registerLine?: (i: string, t: string) => void } | undefined)?.registerLine?.(id, text),
  }
  const cue = startCue({
    ...ctx,
    person: () => core.engine.identity.person,
    voice: cueVoice,
    speaker: cueSpeaker,
    workerUsedVoice: () => liveBox.reg?.workerUsedVoice() ?? false,
    signals: { typingNow: cueSignals.typingNow, quietS: cueSignals.quietS, away: cueSignals.away, suppressed: cueSignals.suppressed } as NonNullable<CueStartContext['signals']>,
    // The page's visible text and controls from the DOM tracker's latest answer (stale after a few seconds: Cue then docks the card at a corner).
    content: () => cueContent.get(),
    attention: attentionWiring?.cuePort,
  })

  // Live voice (flags UNDERSTUDY_X_LIVE and UNDERSTUDY_FLAG_VOICE): the websocket lives in main; the dock only owns the microphone and speaker.
  const noCuePort: LiveCuePort = { candidates: () => [], showStep: () => ({ ok: false, chip: null }), askChoice: () => false, onAnswer: () => () => undefined }
  const live = liveFlagOn() && featureOn('voice')
    ? registerLive({
        bus,
        userDataDir,
        endpoints: core.endpoints,
        sendDock: (c, ...a) => (windows.sendDock as unknown as (c: string, ...a: unknown[]) => void)(c, ...a),
        owns: (id) => windows.owns(id),
        overlay: services.overlay,
        cue: cue?.livePort ?? noCuePort,
        killed: isKilled,
        agentActing: () => understudy.hudModel.state().agentActing,
        cueVoiceOn: () => settings.get().cueVoice === true,
        deny: () => ({ strict: awareness?.getAwarenessState().strict ?? true, workerList: awareness?.getAwarenessState().denylist ?? [] }),
        log: ctx.log,
      })
    : null
  liveBox.reg = live
  live?.manager.start()

  app.on('will-quit', () => {
    void showtime.dispose()
    shellTray?.dispose()
    toast.dispose()
    unregisterLoginItem()
    permissions.dispose()
    unregisterHotkeys()
    stopCue()
    cueSignals.stop()
    live?.dispose()
    attentionWiring?.dispose()
    awareness?.dispose()
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
