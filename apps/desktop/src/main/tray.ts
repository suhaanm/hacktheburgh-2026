// Menu-bar presence: a template icon that stays while `showMenuBarIcon` is on. Click toggles the dock; right-click opens
// the menu. The app keeps running with the dock hidden; Quit here is the way out.
import fs from 'node:fs'
import path from 'node:path'
import { app, globalShortcut, Menu, nativeImage, Tray } from 'electron'
import type { MenuItemConstructorOptions, NativeImage, Rectangle } from 'electron'
import { IPC } from '../shared/ipc'
import { PERSONA_LIST, PERSONAS, DEFAULT_PERSONA } from '../shared/personas'
import type { CompanionState, PersonaId, SessionEndReason } from '../shared/protocol'
import type { ShellCommand } from '../shared/shell'
import type { Settings } from '../shared/settings'
import type { Bus } from './bus'
import { captureLabel, type CaptureMode } from './engine/capture-consent'
import { START_ACCELERATORS, STOP_ACCELERATORS, PANEL_ACCELERATORS, KILL_ACCELERATORS, TALK_FALLBACKS } from './hotkey'
import { trayStateKind, trayTitle } from './panel-rules'
import type { Windows } from './windows'

// The menu-bar icon is the brand mark; its state is a tiny badge, no colour (template images are black and alpha):
//   idle    the mark alone        acting  a 3 px dot: an agent is acting for the person     glance  a 3 px ring: a glance is in flight
//   paused  the disc and two bars: the person paused Understudy from this menu
export type TrayIconKind = 'idle' | 'acting' | 'glance' | 'paused'
export type TrayAction = 'cue_quiet' | 'cue_resume' | 'talk' | 'type' | 'mute' | 'stop' | 'kill' | 'resume' | 'queue' | 'panel' | 'demo' | 'setup' | 'permissions' | 'quit' | 'pause' | 'unpause' | 'awareness' | 'glance_trigger' | 'glance_periodic' | 'dashboard'

export interface MenuEntry {
  id: string // 'status', 'talk:<personaId>', or a TrayAction
  label: string
  enabled: boolean
  accelerator?: string
  separator?: boolean
  checked?: boolean // present on checkbox entries ("Show panel")
}

export interface TrayModel {
  phase: CompanionState['phase']
  micMuted: boolean
  persona: PersonaId | null
  dockVisible: boolean
  showtimeRunning: boolean
  // Understudy: the global kill switch is on (the menu offers Resume instead of Stop everything).
  killed?: boolean
  killAccelerator?: string
  // Understudy: whether desk capture (times only) is on. Shown as a plain line under the status; omitted when unknown.
  capture?: CaptureMode
  // Understudy: how much help the coach is giving now ("Coach: Watch me (help level 1)"). The coach is not drawn on the screen; this
  // line and the dashboard's Today screen are where its state lives. Omitted when unknown.
  coach?: string
  // Paused from the menu until this time (ms since the epoch), else absent. The menu offers "Resume now".
  pausedUntil?: number | null
  // The AWARENESS track's switches (settings awarenessEnabled, glanceOnTrigger, glancePeriodic), shown as checkboxes.
  awareness?: { enabled: boolean; onTrigger: boolean; periodic: boolean }
  // Cue (the proactive cards; only offered when the cue experiment is on): quiet until this time, else null.
  cue?: { quietUntil: number | null }
  // Approvals waiting in the morning queue (null when unknown): the menu says how many, since the screen does not.
  queuePending?: number | null
  // A glance is being taken or sent right now (the icon shows a ring).
  glanceInFlight?: boolean
  // Any agent is acting for the person (also a run of the agent service): the icon shows the acting dot.
  agentActing?: boolean
  // The hold-to-talk key, as an Electron accelerator, shown next to "Talk to Understudy".
  talkAccelerator?: string
  // The old Live-voice items (Type instead, Mute microphone, Stop, the demo walkthrough, Set up again). Off: the menu is the calm one.
  voiceMenu?: boolean
  agents?: readonly { status: string }[]
  startAccelerator?: string
  stopAccelerator?: string
  panelAccelerator?: string
}

const ACTIVE: ReadonlySet<CompanionState['phase']> = new Set(['connecting', 'live', 'thinking', 'speaking'])
export const isSessionActive = (phase: CompanionState['phase']): boolean => ACTIVE.has(phase)

/** One plain line for the top of the menu and the tooltip. */
export function describeStatus(model: Pick<TrayModel, 'phase' | 'micMuted' | 'persona'> & { agents?: readonly { status: string }[]; pausedLabel?: string }): string {
  const name = PERSONAS[model.persona ?? DEFAULT_PERSONA].displayName
  if (model.pausedLabel) return model.pausedLabel
  if (model.micMuted && model.phase !== 'asleep' && model.phase !== 'error') return 'Microphone muted'
  if (trayStateKind({ phase: model.phase, micMuted: false, agents: model.agents }) === 'working') return `${name} is working for you`
  switch (model.phase) {
    case 'asleep':
      return 'Asleep'
    case 'listening_for_name':
      return 'Waiting to hear its name'
    case 'connecting':
      return `Connecting to ${name}…`
    case 'live':
      return `Live with ${name}`
    case 'thinking':
      return `${name} is thinking`
    case 'speaking':
      return `${name} is speaking`
    case 'error':
      return 'Something went wrong'
  }
}

export function iconKind(model: Pick<TrayModel, 'phase' | 'micMuted'> & { agents?: readonly { status: string }[]; paused?: boolean; glanceInFlight?: boolean; agentActing?: boolean }): TrayIconKind {
  if (model.paused) return 'paused'
  if (model.glanceInFlight) return 'glance'
  if (model.agentActing) return 'acting' // any agent acting for the person, including a run of the agent service
  if (trayStateKind({ phase: model.phase, micMuted: false, agents: model.agents }) === 'working') return 'acting' // busy for the person
  return isSessionActive(model.phase) ? 'acting' : 'idle'
}

const clock = (ms: number): string => {
  const d = new Date(ms)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
const cueQuiet = (until: number | null | undefined, now: number): boolean => until !== null && until !== undefined && until > now

/** "Paused until 18:40" for the status line, or undefined when not paused. */
export function pausedLabel(until: number | null | undefined, now: number): string | undefined {
  if (!until || until <= now) return undefined
  return `Paused until ${clock(until)}`
}

/** Menu content as plain data (tests read this; Electron gets it through `toElectronMenu`). */
export function buildMenuEntries(model: TrayModel, now: number = Date.now()): MenuEntry[] {
  const active = isSessionActive(model.phase)
  const hotkeyPersona = model.persona ?? DEFAULT_PERSONA
  const sep = (id: string): MenuEntry => ({ id, label: '', enabled: false, separator: true })
  const paused = pausedLabel(model.pausedUntil, now)
  const aw = model.awareness
  const voice = model.voiceMenu === true
  const entries: (MenuEntry | null)[] = [
    { id: 'status', label: describeStatus({ ...model, pausedLabel: paused }), enabled: false },
    ...(model.capture ? [{ id: 'capture', label: captureLabel(model.capture), enabled: false } as MenuEntry] : []),
    ...(model.coach ? [{ id: 'coach', label: model.coach, enabled: false } as MenuEntry] : []),
    sep('sep1'),
    { id: 'panel', label: 'Show panel', enabled: true, checked: model.dockVisible, ...(model.panelAccelerator ? { accelerator: model.panelAccelerator } : {}) },
    ...PERSONA_LIST.map((p): MenuEntry => ({
      id: `talk:${p.id}`,
      label: `Talk to ${p.displayName}`,
      enabled: true,
      ...(model.talkAccelerator ? { accelerator: model.talkAccelerator } : p.id === hotkeyPersona && model.startAccelerator ? { accelerator: model.startAccelerator } : {}),
    })),
    paused ? { id: 'unpause', label: 'Resume now', enabled: true } : { id: 'pause', label: 'Pause for 1 hour', enabled: true },
    ...(model.cue
      ? cueQuiet(model.cue.quietUntil, now)
        ? [
            { id: 'cue_status', label: `Cue is quiet until ${clock(model.cue.quietUntil as number)}`, enabled: false } as MenuEntry,
            { id: 'cue_resume', label: 'Resume Cue', enabled: true } as MenuEntry,
          ]
        : [{ id: 'cue_quiet', label: 'Quiet Cue for an hour', enabled: true } as MenuEntry]
      : []),
    ...(aw
      ? [
          sep('sep1b'),
          { id: 'awareness', label: 'Awareness', enabled: true, checked: aw.enabled } as MenuEntry,
          { id: 'glance_trigger', label: 'Glance when I seem stuck', enabled: aw.enabled, checked: aw.onTrigger } as MenuEntry,
          { id: 'glance_periodic', label: 'Look now and then', enabled: aw.enabled, checked: aw.periodic } as MenuEntry,
        ]
      : []),
    ...(voice
      ? [
          { id: 'type', label: 'Type instead', enabled: true } as MenuEntry,
          { id: 'mute', label: model.micMuted ? 'Unmute microphone' : 'Mute microphone', enabled: true } as MenuEntry,
          { id: 'stop', label: 'Stop', enabled: active, ...(model.stopAccelerator ? { accelerator: model.stopAccelerator } : {}) } as MenuEntry,
        ]
      : []),
    sep('sep2'),
    model.killed
      ? { id: 'resume', label: 'Resume after stopping everything', enabled: true }
      : { id: 'kill', label: 'Stop everything', enabled: true, ...(model.killAccelerator ? { accelerator: model.killAccelerator } : {}) },
    { id: 'dashboard', label: 'Open dashboard', enabled: true },
    { id: 'queue', label: model.queuePending ? `Open morning queue (${model.queuePending})` : 'Open morning queue', enabled: true },
    sep('sep2b'),
    ...(voice
      ? [{ id: 'demo', label: model.showtimeRunning ? 'Stop the demo walkthrough' : 'Run the demo walkthrough', enabled: true } as MenuEntry, sep('sep3'), { id: 'setup', label: 'Set up again…', enabled: true } as MenuEntry]
      : []),
    { id: 'permissions', label: 'Permissions…', enabled: true },
    sep('sep4'),
    { id: 'quit', label: 'Quit Understudy', enabled: true },
  ]
  return entries.filter((e): e is MenuEntry => e !== null)
}

export interface TrayDeps {
  bus: Bus
  state: { get(): CompanionState; patch(partial: Partial<CompanionState>): unknown; subscribe(l: () => void): () => void }
  settings: { get(): Settings; patch(p: Partial<Settings>): unknown; onChange(l: (s: Settings, patch: Partial<Settings>) => void): () => void }
  windows: Pick<Windows, 'showDock' | 'hideDock' | 'isDockVisible' | 'sendDock'>
  stop(reason: SessionEndReason): void
  log?: (...args: unknown[]) => void
  // Whether the demo walkthrough is running (DEMO). Absent means "never".
  showtimeRunning?: () => boolean
  // Understudy: the global kill switch. `trigger` stops everything local and tells the engine and the agent; `clear` is Resume.
  kill?: { trigger(): void; clear(): void; isKilled(): boolean }
  // Understudy: opens the dashboard's morning queue in the browser.
  openQueue?: () => void
  // Understudy: the current desk capture mode (the menu says plainly when it is off).
  captureMode?: () => CaptureMode
  // Understudy: the coach's current help level as one plain line (null when unknown).
  coachLine?: () => string | null
  // Understudy: opens the dashboard in the browser.
  openDashboard?: () => void
  // Understudy: a glance (a screen look) is in flight right now. The AWARENESS track wires this; absent means never.
  glanceInFlight?: () => boolean
  // The old Live-voice menu items are shown only when this says so (default: hidden).
  voiceMenu?: () => boolean
  // Approvals waiting in the morning queue (null when the engine is unreachable).
  queueCount?: () => number | null
  // Any agent is acting right now (the HUD's own answer, which includes the agent service).
  agentActing?: () => boolean
  // Cue's menu entries are offered only when this says so (the UNDERSTUDY_X_CUE experiment; default: hidden).
  cueMenu?: () => boolean
  now?: () => number
  // Test seams.
  isRegistered?: (accelerator: string) => boolean
  iconDir?: string
  quit?: () => void
}

export interface TrayDebugInfo {
  exists: boolean
  bounds: Rectangle | null
  tooltip: string
  title: string // the short state word next to the icon on macOS ('' while asleep)
  icon: TrayIconKind
  panelVisible: boolean
  menu: { id: string; label: string; enabled: boolean; accelerator?: string; checked?: boolean }[]
}

export interface ShellTray {
  hasTray(): boolean
  info(): TrayDebugInfo
  /** Runs a menu entry by id, as a click would. Returns false for an unknown or disabled entry. */
  activate(id: string): boolean
  /** The primary click and Cmd/Ctrl+Alt+P: show the panel if hidden, hide it if shown (persisted as `showDock`). */
  primaryClick(): void
  togglePanel(): void
  dispose(): void
}

function loadIcon(kind: TrayIconKind, dirs: string[]): NativeImage {
  const base = { idle: 'trayTemplate', acting: 'trayActingTemplate', glance: 'trayGlanceTemplate', paused: 'trayPausedTemplate' }[kind]
  for (const dir of dirs) {
    const file = path.join(dir, `${base}.png`)
    if (!fs.existsSync(file)) continue
    const image = nativeImage.createFromPath(file) // picks up the @2x sibling
    if (!image.isEmpty()) {
      image.setTemplateImage(true) // black + alpha, tinted by the system for light and dark menu bars
      return image
    }
  }
  return nativeImage.createEmpty()
}

export function registerTray(deps: TrayDeps): ShellTray {
  const log = deps.log ?? ((...args: unknown[]) => console.log('[tray]', ...args))
  const isRegistered = deps.isRegistered ?? ((a: string) => globalShortcut.isRegistered(a))
  const iconDirs = deps.iconDir ? [deps.iconDir] : [path.join(app.getAppPath(), 'resources', 'tray'), path.join(process.resourcesPath ?? '', 'tray')]
  const quit = deps.quit ?? (() => app.quit())
  const nowMs = deps.now ?? Date.now

  let tray: Tray | null = null
  let shownKey = ''
  let shownTitle = ''
  // The panel was brought up by "Type instead" while hidden: it goes away again when that session ends.
  let tempShown = false
  const icons = new Map<TrayIconKind, NativeImage>()

  const model = (): TrayModel => {
    const st = deps.state.get()
    const st0 = deps.settings.get()
    const firstRegistered = (list: readonly string[]) => list.find((a) => isRegistered(a))
    return {
      phase: st.phase,
      micMuted: st.micMuted,
      persona: st.persona,
      dockVisible: deps.windows.isDockVisible(),
      showtimeRunning: deps.showtimeRunning?.() ?? false,
      killed: deps.kill?.isKilled() ?? false,
      capture: deps.captureMode?.(),
      coach: deps.coachLine?.() ?? undefined,
      pausedUntil: st0.pausedUntil,
      awareness: { enabled: st0.awarenessEnabled, onTrigger: st0.glanceOnTrigger, periodic: st0.glancePeriodic },
      glanceInFlight: deps.glanceInFlight?.() ?? false,
      talkAccelerator: firstRegistered([st0.talkHotkey, ...TALK_FALLBACKS]),
      voiceMenu: deps.voiceMenu?.() ?? false,
      queuePending: deps.queueCount?.() ?? null,
      agentActing: deps.agentActing?.() ?? false,
      cue: deps.cueMenu?.() ? { quietUntil: st0.cueQuietUntil } : undefined,
      killAccelerator: firstRegistered(KILL_ACCELERATORS),
      agents: st.agents,
      startAccelerator: firstRegistered(START_ACCELERATORS),
      stopAccelerator: firstRegistered(STOP_ACCELERATORS),
      panelAccelerator: firstRegistered(PANEL_ACCELERATORS),
    }
  }

  const sendDock = (cmd: ShellCommand): void => deps.windows.sendDock(IPC.shellCommand, cmd)
  const showDockWith = (cmd: ShellCommand): void => {
    deps.windows.showDock()
    sendDock(cmd)
  }

  // Idempotent: makes the window match, without touching settings. Setup in progress keeps the panel up (first run must be visible).
  const applyPanel = (visible: boolean): void => {
    if (visible) {
      if (!deps.windows.isDockVisible()) showDockWith({ type: 'expand' })
    } else if (deps.settings.get().onboardingDone && deps.windows.isDockVisible()) {
      deps.windows.hideDock()
    }
  }
  const setPanel = (visible: boolean): void => {
    tempShown = false
    deps.settings.patch({ showDock: visible })
    applyPanel(visible)
    refresh()
  }
  const togglePanel = (): void => setPanel(!deps.windows.isDockVisible())

  const run = (id: string): boolean => {
    const entry = buildMenuEntries(model(), nowMs()).find((e) => e.id === id)
    if (!entry || entry.separator || !entry.enabled) return false
    if (id.startsWith('talk:')) {
      const personaId = id.slice('talk:'.length) as PersonaId
      if (deps.voiceMenu?.()) deps.bus.emit('session:request', { personaId, source: 'button' }) // the old Live session, only with voice on
      else {
        deps.windows.showDock()
        deps.bus.emit('talk', { source: 'tray', phase: 'press' })
      }
      return true
    }
    switch (id as TrayAction) {
      case 'type':
        if (!deps.windows.isDockVisible() && !deps.settings.get().showDock) tempShown = true // back to hidden when the session ends
        showDockWith({ type: 'view', view: 'chat' })
        refresh()
        return true
      case 'mute':
        deps.state.patch({ micMuted: !deps.state.get().micMuted })
        return true
      case 'stop':
        deps.stop('stop')
        return true
      case 'kill':
        if (!deps.kill) return false
        deps.kill.trigger()
        refresh()
        return true
      case 'resume':
        if (!deps.kill) return false
        deps.kill.clear()
        refresh()
        return true
      case 'queue':
        if (!deps.openQueue) return false
        deps.openQueue()
        return true
      case 'panel':
        togglePanel()
        return true
      case 'demo':
        deps.bus.emit('showtime:request', deps.showtimeRunning?.() ? { source: 'tray', stop: true } : { source: 'tray' })
        return true
      case 'setup':
        deps.settings.patch({ onboardingDone: false })
        showDockWith({ type: 'view', view: 'onboarding' })
        return true
      case 'permissions':
        showDockWith({ type: 'view', view: 'permissions' })
        return true
      case 'pause':
        deps.settings.patch({ pausedUntil: nowMs() + 60 * 60_000 })
        refresh()
        return true
      case 'unpause':
        deps.settings.patch({ pausedUntil: null })
        refresh()
        return true
      case 'cue_quiet':
        deps.settings.patch({ cueQuietUntil: nowMs() + 60 * 60_000 })
        refresh()
        return true
      case 'cue_resume':
        deps.settings.patch({ cueQuietUntil: null })
        refresh()
        return true
      case 'awareness':
        deps.settings.patch({ awarenessEnabled: !deps.settings.get().awarenessEnabled })
        return true
      case 'glance_trigger':
        deps.settings.patch({ glanceOnTrigger: !deps.settings.get().glanceOnTrigger })
        return true
      case 'glance_periodic':
        deps.settings.patch({ glancePeriodic: !deps.settings.get().glancePeriodic })
        return true
      case 'dashboard':
        if (!deps.openDashboard) return false
        deps.openDashboard()
        return true
      case 'quit':
        quit()
        return true
      default:
        return false
    }
  }

  const toElectronMenu = (): Menu => {
    const template: MenuItemConstructorOptions[] = buildMenuEntries(model(), nowMs()).map((e) =>
      e.separator ? { type: 'separator' } : { label: e.label, enabled: e.enabled, ...(e.checked !== undefined ? { type: 'checkbox' as const, checked: e.checked } : {}), ...(e.accelerator ? { accelerator: e.accelerator } : {}), click: () => void run(e.id) },
    )
    return Menu.buildFromTemplate(template)
  }

  const primaryClick = (): void => togglePanel()

  const iconFor = (kind: TrayIconKind): NativeImage => {
    let image = icons.get(kind)
    if (!image) {
      image = loadIcon(kind, iconDirs)
      icons.set(kind, image)
    }
    return image
  }

  function refresh(): void {
    if (!tray) return
    const m = model()
    const pausedText = pausedLabel(m.pausedUntil, nowMs())
    const kind = iconKind({ ...m, paused: pausedText !== undefined })
    const tooltip = `Understudy: ${describeStatus({ ...m, pausedLabel: pausedText })}`
    const image = iconFor(kind)
    // macOS shows this word next to the icon. Icon file missing: still show something.
    const title = trayTitle(m) || (image.isEmpty() ? 'Understudy' : '')
    const key = `${kind}|${tooltip}|${title}`
    if (key === shownKey) return
    shownKey = key
    tray.setImage(image)
    tray.setToolTip(tooltip)
    try {
      if (title !== shownTitle || !title) tray.setTitle(title)
    } catch {
      /* setTitle is macOS and Linux only */
    }
    shownTitle = title
  }

  const create = (): void => {
    if (tray) return
    const image = iconFor('idle')
    tray = new Tray(image)
    tray.setIgnoreDoubleClickEvents(true)
    tray.on('click', () => primaryClick())
    tray.on('right-click', () => tray?.popUpContextMenu(toElectronMenu()))
    shownKey = ''
    shownTitle = ''
    refresh()
    log(`menu bar item created${image.isEmpty() ? ' (icon file missing, using text title)' : ''}`)
  }

  const destroy = (): void => {
    if (!tray) return
    tray.destroy()
    tray = null
    shownKey = ''
    log('menu bar item removed')
  }

  const apply = (settings: Settings): void => (settings.showMenuBarIcon ? create() : destroy())
  apply(deps.settings.get())

  let wasActive = isSessionActive(deps.state.get().phase)
  const offState = deps.state.subscribe(() => {
    const active = isSessionActive(deps.state.get().phase)
    if (wasActive && !active && tempShown) {
      // The session that "Type instead" opened has ended: the panel returns to hidden.
      tempShown = false
      if (!deps.settings.get().showDock) applyPanel(false)
    }
    wasActive = active
    refresh()
  })
  const offSettings = deps.settings.onChange((next, patch) => {
    if ('showMenuBarIcon' in patch) apply(next)
    if ('showDock' in patch) {
      tempShown = false
      applyPanel(next.showDock) // the Settings switch in the panel mirrors the menu bar checkbox
      refresh()
    }
  })

  return {
    hasTray: () => tray !== null,
    info() {
      const m = model()
      const pausedText = pausedLabel(m.pausedUntil, nowMs())
      return {
        exists: tray !== null,
        bounds: tray ? tray.getBounds() : null,
        tooltip: `Understudy: ${describeStatus({ ...m, pausedLabel: pausedText })}`,
        title: shownTitle,
        icon: iconKind({ ...m, paused: pausedText !== undefined }),
        panelVisible: m.dockVisible,
        menu: buildMenuEntries(m, nowMs())
          .filter((e) => !e.separator)
          .map(({ id, label, enabled, accelerator, checked }) => ({ id, label, enabled, ...(accelerator ? { accelerator } : {}), ...(checked !== undefined ? { checked } : {}) })),
      }
    },
    activate: run,
    primaryClick,
    togglePanel,
    dispose() {
      offState()
      offSettings()
      destroy()
    },
  }
}
