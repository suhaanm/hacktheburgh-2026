const { contextBridge, ipcRenderer } = require('electron')
contextBridge.exposeInMainWorld('harness', { getToken: () => ipcRenderer.invoke('wake:token'), readWav: () => ipcRenderer.invoke('wake:wav') })
