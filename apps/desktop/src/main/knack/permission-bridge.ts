// The permissions the Knack first run can show and ask for, as the dashboard sees them: four kinds, four closed states, nothing else. The page never gets a path, an app name or a
// sentence from the system: only these enums and one boolean. Pure, so the shell, the tests and the bridge all use the same words. The main-process permission code
// (src/main/permissions.ts) stays the one that asks macOS; this only turns what it says into the closed shape and checks what the page asks for.
import type { KnackPermKind, KnackPermState, KnackPermissionsState } from '../../shared/knack'
import type { PermState, PermissionPane, PermissionStatus } from '../../shared/permissions'
import type { HelperStatus } from '../wake/helper'

export const PERM_KINDS: readonly KnackPermKind[] = ['microphone', 'speech', 'screen', 'accessibility']

/** The page's kind, or null: anything that is not one of the four names is refused before anything else happens. */
export function permKindOf(raw: unknown): KnackPermKind | null {
  return typeof raw === 'string' && (PERM_KINDS as readonly string[]).includes(raw) ? (raw as KnackPermKind) : null
}

/** The settings pane that holds a kind (the same four names; macOS lists Speech Recognition separately). */
export const paneOf = (kind: KnackPermKind): PermissionPane => kind

const stateOf = (raw: PermState | boolean): KnackPermState => {
  if (raw === true || raw === 'granted') return 'granted'
  if (raw === 'denied') return 'denied'
  if (raw === 'restricted') return 'restricted'
  return 'not_asked' // not determined, not known, or an accessibility check that says no (macOS does not say whether it was ever asked)
}

/** Speech recognition has no system call to read it: the listener's own status says. Listening means it was allowed; a blocked helper names the refusal; anything else is not asked yet. */
export function speechStateOf(helper: HelperStatus | null): KnackPermState {
  if (!helper) return 'not_asked'
  if (helper.state === 'listening') return 'granted'
  if (helper.state === 'blocked' && helper.code === 'speech_denied') return 'denied'
  if (helper.state === 'blocked' && helper.code === 'speech_restricted') return 'restricted'
  return 'not_asked'
}

export function permissionsView(p: PermissionStatus, helper: HelperStatus | null): KnackPermissionsState {
  return { microphone: stateOf(p.microphone), speech: speechStateOf(helper), screen: stateOf(p.screen), accessibility: stateOf(p.accessibility), needsRestart: p.needsRestart === true }
}

/**
 * What the button on a microphone card does for macOS's own status: ask (the macOS question appears) when it has not been asked, because Knack is not in System Settings' Microphone list until
 * then; open the list when the answer was no or the Mac forbids it. Pure, so the choice is tested. It only names the action for a worker's click and never asks by itself.
 */
export const micFixAction = (status: string): 'ask' | 'open' => (status === 'not-determined' ? 'ask' : 'open')
