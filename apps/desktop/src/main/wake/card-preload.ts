// Preload for the wake card window only: five calls, no access to the rest of the app's IPC.
import { contextBridge, ipcRenderer } from 'electron'
import type { IpcRendererEvent } from 'electron'
import { WAKE_CARD_IPC, type WakeCardApi, type WakeCardView } from './card-ipc'

const api: WakeCardApi = {
  onShow: (cb) => {
    const h = (_e: IpcRendererEvent, v: WakeCardView) => cb(v)
    ipcRenderer.on(WAKE_CARD_IPC.show, h)
    return () => ipcRenderer.off(WAKE_CARD_IPC.show, h)
  },
  onHide: (cb) => {
    const h = () => cb()
    ipcRenderer.on(WAKE_CARD_IPC.hide, h)
    return () => ipcRenderer.off(WAKE_CARD_IPC.hide, h)
  },
  answer: (a) => ipcRenderer.send(WAKE_CARD_IPC.answer, a),
  esc: (id) => ipcRenderer.send(WAKE_CARD_IPC.esc, id),
  size: (s) => ipcRenderer.send(WAKE_CARD_IPC.size, s),
}

contextBridge.exposeInMainWorld('knackWakeCard', api)
