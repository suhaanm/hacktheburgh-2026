// Global shortcuts: the stage-safe activation path (no microphone, no network). Start opens a session with the last
// or default persona; Stop closes it. Registration can fail (another app owns the combo), which is surfaced in state.
import { globalShortcut } from 'electron'
import type { Bus } from './bus'
import type { SettingsStore } from './settings'
import type { StateStore } from './state'
import { DEFAULT_PERSONA } from '../shared/personas'
import type { SessionEndReason } from '../shared/protocol'
import { DEFAULT_SETTINGS } from '../shared/settings'

// Several combos per action because macOS or another app may own one. Deliberately NOT bound: Cmd+Alt+Esc (Force Quit,
// the presenter's escape hatch if the app hangs) and Ctrl+Alt+Space (switches input source for multilingual users).
export const START_ACCELERATORS = ['CommandOrControl+Alt+Space', 'CommandOrControl+Alt+Shift+Space', 'CommandOrControl+Alt+Shift+S'] as const
export const STOP_ACCELERATORS = ['CommandOrControl+Alt+M', 'CommandOrControl+Alt+Shift+X'] as const
// SHELL2: show or hide the side panel (the menu bar item does the same). Losing every combo is tolerated: the menu bar still works.
export const PANEL_ACCELERATORS = ['CommandOrControl+Alt+P', 'CommandOrControl+Alt+Shift+P'] as const
// Understudy: the global kill switch. Stops everything local at once and tells the engine and the agent. Three combos, because
// this one must never fail to register; if every one is taken the menu-bar item and the HUD pill still work.
export const KILL_ACCELERATORS = ['CommandOrControl+Alt+Shift+K', 'CommandOrControl+Alt+Shift+Backspace', 'CommandOrControl+Alt+Shift+.'] as const

// The hold-to-talk key: the setting `talkHotkey` (default Option+Space), with these as fallbacks when another app owns it.
export const TALK_FALLBACKS = ['Alt+Space', 'Alt+Shift+Space'] as const
// Electron has no key-up for a global shortcut. While the keys are held, the keyboard auto-repeat keeps calling the handler, so the
// key counts as released when the calls stop for this long (about half a second after letting go). A tap is a press and a release.
export const TALK_RELEASE_MS = 450

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
  // Understudy: bring the side panel up (the talk key does this on press). When omitted the talk key only emits its event.
  raisePanel?: () => void
  // Test seams.
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (h: unknown) => void
}

export interface HotkeyReport {
  start: string[]
  stop: string[]
  panel: string[]
  kill: string[]
  talk: string[]
  failed: string[]
}

export function registerHotkeys(bus: Bus, settings: SettingsStore, deps: HotkeyDeps = {}): () => void {
  const registered: string[] = []
  const report: HotkeyReport = { start: [], stop: [], panel: [], kill: [], talk: [], failed: [] }

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

  // ---- the talk key: press raises the panel and emits `talk`; release is inferred from the auto-repeat stopping.
  const setT = deps.setTimer ?? ((fn, ms) => setTimeout(fn, ms))
  const clearT = deps.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>))
  let held = false
  let releaseTimer: unknown = null
  const onTalk = (): void => {
    if (!held) {
      held = true
      deps.raisePanel?.()
      bus.emit('talk', { source: 'hotkey', phase: 'press' })
    }
    if (releaseTimer !== null) clearT(releaseTimer)
    releaseTimer = setT(() => {
      releaseTimer = null
      held = false
      bus.emit('talk', { source: 'hotkey', phase: 'release' })
    }, TALK_RELEASE_MS)
  }
  let talkBound: string[] = []
  const bindTalk = (): void => {
    for (const a of talkBound) globalShortcut.unregister(a)
    talkBound = []
    report.talk = []
    const wanted = settings.get().talkHotkey || DEFAULT_SETTINGS.talkHotkey
    for (const accelerator of [wanted, ...TALK_FALLBACKS.filter((f) => f !== wanted)]) {
      let ok = false
      try {
        ok = globalShortcut.register(accelerator, onTalk)
      } catch (err) {
        console.warn(`[hotkey] ${accelerator} rejected:`, err instanceof Error ? err.message : err)
      }
      if (ok) {
        talkBound.push(accelerator)
        report.talk.push(accelerator)
        break // one is enough; the fallbacks are only for when the chosen one is taken
      }
      report.failed.push(accelerator)
    }
  }
  bindTalk()
  const offChange =
    typeof settings.onChange === 'function'
      ? settings.onChange((_s, patch) => {
          if ('talkHotkey' in patch) bindTalk()
        })
      : undefined
  const offSettings = (): void => (typeof offChange === 'function' ? offChange() : undefined)

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

  console.log(`[hotkey] talk: ${report.talk.join(', ') || 'NONE'} | start: ${report.start.join(', ') || 'NONE'} | stop: ${report.stop.join(', ') || 'NONE'}${deps.togglePanel ? ` | panel: ${report.panel.join(', ') || 'NONE'}` : ''}${deps.kill ? ` | kill: ${report.kill.join(', ') || 'NONE'}` : ''}${report.failed.length ? ` | unavailable: ${report.failed.join(', ')}` : ''}`)
  if (deps.state) {
    if (!report.start.length) deps.state.patch({ lastError: 'The keyboard shortcut for starting is taken by another app. Use the on-screen button to start.' })
    else if (!report.stop.length) deps.state.patch({ lastError: 'The keyboard shortcut for stopping is taken by another app. Use the on-screen Stop button.' })
    else if (deps.kill && !report.kill.length) deps.state.patch({ lastError: 'The keyboard shortcut for Stop everything is taken by another app. Use the Stop all pill or the menu bar item.' })
  }

  return () => {
    offSettings()
    if (releaseTimer !== null) clearT(releaseTimer)
    for (const accelerator of [...registered, ...talkBound]) globalShortcut.unregister(accelerator)
    registered.length = 0
    talkBound = []
  }
}
