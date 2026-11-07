// macOS privacy permissions as seen by the main process. Shared by main (src/main/permissions.ts) and the renderers.

export type PermState = 'granted' | 'denied' | 'not-determined' | 'restricted' | 'unknown'
export type PermissionPane = 'screen' | 'microphone' | 'accessibility'
export type ScreenProbe = 'ok' | 'empty' | 'error' | 'skipped'

export interface PermissionStatus {
  microphone: PermState
  // 'granted' only when a real desktopCapturer probe returned sources (or the OS says granted and the probe was not needed).
  screen: PermState
  accessibility: boolean
  // What the probe saw: 'ok' sources came back, 'empty' none after retries, 'error' it threw, 'skipped' not run (see main).
  probe: ScreenProbe
  // The OS says Screen Recording is granted but capture still returns nothing: the app must be quit and reopened.
  needsRestart: boolean
  // Plain sentence naming which app to switch on in System Settings (the launching Terminal vs Electron vs Alongside).
  hint: string
}

export type PermissionRequestResult = boolean
