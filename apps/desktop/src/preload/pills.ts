// Preload for the background agent pills window only: five calls (the view, its changes, open, stop, size) and nothing else of the app's IPC. Main checks the sender on every one.
import { contextBridge, ipcRenderer } from 'electron'
import type { IpcRendererEvent } from 'electron'
import { PILLS_IPC, type PillsApi } from '../main/knack/agent-pills-ipc'
import type { PillsView } from '../main/knack/agent-pills-model'

const api: PillsApi = {
  get: () => ipcRenderer.invoke(PILLS_IPC.get) as Promise<PillsView>,
  onState: (cb) => {
    const handler = (_e: IpcRendererEvent, v: PillsView) => cb(v)
    ipcRenderer.on(PILLS_IPC.state, handler)
    return () => ipcRenderer.off(PILLS_IPC.state, handler)
  },
  open: (id) => ipcRenderer.send(PILLS_IPC.open, id),
  stop: (id) => ipcRenderer.send(PILLS_IPC.stop, id),
  size: (height) => ipcRenderer.send(PILLS_IPC.size, height),
}

contextBridge.exposeInMainWorld('knackPills', api)
