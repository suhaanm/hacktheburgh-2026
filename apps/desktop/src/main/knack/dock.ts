// The macOS Dock icon: shown by default (setting `showInDock`), hidden for a menu-bar-only app. Not Electron-typed beyond what it needs, so tests pass a fake.
import type { Settings } from '../../shared/settings'

export interface DockPort {
  show(): Promise<void> | void
  hide(): void
}

export type DockResult = 'shown' | 'hidden' | 'skipped'

export function applyShowInDock(show: boolean, deps: { platform?: NodeJS.Platform; dock?: DockPort; log?: (...a: unknown[]) => void }): DockResult {
  if ((deps.platform ?? process.platform) !== 'darwin' || !deps.dock) return 'skipped'
  try {
    if (show) void deps.dock.show()
    else deps.dock.hide()
  } catch (err) {
    deps.log?.('dock', err instanceof Error ? err.message : 'could not change the Dock icon')
    return 'skipped'
  }
  return show ? 'shown' : 'hidden'
}

/** Applies the setting now and again whenever it changes. Returns the unsubscribe. */
export function registerDock(
  settings: { get(): Pick<Settings, 'showInDock'>; onChange(l: (s: Settings, patch: Partial<Settings>) => void): () => void },
  deps: { platform?: NodeJS.Platform; dock?: DockPort; log?: (...a: unknown[]) => void; hidden?: boolean },
): () => void {
  // A hidden run (checks) never shows a Dock icon, whatever the setting says.
  applyShowInDock(deps.hidden ? false : settings.get().showInDock, deps)
  return settings.onChange((next, patch) => {
    if ('showInDock' in patch) applyShowInDock(deps.hidden ? false : next.showInDock, deps)
  })
}
