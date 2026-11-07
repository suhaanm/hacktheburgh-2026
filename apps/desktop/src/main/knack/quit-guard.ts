// Quit (Command-Q, the Dock menu, the menu bar) ends the app and the services it started, and never silently over a running job (rows 17 and 18 of
// docs/knack-ux/08-window-states.md): with nothing running it quits at once; otherwise a sheet asks "Knack is working. Stop it and quit?" with Stop and quit and
// Keep working, and when a routine set to run while the worker is away is due within 24 hours the sheet adds one line saying it will not run while Knack is closed.
// The decision comes from the shell machine; this file asks the question and acts on the answer.
import { APP_NAME } from '../../shared/brand'
import { INITIAL_SHELL, reduce } from './shell-machine'

export type QuitChoice = 'stop_and_quit' | 'keep_working'

export interface QuitSheet {
  message: string
  detail?: string
  buttons: readonly [string, string]
}

export interface QuitGuardDeps {
  /** A run is working or a voice session is open. */
  running: () => boolean
  /** A routine set to run while the worker is away is due in the next 24 hours. */
  awayRoutineDueWithin24h: () => boolean | Promise<boolean>
  /** Shows the sheet (a native message box); resolves with the button pressed. */
  ask: (sheet: QuitSheet) => Promise<QuitChoice>
  /** Stops everything that runs (the kill switch), then resolves. */
  stopAll: () => Promise<unknown> | unknown
  /** Quit again, now for real (app.quit). */
  quit: () => void
  /** From now on a close really closes. */
  markQuitting: () => void
}

export const sheetFor = (routineLine: boolean): QuitSheet => ({
  message: `${APP_NAME} is working. Stop it and quit?`,
  ...(routineLine ? { detail: `Routines set to run while you are away will not run until you open ${APP_NAME}.` } : {}),
  buttons: ['Stop and quit', 'Keep working'],
})

export interface QuitGuard {
  /** The `before-quit` listener. */
  onBeforeQuit(event: { preventDefault(): void }): void
  /** True once a quit has been allowed to go through. */
  proceeding(): boolean
}

export function createQuitGuard(deps: QuitGuardDeps): QuitGuard {
  let proceeding = false
  let asking = false
  return {
    proceeding: () => proceeding,
    onBeforeQuit(event) {
      if (proceeding) {
        deps.markQuitting()
        return
      }
      // The same decision as rows 17 and 18 of the machine: not running, quit; running, the sheet.
      const fx = reduce(INITIAL_SHELL, { type: 'quit', running: deps.running() }).effects
      if (fx.some((e) => e.type === 'quit')) {
        proceeding = true
        deps.markQuitting()
        return
      }
      event.preventDefault()
      if (asking) return
      asking = true
      void (async () => {
        try {
          const due = await deps.awayRoutineDueWithin24h()
          const line = reduce(INITIAL_SHELL, { type: 'quit', running: true, awayRoutineDueWithin24h: due }).effects.some((e) => e.type === 'quitSheet' && e.routineLine)
          const choice = await deps.ask(sheetFor(line))
          if (choice === 'stop_and_quit') {
            await deps.stopAll()
            proceeding = true
            deps.quit()
          }
        } catch {
          /* a sheet that cannot be shown is a "keep working": nothing is stopped behind the worker's back */
        } finally {
          asking = false
        }
      })()
    },
  }
}
