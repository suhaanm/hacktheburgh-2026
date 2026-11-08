// Preload for the Ask bar window only: four calls (opened, submit, close, size) and nothing else of the app's IPC. Main checks the sender on every one.
import { contextBridge, ipcRenderer } from 'electron'
import type { IpcRendererEvent } from 'electron'
import { ASK_IPC, type AskApi, type AskSubmitResult } from '../main/knack/ask-ipc'

const api: AskApi = {
  onOpen: (cb) => {
    const handler = (_e: IpcRendererEvent, o: { prefill: string; closed?: boolean }) => cb(o)
    ipcRenderer.on(ASK_IPC.open, handler)
    return () => ipcRenderer.off(ASK_IPC.open, handler)
  },
  submit: (text) => ipcRenderer.invoke(ASK_IPC.submit, text) as Promise<AskSubmitResult>,
  close: () => ipcRenderer.send(ASK_IPC.close),
  size: (height) => ipcRenderer.send(ASK_IPC.size, height),
}

contextBridge.exposeInMainWorld('knackAsk', api)
