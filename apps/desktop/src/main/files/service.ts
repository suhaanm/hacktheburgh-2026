// The files service: consent state (settings), the local index, indexing runs, search, and status for the UI.
import fs from 'node:fs'
import path from 'node:path'
import { FILE_DATA_NOTICE, FILES_LIMITS, type AddFolderResult, type FilesFolder, type FilesSearchResult, type FilesService, type FilesStatus } from '../../shared/files'
import type { Settings } from '../../shared/settings'
import { checkFolder } from './consent'
import type { Embedder } from './embed'
import type { GeminiExtractor } from './extract'
import { runIndex, type IndexRunOptions } from './indexer'
import { searchIndex } from './search'
import { IndexStore, type IndexData } from './store'

export interface FilesCtx {
  state: { patch(partial: { files?: FilesStatus }): unknown }
  settings: {
    get(): Settings
    patch(raw: unknown): Settings
    onChange(cb: (s: Settings, patch: Partial<Settings>) => void): () => void
  }
  userDataDir: string | null
  log(scope: string, ...args: unknown[]): void
}

export interface FilesServiceDeps {
  ctx: FilesCtx
  home: string
  embedder: Embedder | null
  extractor: GeminiExtractor | null
  now?: () => number
  run?: Partial<IndexRunOptions>
  // Re-index a few seconds after launch when the feature is on (changed files only).
  autoStart?: boolean
  // Searches per minute before the tool answers "slow down".
  searchesPerMinute?: number
}

const MAX_FOLDERS = 20
const inside = (child: string, parent: string) => child === parent || child.startsWith(parent + path.sep)

export function createFilesService(deps: FilesServiceDeps): FilesService {
  const { ctx, home, embedder, extractor } = deps
  const now = deps.now ?? Date.now
  const store = new IndexStore(ctx.userDataDir ?? path.join(process.cwd(), '.files-index-nodata'))
  const listeners = new Set<(s: FilesStatus) => void>()
  let index: IndexData | null = ctx.userDataDir ? store.load() : null
  let controller: AbortController | null = null
  let running: Promise<void> | null = null
  let pending = false
  let progress = { done: 0, total: 0 }
  let lastError: string | undefined
  let lastPublish = 0
  const searchTimes: number[] = []
  const memoryOnly = !ctx.userDataDir

  // The consented set: settings.fileFolders re-validated on every use, so a changed or tampered entry is simply ignored.
  const consented = (): string[] => {
    const out: string[] = []
    for (const f of ctx.settings.get().fileFolders) {
      const check = checkFolder(f, { home, extraBlocked: [store.dir] })
      if (check.ok) out.push(check.real)
    }
    return out
  }

  function status(): FilesStatus {
    const s = ctx.settings.get()
    const folderSet = consented()
    const counts = new Map<string, number>()
    let indexedFiles = 0
    if (index) {
      for (const rec of Object.values(index.files)) {
        if (rec.status !== 'ok' && rec.status !== 'unembedded') continue
        if (!folderSet.includes(rec.folder)) continue
        indexedFiles++
        counts.set(rec.folder, (counts.get(rec.folder) ?? 0) + 1)
      }
    }
    // Refused folders (/, home, ~/.ssh, system paths) are never listed; a folder that has merely gone missing is, so it can be removed.
    const folders: FilesFolder[] = s.fileFolders
      .filter((p) => checkFolder(p, { home, extraBlocked: [store.dir] }).ok || !fs.existsSync(p))
      .map((p) => {
        let real = p
        try {
          real = fs.realpathSync(p)
        } catch {
          // Missing folder: show it with 0 files so the person can remove it.
        }
        return { path: p, name: path.basename(real) || real, fileCount: counts.get(real) ?? 0 }
      })
    const semantic = !!(embedder && index && index.embedModel === embedder.model && index.chunks.some((c) => c.v === 1))
    return {
      enabled: s.filesEnabled,
      folders,
      indexing: running !== null,
      done: progress.done,
      total: progress.total,
      indexedFiles,
      chunks: index?.chunks.length ?? 0,
      lastIndexedAt: index?.updatedAt || null,
      skippedFiles: index?.skippedFiles ?? 0,
      truncated: index?.truncated ?? false,
      ...(lastError ? { lastError } : {}),
      mode: semantic ? 'semantic' : index && index.chunks.length > 0 ? 'keyword' : 'none',
      embedModel: embedder?.model ?? 'none',
    }
  }

  function publish(force = true): void {
    const t = now()
    if (!force && t - lastPublish < 250) return
    lastPublish = t
    const s = status()
    ctx.state.patch({ files: s })
    for (const l of listeners) l(s)
  }

  // Drop everything in the index that no longer belongs to a consented folder (used on Remove, no network needed).
  function prune(): void {
    if (!index) return
    const folderSet = new Set(consented())
    const keepFiles = Object.values(index.files).filter((r) => folderSet.has(r.folder))
    if (keepFiles.length === Object.keys(index.files).length) return
    if (keepFiles.length === 0) {
      store.clear()
      index = null
      return
    }
    const keep = new Set(keepFiles.map((r) => r.abs))
    const dims = index.dims
    const chunks = [] as IndexData['chunks']
    const rows: Float32Array[] = []
    index.chunks.forEach((c, i) => {
      if (!keep.has(c.file)) return
      chunks.push(c)
      rows.push(index?.vectors.subarray(i * dims, (i + 1) * dims) as Float32Array)
    })
    const vectors = new Float32Array(chunks.length * dims)
    rows.forEach((r, i) => vectors.set(r, i * dims))
    index = { ...index, files: Object.fromEntries(keepFiles.map((r) => [r.abs, r])), chunks, vectors, updatedAt: now() }
    if (!memoryOnly) store.save(index)
  }

  async function runOnce(): Promise<void> {
    const s = ctx.settings.get()
    const folders = consented()
    if (!s.filesEnabled || folders.length === 0 || memoryOnly) {
      prune()
      return
    }
    controller = new AbortController()
    progress = { done: 0, total: 0 }
    lastError = undefined
    publish()
    try {
      const result = await runIndex(
        folders,
        { store, embedder, extractor, home, now, log: ctx.log },
        {
          ...deps.run,
          signal: controller.signal,
          onProgress: (p) => {
            progress = p
            publish(false)
          },
        },
      )
      index = result.data
      lastError = result.error
      if (result.rejectedFolders.length) lastError ??= 'One of your folders could not be opened, so I skipped it.'
      ctx.log('files', `indexed: ${result.changed} read, ${result.unchanged} unchanged, ${result.removed} removed, mode=${status().mode}`)
    } catch (e) {
      lastError = 'I could not finish looking through your files.'
      ctx.log('files', `index run failed: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      controller = null
    }
  }

  function reindex(): Promise<FilesStatus> {
    if (running) {
      pending = true
      return running.then(status)
    }
    running = (async () => {
      do {
        pending = false
        await runOnce()
      } while (pending)
    })().finally(() => {
      running = null
      publish()
    })
    publish()
    return running.then(status)
  }

  const unsubscribe = ctx.settings.onChange((s, patch) => {
    if ('filesEnabled' in patch) {
      if (s.filesEnabled) void reindex()
      else {
        controller?.abort()
        publish()
      }
    } else if ('fileFolders' in patch) {
      prune()
      if (s.filesEnabled) void reindex()
      else publish()
    }
  })

  let startTimer: ReturnType<typeof setTimeout> | undefined
  if (deps.autoStart && !memoryOnly) {
    startTimer = setTimeout(() => {
      if (ctx.settings.get().filesEnabled) void reindex()
    }, 4000)
    startTimer.unref?.()
  }

  const notice = (partial: Omit<FilesSearchResult, 'results' | 'data_notice'> & { results?: FilesSearchResult['results'] }): FilesSearchResult => ({ results: [], data_notice: FILE_DATA_NOTICE, ...partial })

  return {
    status,
    async addFolder(input) {
      const check = checkFolder(input, { home, extraBlocked: [store.dir] })
      if (!check.ok) return { ok: false, error: check.error }
      const current = ctx.settings.get().fileFolders
      const real = check.real
      const existing = consented()
      if (existing.some((e) => inside(real, e))) return { ok: false, error: 'That folder is already included.' }
      if (current.length >= MAX_FOLDERS) return { ok: false, error: 'That is plenty of folders for now. Remove one first.' }
      const kept = current.filter((p) => {
        try {
          return !inside(fs.realpathSync(p), real)
        } catch {
          return true
        }
      })
      ctx.settings.patch({ fileFolders: [...kept, real] })
      publish()
      return { ok: true, path: real, name: check.name } satisfies AddFolderResult
    },
    async removeFolder(input) {
      const current = ctx.settings.get().fileFolders
      let target = input
      try {
        target = fs.realpathSync(input)
      } catch {
        // Folder gone: match the stored string.
      }
      ctx.settings.patch({
        fileFolders: current.filter((p) => {
          if (p === input) return false
          try {
            return fs.realpathSync(p) !== target
          } catch {
            return true
          }
        }),
      })
      prune()
      publish()
      return status()
    },
    reindex,
    async deleteIndex() {
      controller?.abort()
      if (running) await running.catch(() => undefined)
      store.clear()
      index = null
      progress = { done: 0, total: 0 }
      lastError = undefined
      publish()
      return status()
    },
    async search(rawQuery, k) {
      const s = ctx.settings.get()
      const query = typeof rawQuery === 'string' ? rawQuery.replace(/\s+/g, ' ').trim().slice(0, 300) : ''
      if (!s.filesEnabled) return notice({ ok: false, mode: 'none', unverified: true, reason: 'files_off', note: 'File search is switched off. The person can switch it on in settings and choose folders.' })
      const folderSet = new Set(consented())
      if (folderSet.size === 0) return notice({ ok: false, mode: 'none', unverified: true, reason: 'no_folders', note: 'No folders have been chosen yet.' })
      if (!query) return notice({ ok: false, mode: 'none', unverified: true, reason: 'empty_query' })
      const t = now()
      while (searchTimes.length && t - searchTimes[0] > 60_000) searchTimes.shift()
      if (searchTimes.length >= (deps.searchesPerMinute ?? 20)) return notice({ ok: false, mode: 'none', unverified: true, reason: 'rate_limited', note: 'Too many searches in a row. Ask the person what they are looking for first.' })
      searchTimes.push(t)
      if (!index || index.chunks.length === 0) {
        return notice(running ? { ok: false, mode: 'none', unverified: true, reason: 'indexing', note: 'Still looking through the files; try again in a moment.' } : { ok: false, mode: 'none', unverified: true, reason: 'not_indexed', note: 'The files have not been looked through yet.' })
      }
      try {
        const out = await searchIndex({ data: index, embedder, query, k, allowed: (rec) => folderSet.has(rec.folder) })
        ctx.log('files', `search (${query.length} chars) -> ${out.hits.length} hit(s), ${out.mode}${out.unverified ? ', weak' : ''}`)
        return notice({
          ok: out.hits.length > 0,
          mode: out.mode,
          unverified: out.unverified,
          ...(out.reason ? { reason: out.reason } : {}),
          ...(out.note || running ? { note: [out.note, running ? 'Still learning some files, so this may be incomplete.' : ''].filter(Boolean).join(' ') } : {}),
          results: out.hits.slice(0, FILES_LIMITS.maxResults),
        })
      } catch (e) {
        ctx.log('files', `search failed: ${e instanceof Error ? e.message : String(e)}`)
        return notice({ ok: false, mode: 'none', unverified: true, reason: 'error', note: 'The search did not work.' })
      }
    },
    resolveIndexedPath(p) {
      if (!index || !ctx.settings.get().filesEnabled || typeof p !== 'string' || !path.isAbsolute(p)) return null
      let real: string
      try {
        real = fs.realpathSync(p)
      } catch {
        return null
      }
      const rec = index.files[real]
      if (!rec || (rec.status !== 'ok' && rec.status !== 'unembedded')) return null
      return consented().includes(rec.folder) ? real : null
    },
    onStatus(cb) {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    dispose() {
      controller?.abort()
      unsubscribe()
      if (startTimer) clearTimeout(startTimer)
    },
  }
}
