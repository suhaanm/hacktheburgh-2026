// Preload for the corner pill window only: read its view, listen for changes, press Stop or open Knack, and say whether the pointer is over a part that takes
// clicks. No access to the rest of the app's IPC.
import { contextBridge, ipcRenderer } from 'electron'
import type { IpcRendererEvent } from 'electron'
import { PILL_IPC, type KnackPillApi, type PillActionDto, type PillViewDto } from '../shared/knack'

const api: KnackPillApi = {
  get: () => ipcRenderer.invoke(PILL_IPC.get) as Promise<PillViewDto>,
  onState: (cb) => {
    const handler = (_e: IpcRendererEvent, view: PillViewDto) => cb(view)
    ipcRenderer.on(PILL_IPC.state, handler)
    return () => ipcRenderer.off(PILL_IPC.state, handler)
  },
  action: (a: PillActionDto) => ipcRenderer.send(PILL_IPC.action, a),
  setInteractive: (on: boolean) => ipcRenderer.send(PILL_IPC.interactive, on === true),
}

contextBridge.exposeInMainWorld('knackPill', api)
