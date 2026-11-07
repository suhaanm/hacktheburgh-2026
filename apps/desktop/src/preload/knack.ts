// Preload for the Knack main window. Three calls for the "Starting" and error page (the state, a state listener, Try again) and the platform name, which the
// dashboard reads to leave room for the macOS traffic lights (apps/dashboard/src/main.tsx). It runs on the dashboard too (same window) and gives it nothing more.
import { contextBridge, ipcRenderer } from 'electron'
import type { IpcRendererEvent } from 'electron'
import { KNACK_IPC, type KnackModelsSetResult, type KnackModelsState, type KnackShellApi, type KnackWakeContext, type KnackWakeStatus, type ShellUiState } from '../shared/knack'

const api: KnackShellApi = {
  get: () => ipcRenderer.invoke(KNACK_IPC.get) as Promise<ShellUiState>,
  onState: (cb) => {
    const handler = (_e: IpcRendererEvent, state: ShellUiState) => cb(state)
    ipcRenderer.on(KNACK_IPC.state, handler)
    return () => ipcRenderer.off(KNACK_IPC.state, handler)
  },
  retry: () => ipcRenderer.send(KNACK_IPC.retry),
  platform: process.platform,
  // Hey Knack (src/main/wake/electron.ts): the status line and the switch for Settings; the shell may also report what the worker is looking at.
  wake: {
    state: () => ipcRenderer.invoke('wake:state') as Promise<KnackWakeStatus>,
    set: (listen: boolean) => ipcRenderer.invoke('wake:set', { listen: listen === true }) as Promise<KnackWakeStatus>,
    context: (c: KnackWakeContext) => ipcRenderer.invoke('wake:context', c) as Promise<boolean>,
  },
  models: {
    get: () => ipcRenderer.invoke(KNACK_IPC.modelsGet) as Promise<KnackModelsState>,
    setUseLiveModels: (on: boolean) => ipcRenderer.invoke(KNACK_IPC.modelsSet, on === true) as Promise<KnackModelsSetResult>,
  },
}
contextBridge.exposeInMainWorld('knackShell', api)
