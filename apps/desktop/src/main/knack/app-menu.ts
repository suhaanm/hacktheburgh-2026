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
  const stop: MenuItemConstructorOptions = {
    label: 'Stop Everything',
    ...(i.killAccelerator ? { accelerator: i.killAccelerator, registerAccelerator: false } : {}),
    click: () => i.handlers.stopEverything(),
  }
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

/** The menu on the Dock icon (right-click): open Knack, and the one safety control. */
export function buildDockMenuTemplate(i: Pick<AppMenuInput, 'appName' | 'handlers'>): MenuItemConstructorOptions[] {
  return [
    { label: `Open ${i.appName}`, click: () => i.handlers.showWindow() },
    { label: 'Stop Everything', click: () => i.handlers.stopEverything() },
  ]
}
