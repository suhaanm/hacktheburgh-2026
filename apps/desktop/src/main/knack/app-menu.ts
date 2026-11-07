// The application menu and the Dock menu, as plain data. Electron turns the template into a Menu (applyAppMenu in knack-shell.ts); tests read it as data.
//
// Cmd-W closes the window and the app keeps running in the menu bar (main-window.ts hides a window that is asked to close). Cmd-Q quits and stops the
// services the app started. Edit has the standard roles so copy and paste work. The kill switch stays a global shortcut (hotkey.ts KILL_ACCELERATORS);
// the menu item only shows it and does not register a second copy.
import type { MenuItemConstructorOptions } from 'electron'

export interface MenuHandlers {
  openSettings(): void
  showWindow(): void
  stopEverything(): void
}

export interface AppMenuInput {
  appName: string
  platform: NodeJS.Platform
  isPackaged: boolean
  /** The kill switch's global accelerator as registered (null when none could be), shown on the item. */
  killAccelerator: string | null
  handlers: MenuHandlers
}

export function buildAppMenuTemplate(i: AppMenuInput): MenuItemConstructorOptions[] {
  const mac = i.platform === 'darwin'
  const settings: MenuItemConstructorOptions = { label: 'Settings…', accelerator: 'CommandOrControl+,', click: () => i.handlers.openSettings() }
  // Command-Shift-K works while Knack is frontmost (a menu accelerator is app-local); the global Option-Shift-Command-K stays in hotkey.ts and is shown on the menu bar
  // item. A global Command-Shift-K would take a common shortcut from other apps.
  const stop: MenuItemConstructorOptions = { label: 'Stop Everything', accelerator: 'Shift+CommandOrControl+K', click: () => i.handlers.stopEverything() }
  const appMenu: MenuItemConstructorOptions = {
    label: i.appName,
    submenu: [
      { label: `About ${i.appName}`, role: 'about' },
      { type: 'separator' },
      settings,
      { type: 'separator' },
      { role: 'services' },
      { type: 'separator' },
      { label: `Hide ${i.appName}`, role: 'hide' },
      { role: 'hideOthers' },
      { role: 'unhide' },
      { type: 'separator' },
      { label: `Quit ${i.appName}`, role: 'quit' },
    ],
  }
  const file: MenuItemConstructorOptions = {
    label: 'File',
    submenu: [stop, { type: 'separator' }, { label: 'Close Window', role: 'close', accelerator: 'CommandOrControl+W' }, ...(mac ? [] : [{ type: 'separator' as const }, settings, { label: `Quit ${i.appName}`, role: 'quit' as const }])],
  }
  const edit: MenuItemConstructorOptions = {
    label: 'Edit',
    submenu: [{ role: 'undo' }, { role: 'redo' }, { type: 'separator' }, { role: 'cut' }, { role: 'copy' }, { role: 'paste' }, { role: 'pasteAndMatchStyle' }, { role: 'delete' }, { role: 'selectAll' }],
  }
  const view: MenuItemConstructorOptions = {
    label: 'View',
    submenu: [{ role: 'togglefullscreen' }, ...(i.isPackaged ? [] : [{ type: 'separator' as const }, { role: 'reload' as const }, { role: 'toggleDevTools' as const }])],
  }
  const windowMenu: MenuItemConstructorOptions = {
    label: 'Window',
    submenu: [{ role: 'minimize' }, { role: 'zoom' }, { type: 'separator' }, { label: i.appName, accelerator: 'CommandOrControl+0', click: () => i.handlers.showWindow() }, ...(mac ? [{ type: 'separator' as const }, { role: 'front' as const }] : [])],
  }
  return [...(mac ? [appMenu] : []), file, edit, view, windowMenu]
}

export interface DockMenuInput {
  handlers: MenuHandlers & { openNeedsYou(): void; pause(): void; resume(): void }
  /** Things waiting for the worker. */
  needsYou: number
  paused: boolean
  stopped: boolean
}

/**
 * The menu on the Dock icon (right-click), exactly three rows: Needs you (n) when n is above 0, Pause for 1 hour (Resume now), and Stop everything (Resume after stopping).
 * Nothing else: a click on the icon opens the window, and the Dock icon never bounces.
 */
export function buildDockMenuTemplate(i: DockMenuInput): MenuItemConstructorOptions[] {
  return [
    ...(i.needsYou > 0 ? [{ label: `Needs you (${i.needsYou})`, click: () => i.handlers.openNeedsYou() }] : []),
    i.paused ? { label: 'Resume now', click: () => i.handlers.resume() } : { label: 'Pause for 1 hour', click: () => i.handlers.pause() },
    i.stopped ? { label: 'Resume after stopping', click: () => i.handlers.resume() } : { label: 'Stop everything', click: () => i.handlers.stopEverything() },
  ]
}
