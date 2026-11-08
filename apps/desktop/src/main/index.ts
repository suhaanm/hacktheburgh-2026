import { applyDesktopDefaultFlags } from './default-flags'
import path from 'node:path'
import dotenv from 'dotenv'
import { app, BrowserWindow, nativeImage, powerMonitor, screen, shell, systemPreferences, webContents } from 'electron'
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
import { registerWake } from './wake/electron'
import { createContextHub, screenIdFromUrl } from './wake/context-source'
import { readRung } from './wake/rung'
import { dataDirPath } from './kill-file'
import { LIVE_CONSENT_VERSION } from './live/settings'
import type { WakeController } from './wake/controller'
import type { LiveRegistration } from './live'
import type { CueSpeaker, CueVoice, LiveCuePort } from './cue/voice'
import { redactingLog } from './model-port/redact'
import { createModelPortFromEnv, runBootCheck } from './model-port'
import { experimentOn, featureOn, forcedSettings } from './feature-flags'
import { isSessionActive } from './tray'
import { HELP_LEVEL_LABELS } from '../shared/protocol'
import { appIconPath } from './app-icon'
import { createUnderstudyCore, registerUnderstudy } from './understudy'
import { lastHotkeyReport, registerHotkeys } from './hotkey'
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
import { APP_NAME } from '../shared/brand'
import { createAskBar } from './knack/ask-bar'
import { createTryRingPort } from './knack/try-ring'
import { askUnavailableLine } from './knack/ask-ipc'
import { registerAppScheme } from './knack/app-protocol-electron'
import { glyphSvg } from './knack/brand-glyph'
import { knackHidden, knackShellEnabled, prepareKnackEnv } from './knack/env'
import { createKnackShell, type KnackShell } from './knack/knack-shell'

// The key lives only in REPO/.env; it is never logged or sent to a renderer.
if (process.env.ALONGSIDE_USERDATA) app.setPath('userData', path.resolve(process.env.ALONGSIDE_USERDATA))
// Understudy: the repo-level .env holds OPENAI_API_KEY and OPENAI_MODEL_*; the app-level one (Gemini voice key) is still honoured.
// dotenv never overrides a variable that is already set, and nothing is printed (quiet).
dotenv.config({ path: path.join(app.getAppPath(), '.env'), quiet: true })
dotenv.config({ path: path.join(app.getAppPath(), '../../.env'), quiet: true })
// KNACK: the repository's own .env (the Gemini key) is loaded into this process BEFORE the defaults below apply, so an explicit 0 in it still wins (a Dock-launched app
// has no .env next to it). Nothing is printed and a variable that is already set is never overridden.
app.setName(APP_NAME)
const knackWanted = knackShellEnabled(process.env, process.env.ALONGSIDE_HEADLESS === '1')
const knackConfig = knackWanted ? prepareKnackEnv({ env: process.env, appPath: app.getAppPath(), resourcesPath: app.isPackaged ? process.resourcesPath : undefined, isPackaged: app.isPackaged }) : null
applyDesktopDefaultFlags() // D48: voice and the REQ-5 layers are on unless a variable says '0'

const flag = (name: string) => process.env[name] === '1'

// KNACK: one app, a dashboard window plus a menu-bar item plus a corner pill, which starts the engine and the agent itself (src/main/knack). On by default; off
// for headless runs and with KNACK_SHELL=0. The scheme must be declared before ready; a second launch hands over to the first instead of starting another.
// KNACK_HIDDEN=1 (the hidden end-to-end run, scripts/knack-e2e.mjs): the app runs for real but nothing is shown (no Dock icon, no menu bar item, no window), no global shortcut is
// taken, and no permission is asked. Never set in normal use.
const hiddenRun = knackWanted && knackHidden(process.env)
if (hiddenRun && process.platform === 'darwin') app.setActivationPolicy('prohibited')
let secondInstance = false
if (knackWanted) {
  registerAppScheme()
  if (!flag('KNACK_NO_SINGLE_INSTANCE') && !app.requestSingleInstanceLock()) {
    secondInstance = true
    app.quit()
  }
}
let shellTray: ShellTray | null = null // SHELL: the menu-bar item keeps the app alive when the dock window is hidden

void app.whenReady().then(async () => {
  if (secondInstance) return
  const headless = flag('ALONGSIDE_HEADLESS')
  const userDataDir = app.getPath('userData')
  // The brand mark as the dock icon (macOS), instead of the Electron default.
  if (process.platform === 'darwin') {
    const icon = appIconPath(app.getAppPath(), process.resourcesPath)
    if (icon) app.dock?.setIcon(nativeImage.createFromPath(icon))
  }

  const bus = new Bus()
  // Voice-adjacent settings pinned off by feature flags. In the Knack app the old side panel's own eight-step set-up never runs: Knack has one onboarding, the first run in its own
  // window, so the old flow's flag is pinned done (a pinned key wins over the saved file and over every patch, so nothing can bring that flow back).
  const settings = new SettingsStore(userDataDir, { forced: { ...forcedSettings(), ...(knackWanted ? { onboardingDone: true } : {}) } })
  // KNACK: the window comes up first, with a calm "Starting Knack…", while the models are chosen (live when a key is present and the boot check passes, example
  // data otherwise) and the services start. Everything built below (the model port included) then sees the environment that choice made.
  const lateBox: { windows: ReturnType<typeof createWindows> | null; kill: (() => void) | null } = { windows: null, kill: null }
  let knack: KnackShell | null = null
  if (knackWanted && knackConfig) {
    knack = createKnackShell({
      settings,
      userDataDir,
      config: knackConfig,
      hidden: knackHidden(process.env),
      openedAtLogin: process.platform === 'darwin' && app.getLoginItemSettings().wasOpenedAtLogin === true,
      env: process.env,
      glyphSvg,
      // The key is only checked for being there; the boot check lists the models it can use. A port built for live (never the mock) answers it.
      bootCheck: async () => (await createModelPortFromEnv({ env: { ...process.env, UNDERSTUDY_MOCK: '0', ALONGSIDE_MOCK: '0' } }).bootCheck()).ok,
      killAccelerator: () => lastHotkeyReport()?.kill[0] ?? null,
      stopEverything: () => lateBox.kill?.(),
      log: (...args) => console.log('[knack]', ...args),
      onChange: () => shellTray?.refresh(),
    })
    await knack.planned
  }
  const state = new StateStore(settings.get())
  // SHELL2: the panel stays hidden unless showDock is on, setup is unfinished, or there is no menu bar item to reopen it. The window still exists and runs (mic, wake spotter, Live session).
  // KNACK: the side panel is not drawn (the main window is the front door); its hidden window stays as the host of the microphone and the Live audio.
  const windows = createWindows({ noOverlay: flag('ALONGSIDE_NO_OVERLAY'), headless: headless || hiddenRun, showDockAtStart: knackWanted ? false : shouldShowDockAtStart(settings.get(), headless) })
  lateBox.windows = windows

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
  // Hey Knack (the on-device listener) is created after Live and the attention layer; the tray and Live's `do_it_for_me` read it through this box.
  const wakeBox: { ctl: WakeController | null; settings: { get(): { voiceAnswer: string; screenAnswer: string } } | null } = { ctl: null, settings: null }
  // The last coach decision's step id and capture zone (ids only), for the voice conversation's context packet.
  const coachBox: { last: { step: string | null; zone: string | null; t: number } | null } = { last: null }

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
    hudHidden: hiddenRun,
    noOverlay: flag('ALONGSIDE_NO_OVERLAY'),
    onCoachDecision: (d) => {
      awarenessBox.a?.observeStuck(pStuckForTrigger(d))
      coachBox.last = { step: d.step, zone: d.target?.zone ?? null, t: Date.now() }
    },
    onPageContent: (rects) => cueContent.set(rects),
    onAgentSample: (sample) => knack?.feedAgentSample(sample),
    onLocalActing: (acting) => knack?.feedLocalActing(acting),
    corner: knackWanted,
  })
  lateBox.kill = () => void understudy.kill.trigger('hud')

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

  // KNACK: the Ask bar (an Option-Space tap, the menu bar's Ask row). A typed line goes into a voice conversation that is already open; typed chat has no model behind it
  // in this build, so otherwise the bar says one plain sentence and stays. The old chat panel is not drawn in the app: a talk press no longer raises it either.
  const askBar = knack
    ? createAskBar({
        hidden: hiddenRun,
        disabled: headless || flag('ALONGSIDE_NO_OVERLAY'),
        log: ctx.log,
        onClosed: () => void knack?.dispatch({ type: 'ask_closed' }),
        submit: (text) => (liveBox.reg?.manager.injectTyped(text) ? { ok: true } : { ok: false, line: askUnavailableLine(settings.get().talkHotkey) }),
      })
    : null
  const toggleAsk = (): void => {
    if (askBar?.isOpen()) askBar.close()
    else void knack?.dispatch({ type: 'ask_tap' })
  }
  const unregisterHotkeys = hiddenRun ? () => undefined : registerHotkeys(bus, settings, { look: awareness ? () => void awareness.hotkey() : undefined, state, stop: (r) => session.stop(r), togglePanel: () => shellTray?.togglePanel(), kill: () => void understudy.kill.trigger('hotkey'), raisePanel: knack ? undefined : () => windows.showDock(), askTap: knack ? toggleAsk : undefined })
  // NOTIFY: permission prompts also appear as a toast at the top of the screen (settings.confirmStyle; no window when headless / no overlay).
  // KNACK: in the app the prompt is a corner card (bottom-right, above the corner pill column while that shows), not a top-right toast.
  const toast = registerToast({ ctx, adoptOwner, disabled: headless || flag('ALONGSIDE_NO_OVERLAY'), corner: knack ? { column: () => { const w = understudy.hud.window(); return w && w.isVisible() ? w.getBounds() : null } } : undefined })
  const unregisterLoginItem = registerLoginItem(settings, { log: (...args) => ctx.log('login-item', ...args) })
  if (!headless && !hiddenRun) shellTray = registerTray({ bus, state, settings, windows, stop: (r) => session.stop(r), showtimeRunning: () => showtime.active(), kill: { trigger: () => void understudy.kill.trigger('tray'), clear: () => void understudy.kill.clear(), isKilled: () => understudy.kill.isKilled() }, awareness: awareness ? trayAwareness(awareness) : undefined, openQueue: understudy.openQueue, captureMode: () => core.capture.mode(), openApp: knack ? () => knack?.openMain() : undefined, models: knack ? () => knack?.modelStatus() ?? { live: null, text: '' } : undefined, knack: knack ? () => knack?.trayStatus() ?? { working: null, needsYou: 0, stopped: false } : undefined, openSettings: knack ? () => knack?.openSettings() : undefined, openSetup: knack ? () => knack?.openSetup() : undefined, ask: knack ? toggleAsk : undefined, openNeedsYou: knack ? () => void knack?.dispatch({ type: 'review_clicked' }) : undefined, coachLine: () => { const c = understudy.chip.current(); return c ? `Help level ${c.level}: ${HELP_LEVEL_LABELS[c.level]}` : null }, openDashboard: understudy.openDashboard, wake: { view: () => (wakeBox.ctl ? { on: wakeBox.ctl.status().switchOn, line: wakeBox.ctl.status().line } : null), setListen: (on) => wakeBox.ctl?.setListen(on) }, voiceMenu: () => featureOn('voice'), cueMenu: () => experimentOn('cue'), queueCount: () => understudy.hudModel.state().queuePending, agentActing: () => understudy.hudModel.state().agentActing, log: (...args) => ctx.log('tray', ...args) })
  // The attention layer (the one-voice router). One call; null with its flag off.
  const screenShare = createScreenShareProbe()
  // KNACK: the corner pill and the minimise and restore rules. The pill is never over a secure input or a denylisted app (the same probes Cue reads) and not
  // while a screen is shared; a probe that cannot be read counts as "stay away".
  let shareAt = 0
  let sharing = false
  knack?.attach({
    kill: { trigger: (source) => understudy.kill.trigger(source), clear: () => understudy.kill.clear(), isKilled: () => understudy.kill.isKilled(), subscribe: (cb) => understudy.kill.subscribe(() => cb()) },
    // Cue's own signal reader polls every 2 s when it runs; otherwise one look is taken here. The screen-share look (a process list) is taken every 10 s.
    probe: async () => {
      if (hiddenRun) return { suppressed: null, presenting: false } // the hidden run reads nothing from the desk
      if (!cueOn) await cueSignals.refresh()
      if (Date.now() - shareAt > 10_000) {
        shareAt = Date.now()
        sharing = (await screenShare.read()) === true
      }
      return { suppressed: cueSignals.suppressed(), presenting: sharing }
    },
    hud: understudy.hudModel,
    pendingQueue: () => core.engine.pendingQueue(),
    onVoiceEnd: () => liveBox.reg?.manager.stopAll('stop'),
    askBar: askBar ?? undefined,
    // The first run's bridge: what it shows and asks of macOS, and the sample ring (the overlay covers the primary display).
    permissions,
    speech: { helper: () => wakeBox.ctl?.status().helper ?? null, request: () => wakeBox.ctl?.arm() },
    ring: createTryRingPort(services.overlay, () => screen.getPrimaryDisplay().bounds),
  })
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
    // KNACK: the corner pill column is a window of ours the no-target card must not cover: it stacks above it.
    avoid: knack ? () => { const w = understudy.hud.window(); if (!w || !w.isVisible()) return []; const b = w.getBounds(); return [{ x: b.x, y: b.y, w: b.width, h: b.height }] } : undefined,
    attention: attentionWiring?.cuePort,
  })

  // The context packet every voice conversation starts with (Hey Knack and the talk key): enums, ids and counts built by code, never anything from the screen.
  const contextHub = createContextHub({
    mock: flag('UNDERSTUDY_MOCK') || flag('ALONGSIDE_MOCK'),
    approvals: () => understudy.hudModel.state().queuePending,
    task: () => understudy.coachPoller.lastState()?.task ?? null,
    coach: () => coachBox.last,
    cue: () => cue?.controller.visible()?.kind ?? 'none',
    consent: () => {
      const l = liveBox.reg?.settings.get()
      const w = wakeBox.settings?.get()
      const voiceOk = l?.liveEnabled === true && l.liveConsentVersion === LIVE_CONSENT_VERSION
      return { voice: voiceOk ? 'yes' : (w?.voiceAnswer ?? 'unset'), screen: l?.liveFrames === true ? 'yes' : (w?.screenAnswer ?? 'unset'), frames: l?.liveFrames === true }
    },
    rung: () => readRung(dataDirPath()),
    // The Knack window's route, only while the worker is looking at it (otherwise the screen id would mislead the model).
    screen: () => {
      const id = knack?.mainWindow.window()?.webContentsId()
      const wc = id !== undefined && knack?.mainWindow.isFocused() ? webContents.fromId(id) : null
      return wc && !wc.isDestroyed() ? screenIdFromUrl(wc.getURL()) : null
    },
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
        doIt: (req) => (wakeBox.ctl ? wakeBox.ctl.doIt(req) : Promise.resolve({ ok: false, reason: 'not_available' })),
        context: (o) => contextHub.build(o),
        killed: isKilled,
        agentActing: () => understudy.hudModel.state().agentActing,
        cueVoiceOn: () => settings.get().cueVoice === true,
        deny: () => ({ strict: awareness?.getAwarenessState().strict ?? true, workerList: awareness?.getAwarenessState().denylist ?? [] }),
        log: ctx.log,
      })
    : null
  liveBox.reg = live
  live?.manager.start()
  // The corner pill says what a voice conversation is doing (Listening, Thinking, Speaking) for both the talk key and Hey Knack, and leaves with it.
  let pillVoice: 'Listening' | 'Thinking' | 'Speaking' | null = null
  const offVoicePill = live && knack
    ? live.manager.subscribe((s) => {
        const next = s.phase === 'connecting' || s.phase === 'listening' ? 'Listening' : s.phase === 'thinking' || s.phase === 'waiting' ? 'Thinking' : s.phase === 'speaking' ? 'Speaking' : null
        if (next === pillVoice) return
        const was = pillVoice
        pillVoice = next
        if (next) void knack?.dispatch({ type: 'voice_hold', phase: next })
        else if (was) void knack?.dispatch({ type: 'voice_end' })
      })
    : null

  // Hey Knack (flag UNDERSTUDY_X_WAKE, on by default, D52): an on-device listener that opens the SAME Live conversation as the talk key. It is dormant
  // while the screen is locked, during a call or meeting, while a conversation or an agent is active, and when the worker switches it off. The app
  // runs normally without the helper binary or without the macOS permissions (one plain line in the menu).
  const wake = live && !headless && experimentOn('wake')
    ? registerWake({
        userDataDir,
        live,
        endpoints: core.endpoints,
        attentionSignals: attentionWiring ? () => attentionWiring.signals() : null,
        lock: attentionWiring?.attention.lock ?? null,
        mainSettings: settings,
        agentActing: () => understudy.hudModel.state().agentActing,
        killed: isKilled,
        owns: (id) => windows.owns(id) || knack?.mainWindow.owns(id) === true,
        openSettings: () => knack?.openSettings(),
        openMicrophoneSettings: () => permissions.openSettings('microphone'),
        context: contextHub,
        log: ctx.log,
      })
    : null
  wakeBox.ctl = wake?.controller ?? null
  wakeBox.settings = wake?.settings ?? null
  wake?.controller.subscribe(() => shellTray?.refresh())
  const offWakeKill = wake ? understudy.kill.subscribe((k) => wake.controller.setKilled(k.killed)) : null

  app.on('will-quit', () => {
    askBar?.dispose()
    void showtime.dispose()
    shellTray?.dispose()
    toast.dispose()
    unregisterLoginItem()
    permissions.dispose()
    unregisterHotkeys()
    stopCue()
    cueSignals.stop()
    offWakeKill?.()
    offVoicePill?.()
    wake?.dispose()
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
    startDebugServer({ ctx, services, dispatch, session, capture: { overlayPng: windows.overlayPng, overlayText: windows.overlayText, dockPng: windows.dockPng, hudPng: understudy.hud.png, hudPreview: understudy.hud.preview, hudVisible: () => understudy.hud.window()?.isVisible() ?? null }, knack: knack ? { dispatch: (e) => knack?.dispatch(e as never), info: () => knack?.info() } : undefined, understudy: { kill: understudy.kill, hud: understudy.hudModel, dom: { status: () => ({ port: understudy.extServer()?.port() ?? null, pending: understudy.domGrounder.pending(), extensionSeenMs: understudy.extServer()?.lastSeenAt() ? Date.now() - (understudy.extServer()?.lastSeenAt() ?? 0) : null, ring: understudy.ring.current(), chip: understudy.chip.current(), capture: core.capture.mode(), coach: understudy.coachBrain.status() }) } }, tray: shellTray ?? undefined })
  }

  // Understudy: the microphone is only needed for voice or the wake word, both off unless their flags are set.
  if (!headless && !hiddenRun && !flag('ALONGSIDE_MOCK') && !flag('UNDERSTUDY_MOCK') && (featureOn('voice') || featureOn('wake')) && process.platform === 'darwin' && systemPreferences.getMediaAccessStatus('microphone') === 'not-determined') {
    void systemPreferences.askForMediaAccess('microphone')
  }
})

// With a menu-bar item the app keeps running when the dock is hidden; without one there is no way back in, so quit.
app.on('window-all-closed', () => {
  if (!shellTray?.hasTray()) app.quit()
})
