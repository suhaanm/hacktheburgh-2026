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
import { START_ACCELERATORS, STOP_ACCELERATORS, PANEL_ACCELERATORS } from './hotkey'
import { trayStateKind, trayTitle } from './panel-rules'
import type { Windows } from './windows'

export type TrayIconKind = 'idle' | 'live' | 'muted'
export type TrayAction = 'talk' | 'type' | 'mute' | 'stop' | 'panel' | 'demo' | 'setup' | 'permissions' | 'quit'

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
  agents?: readonly { status: string }[]
  startAccelerator?: string
  stopAccelerator?: string
  panelAccelerator?: string
}

const ACTIVE: ReadonlySet<CompanionState['phase']> = new Set(['connecting', 'live', 'thinking', 'speaking'])
export const isSessionActive = (phase: CompanionState['phase']): boolean => ACTIVE.has(phase)

/** One plain line for the top of the menu and the tooltip. */
export function describeStatus(model: Pick<TrayModel, 'phase' | 'micMuted' | 'persona'> & { agents?: readonly { status: string }[] }): string {
  const name = PERSONAS[model.persona ?? DEFAULT_PERSONA].displayName
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

export function iconKind(model: Pick<TrayModel, 'phase' | 'micMuted'> & { agents?: readonly { status: string }[] }): TrayIconKind {
  if (model.micMuted) return 'muted'
  if (trayStateKind({ phase: model.phase, micMuted: false, agents: model.agents }) === 'working') return 'live' // busy for the user: same lit icon as a session
  return isSessionActive(model.phase) ? 'live' : 'idle'
}

/** Menu content as plain data (tests read this; Electron gets it through `toElectronMenu`). */
export function buildMenuEntries(model: TrayModel): MenuEntry[] {
  const active = isSessionActive(model.phase)
  const hotkeyPersona = model.persona ?? DEFAULT_PERSONA
  const sep = (id: string): MenuEntry => ({ id, label: '', enabled: false, separator: true })
  return [
    { id: 'status', label: describeStatus(model), enabled: false },
    sep('sep1'),
    { id: 'panel', label: 'Show panel', enabled: true, checked: model.dockVisible, ...(model.panelAccelerator ? { accelerator: model.panelAccelerator } : {}) },
    ...PERSONA_LIST.map((p): MenuEntry => ({ id: `talk:${p.id}`, label: `Talk to ${p.displayName}`, enabled: true, ...(p.id === hotkeyPersona && model.startAccelerator ? { accelerator: model.startAccelerator } : {}) })),
    { id: 'type', label: 'Type instead', enabled: true },
    { id: 'mute', label: model.micMuted ? 'Unmute microphone' : 'Mute microphone', enabled: true },
    { id: 'stop', label: 'Stop', enabled: active, ...(model.stopAccelerator ? { accelerator: model.stopAccelerator } : {}) },
    sep('sep2'),
    { id: 'demo', label: model.showtimeRunning ? 'Stop the demo walkthrough' : 'Run the demo walkthrough', enabled: true },
    sep('sep3'),
    { id: 'setup', label: 'Set up again…', enabled: true },
    { id: 'permissions', label: 'Permissions…', enabled: true },
    sep('sep4'),
    { id: 'quit', label: 'Quit Alongside', enabled: true },
  ]
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
  const base = { idle: 'trayTemplate', live: 'trayLiveTemplate', muted: 'trayMutedTemplate' }[kind]
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

  let tray: Tray | null = null
  let shownKey = ''
  let shownTitle = ''
  // The panel was brought up by "Type instead" while hidden: it goes away again when that session ends.
  let tempShown = false
  const icons = new Map<TrayIconKind, NativeImage>()

  const model = (): TrayModel => {
    const st = deps.state.get()
    const firstRegistered = (list: readonly string[]) => list.find((a) => isRegistered(a))
    return {
      phase: st.phase,
      micMuted: st.micMuted,
      persona: st.persona,
      dockVisible: deps.windows.isDockVisible(),
      showtimeRunning: deps.showtimeRunning?.() ?? false,
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
    const entry = buildMenuEntries(model()).find((e) => e.id === id)
    if (!entry || entry.separator || !entry.enabled) return false
    if (id.startsWith('talk:')) {
      const personaId = id.slice('talk:'.length) as PersonaId
      deps.bus.emit('session:request', { personaId, source: 'button' })
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
      case 'quit':
        quit()
        return true
      default:
        return false
    }
  }

  const toElectronMenu = (): Menu => {
    const template: MenuItemConstructorOptions[] = buildMenuEntries(model()).map((e) =>
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
    const kind = iconKind(m)
    const tooltip = `Alongside: ${describeStatus(m)}`
    const image = iconFor(kind)
    // macOS shows this word next to the icon. Icon file missing: still show something.
    const title = trayTitle(m) || (image.isEmpty() ? 'Alongside' : '')
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
      return {
        exists: tray !== null,
        bounds: tray ? tray.getBounds() : null,
        tooltip: `Alongside: ${describeStatus(m)}`,
        title: shownTitle,
        icon: iconKind(m),
        panelVisible: m.dockVisible,
        menu: buildMenuEntries(m)
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
