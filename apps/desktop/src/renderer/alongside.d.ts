import type { AlongsideApi } from '../shared/ipc'

declare global {
  interface Window {
    alongside: AlongsideApi
  }
}
