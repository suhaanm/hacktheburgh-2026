// When the main window minimises itself and when it comes back. Pure rules; the shell (knack-shell.ts) performs the answer.
//
//   a new run starts (the pill goes from quiet to working)   -> minimise, if the setting minimiseWhileWorking is on and the window is up (not hide: the
//                                                               Dock icon and the window stay one click away; not in full screen)
//   the pill says needs-you                                  -> restore (also from the menu bar, after Cmd-W): the worker is needed
//   the worker clicks the pill or the Dock icon              -> restore
//   a run ends with nothing to approve (done, error, killed) -> do nothing: no window pops up
//
// A run that carries on after the worker approved something (needs-you -> working) does not minimise the window again.
import type { PillKind } from './pill-state'

export interface ShellWindowState {
  exists: boolean
  visible: boolean
  minimised: boolean
  fullScreen: boolean
}

export interface ShellSettings {
  minimiseWhileWorking: boolean
}

export type ShellAction = 'minimise' | 'restore' | 'none'

export type ShellEvent =
  | { type: 'pill'; from: PillKind; to: PillKind }
  | { type: 'pill-click' }
  | { type: 'dock-click' }
  /** The worker brought the window back themselves (menu, Dock, Cmd-Tab). */
  | { type: 'window-shown' }

export interface ShellMemo {
  /** The last minimise was ours (a run started), not the worker's own. */
  minimisedByUs: boolean
}
export const INITIAL_MEMO: ShellMemo = { minimisedByUs: false }

export function decideWindow(ev: ShellEvent, win: ShellWindowState, settings: ShellSettings, memo: ShellMemo): { action: ShellAction; memo: ShellMemo } {
  if (!win.exists) return { action: 'none', memo }
  const away = !win.visible || win.minimised
  switch (ev.type) {
    case 'pill': {
      if (ev.to === ev.from) return { action: 'none', memo }
      if (ev.to === 'needs-you') return away ? { action: 'restore', memo: { minimisedByUs: false } } : { action: 'none', memo }
      if (ev.to === 'working' && settings.minimiseWhileWorking && (ev.from === 'idle' || ev.from === 'done' || ev.from === 'error' || ev.from === 'killed')) {
        if (win.visible && !win.minimised && !win.fullScreen) return { action: 'minimise', memo: { minimisedByUs: true } }
      }
      return { action: 'none', memo }
    }
    case 'pill-click':
    case 'dock-click':
      return { action: 'restore', memo: { minimisedByUs: false } }
    case 'window-shown':
      return { action: 'none', memo: { minimisedByUs: false } }
  }
}
