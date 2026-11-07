// IPC for "Files I can look at". The folder comes from a native dialog opened HERE, in main: no renderer or model string
// is ever treated as a folder to read. Every handler rejects senders that are not our own windows.
import { dialog, ipcMain } from 'electron'
import type { IpcMainInvokeEvent } from 'electron'
import { z } from 'zod'
import { IPC } from '../../shared/ipc'
import type { FilesService } from '../../shared/files'

export interface FilesIpcDeps {
  files: FilesService
  owns(webContentsId: number): boolean
  log(scope: string, ...args: unknown[]): void
}

const SearchReq = z.object({ query: z.string().max(300), k: z.number().int().min(1).max(3).optional() })

export function registerFilesIpc({ files, owns, log }: FilesIpcDeps): void {
  const handle = (channel: string, fn: (...args: unknown[]) => unknown) => {
    ipcMain.handle(channel, (event: IpcMainInvokeEvent, ...args: unknown[]) => {
      if (!owns(event.sender.id)) throw new Error('IPC from an unknown sender')
      return fn(...args)
    })
  }

  let dialogOpen = false
  handle(IPC.filesAddFolder, async () => {
    if (dialogOpen) return { ok: false, canceled: true }
    dialogOpen = true
    try {
      const res = await dialog.showOpenDialog({
        title: 'Choose a folder I may look at',
        message: 'I will only read files in the folder you choose. You can remove it again at any time.',
        buttonLabel: 'Choose folder',
        properties: ['openDirectory'],
      })
      if (res.canceled || res.filePaths.length === 0) return { ok: false, canceled: true }
      return await files.addFolder(res.filePaths[0])
    } catch (err) {
      log('files', 'folder dialog failed:', err instanceof Error ? err.message : err)
      return { ok: false, error: 'I could not open the folder chooser.' }
    } finally {
      dialogOpen = false
    }
  })
  handle(IPC.filesRemoveFolder, (p) => files.removeFolder(z.string().max(1024).parse(p)))
  handle(IPC.filesList, () => files.status())
  handle(IPC.filesStatus, () => files.status())
  handle(IPC.filesReindex, () => files.reindex())
  handle(IPC.filesDeleteIndex, () => files.deleteIndex())
  handle(IPC.filesSearch, (req) => {
    const { query, k } = SearchReq.parse(req)
    return files.search(query, k)
  })
}
