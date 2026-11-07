// Preload for the Knack main window. Three calls for the "Starting" and error page (the state, a state listener, Try again) and the platform name, which the
// dashboard reads to leave room for the macOS traffic lights (apps/dashboard/src/main.tsx). It runs on the dashboard too (same window) and gives it nothing more.
import { contextBridge, ipcRenderer } from 'electron'
import type { IpcRendererEvent } from 'electron'
import { KNACK_IPC, type DashboardSettingsView, type KnackModelsSetResult, type KnackModelsState, type KnackSettingsApi, type KnackShellApi, type ShellUiState } from '../shared/knack'

const api: KnackShellApi = {
  get: () => ipcRenderer.invoke(KNACK_IPC.get) as Promise<ShellUiState>,
  onState: (cb) => {
    const handler = (_e: IpcRendererEvent, state: ShellUiState) => cb(state)
    ipcRenderer.on(KNACK_IPC.state, handler)
    return () => ipcRenderer.off(KNACK_IPC.state, handler)
  },
  retry: () => ipcRenderer.send(KNACK_IPC.retry),
  platform: process.platform,
  models: {
    get: () => ipcRenderer.invoke(KNACK_IPC.modelsGet) as Promise<KnackModelsState>,
    setUseLiveModels: (on: boolean) => ipcRenderer.invoke(KNACK_IPC.modelsSet, on === true) as Promise<KnackModelsSetResult>,
  },
}
contextBridge.exposeInMainWorld('knackShell', api)

// The dashboard's Settings screen reads and changes the few desktop switches it shows (Move aside, Launch at login, Cue, Help level) through this, the name its bridge looks for.
// Main answers only this window's own page, with a small view and an allow-list for writes.
const settingsApi: KnackSettingsApi = {
  getSettings: () => ipcRenderer.invoke(KNACK_IPC.settingsGet) as Promise<DashboardSettingsView>,
  patchSettings: (patch) => ipcRenderer.invoke(KNACK_IPC.settingsPatch, patch) as Promise<DashboardSettingsView>,
}
contextBridge.exposeInMainWorld('knackSettings', settingsApi)
