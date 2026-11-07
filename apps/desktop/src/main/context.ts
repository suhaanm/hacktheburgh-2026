import type { Bus } from './bus'
import type { SettingsStore } from './settings'
import type { StateStore } from './state'
import type { EventArgs, EventChannel } from '../shared/ipc'
import type { OverlayCommand } from '../shared/protocol'

// What every service factory receives. No electron imports here so services stay unit-testable.
export interface ServiceContext {
  state: StateStore
  bus: Bus
  settings: SettingsStore
  userDataDir: string | null
  sendOverlay(cmd: OverlayCommand): void
  sendDock<C extends EventChannel>(channel: C, ...args: EventArgs<C>): void
  log(scope: string, ...args: unknown[]): void
}
