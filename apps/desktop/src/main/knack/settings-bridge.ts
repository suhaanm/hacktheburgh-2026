// The few desktop settings the dashboard's own Settings screen may read and change from inside the Knack window (docs/KNACK_UX.md section 7). The page gets this small view and
// an allow-list for writes, never the whole settings object: nothing about folders, the denylist or consent leaves through it, and a key that is not listed is dropped. The store
// still validates every value (and a feature switched off by its flag stays off). "Use live models" is not here: it has its own two calls because changing it restarts the app.
import type { DashboardSettingsView } from '../../shared/knack'
import type { Settings } from '../../shared/settings'

/** What the page reads (both names of the move-aside switch are answered, and both are accepted on a write). */
export function dashboardSettingsView(s: Settings): DashboardSettingsView {
  return {
    useLiveModels: s.useLiveModels,
    minimiseWhileWorking: s.moveAsideWhileWorking,
    moveAsideWhileWorking: s.moveAsideWhileWorking,
    keepAwakeWhileWorking: s.keepAwakeWhileWorking,
    showInDock: s.showInDock,
    launchAtLogin: s.launchAtLogin,
    cueEnabled: s.cueEnabled,
    helpLevelMode: s.helpLevelMode,
    lockedLevel: s.lockedLevel,
  }
}

const WRITABLE = ['moveAsideWhileWorking', 'keepAwakeWhileWorking', 'showInDock', 'launchAtLogin', 'cueEnabled', 'helpLevelMode', 'lockedLevel'] as const

/** The part of a patch from the page that may reach the settings store: only the listed keys, with the dashboard's name for "move aside" turned into the app's. */
export function dashboardSettingsPatch(raw: unknown): Record<string, unknown> {
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) return {}
  const input = raw as Record<string, unknown>
  const out: Record<string, unknown> = {}
  for (const key of WRITABLE) if (Object.prototype.hasOwnProperty.call(input, key)) out[key] = input[key]
  if (Object.prototype.hasOwnProperty.call(input, 'minimiseWhileWorking') && !('moveAsideWhileWorking' in out)) out.moveAsideWhileWorking = input.minimiseWhileWorking
  return out
}
