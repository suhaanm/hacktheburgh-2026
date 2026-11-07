// Preload for the HUD window only: three calls, no access to the rest of the app's IPC.
import { contextBridge, ipcRenderer } from 'electron'
import type { IpcRendererEvent } from 'electron'
import { HUD_IPC, type HudAction, type HudApi, type HudState } from '../shared/hud'

const api: HudApi = {
  get: () => ipcRenderer.invoke(HUD_IPC.get) as Promise<HudState>,
  onState: (cb) => {
    const handler = (_e: IpcRendererEvent, state: HudState) => cb(state)
    ipcRenderer.on(HUD_IPC.state, handler)
    return () => ipcRenderer.off(HUD_IPC.state, handler)
  },
  action: (a: HudAction) => ipcRenderer.send(HUD_IPC.action, a),
}

contextBridge.exposeInMainWorld('understudyHud', api)
