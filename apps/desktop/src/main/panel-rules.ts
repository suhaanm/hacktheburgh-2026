// SHELL2: pure rules for the side panel and the menu-bar state line. No Electron imports, so tests read them directly.
import type { CompanionState } from '../shared/protocol'
import type { Settings } from '../shared/settings'

/** The panel starts hidden unless the user keeps it open, setup is not finished, or there is no menu bar item to bring it back. */
export function shouldShowDockAtStart(s: Pick<Settings, 'showDock' | 'onboardingDone' | 'showMenuBarIcon'>, headless = false): boolean {
  if (headless) return false
  return s.showDock || !s.onboardingDone || !s.showMenuBarIcon
}

export type TrayStateKind = 'asleep' | 'listening' | 'connecting' | 'live' | 'thinking' | 'speaking' | 'muted' | 'working' | 'error'

export interface TrayStateInput {
  phase: CompanionState['phase']
  micMuted: boolean
  agents?: readonly { status: string }[]
}

/** The one state the menu bar shows: mute wins, then error, then a running agent, then the session phase. */
export function trayStateKind(m: TrayStateInput): TrayStateKind {
  if (m.phase === 'error') return 'error'
  if (m.micMuted && m.phase !== 'asleep') return 'muted'
  if ((m.agents ?? []).some((a) => a.status === 'running')) return 'working'
  switch (m.phase) {
    case 'asleep':
      return 'asleep'
    case 'listening_for_name':
      return 'listening'
    case 'connecting':
      return 'connecting'
    case 'live':
      return 'live'
    case 'thinking':
      return 'thinking'
    case 'speaking':
      return 'speaking'
    default:
      return 'asleep'
  }
}

// Short sentence-case word next to the icon on macOS. Asleep shows the icon alone to keep the menu bar quiet.
const TITLES: Record<TrayStateKind, string> = {
  asleep: '',
  listening: 'Listening',
  connecting: 'Connecting',
  live: 'Live',
  thinking: 'Thinking',
  speaking: 'Speaking',
  muted: 'Muted',
  working: 'Working…',
  error: 'Problem',
}

export const trayTitle = (m: TrayStateInput): string => TITLES[trayStateKind(m)]
