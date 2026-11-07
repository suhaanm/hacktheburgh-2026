// Global shortcuts: the stage-safe activation path (no microphone, no network). Start opens a session with the last
// or default persona; Stop closes it. Registration can fail (another app owns the combo), which is surfaced in state.
import { globalShortcut } from 'electron'
import type { Bus } from './bus'
import type { SettingsStore } from './settings'
import type { StateStore } from './state'
import { DEFAULT_PERSONA } from '../shared/personas'
import type { SessionEndReason } from '../shared/protocol'

// Several combos per action because macOS or another app may own one. Deliberately NOT bound: Cmd+Alt+Esc (Force Quit,
// the presenter's escape hatch if the app hangs) and Ctrl+Alt+Space (switches input source for multilingual users).
export const START_ACCELERATORS = ['CommandOrControl+Alt+Space', 'CommandOrControl+Alt+Shift+Space', 'CommandOrControl+Alt+Shift+S'] as const
export const STOP_ACCELERATORS = ['CommandOrControl+Alt+M', 'CommandOrControl+Alt+Shift+X'] as const
// SHELL2: show or hide the side panel (the menu bar item does the same). Losing every combo is tolerated: the menu bar still works.
export const PANEL_ACCELERATORS = ['CommandOrControl+Alt+P', 'CommandOrControl+Alt+Shift+P'] as const
// Understudy: the global kill switch. Stops everything local at once and tells the engine and the agent. Three combos, because
// this one must never fail to register; if every one is taken the menu-bar item and the HUD pill still work.
export const KILL_ACCELERATORS = ['CommandOrControl+Alt+Shift+K', 'CommandOrControl+Alt+Shift+Backspace', 'CommandOrControl+Alt+Shift+.'] as const

const ACTIVE = new Set(['connecting', 'live', 'thinking', 'speaking'])

export interface HotkeyDeps {
  // Closes the Live session in the dock and emits session:ended. Falls back to the bus event alone when omitted.
  stop?: (reason: SessionEndReason) => void
  // Lets Start ignore presses while a session is already running, and lets a registration failure show up in state.
  state?: StateStore
  // SHELL2: toggles the side panel. When omitted the panel shortcut is not registered.
  togglePanel?: () => void
  // Understudy: the kill switch. When omitted the kill shortcuts are not registered.
  kill?: () => void
}

export interface HotkeyReport {
  start: string[]
  stop: string[]
  panel: string[]
  kill: string[]
  failed: string[]
}

export function registerHotkeys(bus: Bus, settings: SettingsStore, deps: HotkeyDeps = {}): () => void {
  const registered: string[] = []
  const report: HotkeyReport = { start: [], stop: [], panel: [], kill: [], failed: [] }

  const onStart = (): void => {
    if (deps.state && ACTIVE.has(deps.state.get().phase)) return
    bus.emit('session:request', { personaId: settings.get().persona ?? DEFAULT_PERSONA, source: 'hotkey' })
  }
  const onStop = (): void => {
    if (deps.stop) deps.stop('stop')
    else bus.emit('session:ended', { reason: 'stop' })
  }

  const bind = (accelerators: readonly string[], handler: () => void, into: string[]): void => {
    for (const accelerator of accelerators) {
      let ok = false
      try {
        ok = globalShortcut.register(accelerator, handler)
      } catch (err) {
        console.warn(`[hotkey] ${accelerator} rejected:`, err instanceof Error ? err.message : err)
      }
      if (ok) {
        registered.push(accelerator)
        into.push(accelerator)
      } else {
        report.failed.push(accelerator)
      }
    }
  }

  bind(START_ACCELERATORS, onStart, report.start)
  bind(STOP_ACCELERATORS, onStop, report.stop)
  if (deps.togglePanel) {
    const toggle = deps.togglePanel
    bind(PANEL_ACCELERATORS, () => toggle(), report.panel)
  }
  if (deps.kill) {
    const kill = deps.kill
    bind(KILL_ACCELERATORS, () => kill(), report.kill)
  }

  console.log(`[hotkey] start: ${report.start.join(', ') || 'NONE'} | stop: ${report.stop.join(', ') || 'NONE'}${deps.togglePanel ? ` | panel: ${report.panel.join(', ') || 'NONE'}` : ''}${deps.kill ? ` | kill: ${report.kill.join(', ') || 'NONE'}` : ''}${report.failed.length ? ` | unavailable: ${report.failed.join(', ')}` : ''}`)
  if (deps.state) {
    if (!report.start.length) deps.state.patch({ lastError: 'The keyboard shortcut for starting is taken by another app. Use the on-screen button to start.' })
    else if (!report.stop.length) deps.state.patch({ lastError: 'The keyboard shortcut for stopping is taken by another app. Use the on-screen Stop button.' })
    else if (deps.kill && !report.kill.length) deps.state.patch({ lastError: 'The keyboard shortcut for Stop everything is taken by another app. Use the Stop all pill or the menu bar item.' })
  }

  return () => {
    for (const accelerator of registered) globalShortcut.unregister(accelerator)
    registered.length = 0
  }
}
