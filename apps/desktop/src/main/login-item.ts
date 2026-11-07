// "Open at login": macOS only, and only for a packaged build (a dev build would register the bare Electron binary).
import { app } from 'electron'
import type { Settings } from '../shared/settings'

export type LoginItemResult = 'applied' | 'unchanged' | 'skipped-platform' | 'skipped-dev'

export interface LoginItemDeps {
  platform?: NodeJS.Platform
  isPackaged?: boolean
  getOpenAtLogin?: () => boolean
  setOpenAtLogin?: (open: boolean) => void
  log?: (...args: unknown[]) => void
}

export function applyLoginItem(openAtLogin: boolean, deps: LoginItemDeps = {}): LoginItemResult {
  const log = deps.log ?? ((...args: unknown[]) => console.log('[login-item]', ...args))
  if ((deps.platform ?? process.platform) !== 'darwin') return 'skipped-platform'
  if (!(deps.isPackaged ?? app.isPackaged)) {
    if (openAtLogin) log('launchAtLogin is on but this is a development build: not registering a login item (it only works in the packaged app)')
    return 'skipped-dev'
  }
  const current = (deps.getOpenAtLogin ?? (() => app.getLoginItemSettings().openAtLogin))()
  if (current === openAtLogin) return 'unchanged'
  ;(deps.setOpenAtLogin ?? ((open: boolean) => app.setLoginItemSettings({ openAtLogin: open })))(openAtLogin)
  log(`open at login ${openAtLogin ? 'enabled' : 'disabled'}`)
  return 'applied'
}

/** Applies the setting now and again whenever it changes. Returns the unsubscribe. */
export function registerLoginItem(
  settings: { get(): Settings; onChange(l: (s: Settings, patch: Partial<Settings>) => void): () => void },
  deps: LoginItemDeps = {},
): () => void {
  applyLoginItem(settings.get().launchAtLogin, deps)
  return settings.onChange((next, patch) => {
    if ('launchAtLogin' in patch) applyLoginItem(next.launchAtLogin, deps)
  })
}
