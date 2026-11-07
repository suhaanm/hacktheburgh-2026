// Preload for the Cue panel window only: four calls, no access to the rest of the app's IPC.
import { contextBridge, ipcRenderer } from 'electron'
import type { IpcRendererEvent } from 'electron'
import { CUE_IPC, type CueCardAction, type CueCardApi, type CueView } from './ipc'

const api: CueCardApi = {
  get: () => ipcRenderer.invoke(CUE_IPC.get) as Promise<CueView>,
  onView: (cb) => {
    const handler = (_e: IpcRendererEvent, view: CueView) => cb(view)
    ipcRenderer.on(CUE_IPC.view, handler)
    return () => ipcRenderer.off(CUE_IPC.view, handler)
  },
  action: (a: CueCardAction) => ipcRenderer.send(CUE_IPC.action, a),
  size: (s) => ipcRenderer.send(CUE_IPC.size, s),
}

contextBridge.exposeInMainWorld('understudyCue', api)
