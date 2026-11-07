// One incremental index run: scan the consented folders, re-read only files whose size+mtime changed, redact, chunk, embed,
// then write the whole index atomically. Embedding failure never loses text: chunks are kept for keyword search.
import { FILES_LIMITS } from '../../shared/files'
import { chunkText } from './chunk'
import { checkFolder, scanFolders, skippedTotal, type ScannedFile } from './consent'
import { EmbedError, type Embedder } from './embed'
import { needsGemini, readLocalText, type GeminiExtractor } from './extract'
import { redactForIndex } from './redact'
import { emptyIndex, fileSig, type ChunkRec, type FileRecord, type IndexData, type IndexStore } from './store'

export interface IndexerDeps {
  store: IndexStore
  embedder: Embedder | null
  extractor: GeminiExtractor | null
  home: string
  now?: () => number
  log?: (scope: string, ...args: unknown[]) => void
}

export interface IndexRunOptions {
  signal?: AbortSignal
  onProgress?: (p: { done: number; total: number }) => void
  maxGemini?: number
  concurrency?: number
  maxFiles?: number
  maxTotalBytes?: number
}

export interface IndexRunResult {
  data: IndexData
  total: number
  changed: number
  removed: number
  unchanged: number
  geminiDeferred: number
  aborted: boolean
  // Plain-English; set when embeddings were unavailable so search fell back to keywords.
  error?: string
  // Folders that failed the consent check this run (moved, now too broad, ...). They are skipped, never read.
  rejectedFolders: string[]
}

interface Processed {
  rec: FileRecord
  chunks: ChunkRec[]
  vectors: Float32Array[]
}

const RETRY_STATUS = new Set(['unembedded'])

export async function runIndex(folders: string[], deps: IndexerDeps, opts: IndexRunOptions = {}): Promise<IndexRunResult> {
  const now = deps.now ?? Date.now
  const embedder = deps.embedder
  const loaded = deps.store.load()
  const dims = embedder?.dims ?? loaded?.dims ?? 768
  // A different embedding model or size means old vectors are not comparable: re-embed everything.
  const modelChanged = !!(loaded && embedder && (loaded.embedModel !== embedder.model || loaded.dims !== embedder.dims))
  const prev: IndexData = loaded && !modelChanged ? loaded : emptyIndex(embedder?.model ?? loaded?.embedModel ?? 'none', dims)
  const prevDims = prev.dims

  const rejectedFolders: string[] = []
  const okFolders: string[] = []
  for (const f of folders) {
    const check = checkFolder(f, { home: deps.home, extraBlocked: [deps.store.dir] })
    if (check.ok) okFolders.push(check.real)
    else rejectedFolders.push(f)
  }

  const scan = scanFolders(okFolders, { exclude: [deps.store.dir], maxFiles: opts.maxFiles, maxTotalBytes: opts.maxTotalBytes })
  const scanned = new Map<string, ScannedFile>(scan.files.map((f) => [f.abs, f]))

  const toProcess: ScannedFile[] = []
  let unchanged = 0
  for (const f of scan.files) {
    const old = prev.files[f.abs]
    const same = old && old.sig === fileSig(f.size, f.mtimeMs) && !RETRY_STATUS.has(old.status) && old.reason !== 'deferred'
    const retryEmbed = old && RETRY_STATUS.has(old.status) && old.sig === fileSig(f.size, f.mtimeMs) && !embedder
    if (same || retryEmbed) unchanged++
    else toProcess.push(f)
  }
  const removed = Object.keys(prev.files).filter((k) => !scanned.has(k)).length

  // PDFs and images cost one Gemini call each: cap per run, the rest are picked up on the next Refresh.
  const maxGemini = opts.maxGemini ?? FILES_LIMITS.maxGeminiPerRun
  let geminiUsed = 0
  const work: ScannedFile[] = []
  const deferred: ScannedFile[] = []
  for (const f of toProcess) {
    if (needsGemini(f)) {
      if (!deps.extractor || geminiUsed >= maxGemini) {
        deferred.push(f)
        continue
      }
      geminiUsed++
    }
    work.push(f)
  }

  const total = work.length
  let done = 0
  opts.onProgress?.({ done, total })
  let firstError: string | undefined
  let embedBroken = false
  const results = new Map<string, Processed>()

  const processOne = async (file: ScannedFile): Promise<Processed> => {
    const base: FileRecord = {
      abs: file.abs,
      folder: file.folder,
      rel: file.rel,
      name: file.name,
      ext: file.ext,
      size: file.size,
      mtimeMs: file.mtimeMs,
      sig: fileSig(file.size, file.mtimeMs),
      status: 'ok',
      chunkCount: 0,
      indexedAt: now(),
    }
    const read = needsGemini(file) ? await (deps.extractor as GeminiExtractor).extract(file) : readLocalText(file)
    if (!read.ok) return { rec: { ...base, status: 'skipped', reason: read.reason }, chunks: [], vectors: [] }
    const pieces = chunkText(redactForIndex(read.text))
    if (pieces.length === 0) return { rec: { ...base, status: 'empty' }, chunks: [], vectors: [] }

    let vectors: Float32Array[] = []
    if (embedder && !embedBroken) {
      try {
        vectors = await embedder.embedDocuments(
          pieces.map((p) => ({ title: file.name.replace(/\.[^.]+$/, ''), text: p.text })),
          opts.signal,
        )
      } catch (e) {
        if (e instanceof EmbedError && e.code === 'aborted') throw e
        embedBroken = true
        firstError ??= e instanceof EmbedError ? e.plain : 'I could not learn some of your files, so I will search them by words.'
        deps.log?.('files', `embedding unavailable: ${e instanceof Error ? e.message : String(e)}`)
        vectors = []
      }
    }
    const embedded = vectors.length === pieces.length
    const chunks: ChunkRec[] = pieces.map((p, i) => ({ file: file.abs, ord: i, text: p.text, v: embedded ? 1 : 0 }))
    return { rec: { ...base, status: embedded ? 'ok' : 'unembedded', chunkCount: chunks.length }, chunks, vectors: embedded ? vectors : [] }
  }

  let next = 0
  const worker = async () => {
    while (!opts.signal?.aborted) {
      const idx = next++
      if (idx >= work.length) return
      const file = work[idx]
      try {
        results.set(file.abs, await processOne(file))
      } catch (e) {
        if (e instanceof EmbedError && e.code === 'aborted') return
        deps.log?.('files', `could not process a file: ${e instanceof Error ? e.message : String(e)}`)
        results.set(file.abs, { rec: { abs: file.abs, folder: file.folder, rel: file.rel, name: file.name, ext: file.ext, size: file.size, mtimeMs: file.mtimeMs, sig: fileSig(file.size, file.mtimeMs), status: 'skipped', reason: 'could not be read', chunkCount: 0, indexedAt: now() }, chunks: [], vectors: [] })
      }
      done++
      opts.onProgress?.({ done, total })
    }
  }
  await Promise.all(Array.from({ length: Math.max(1, Math.min(opts.concurrency ?? 3, 6)) }, worker))
  const aborted = !!opts.signal?.aborted

  // Merge in scan order: unchanged files keep their rows, processed files bring theirs.
  const prevByFile = new Map<string, number[]>()
  prev.chunks.forEach((c, i) => {
    const list = prevByFile.get(c.file)
    if (list) list.push(i)
    else prevByFile.set(c.file, [i])
  })
  const files: Record<string, FileRecord> = {}
  const chunks: ChunkRec[] = []
  const rows: Float32Array[] = []
  const zero = new Float32Array(dims)
  const keepPrev = (abs: string) => {
    const rec = prev.files[abs]
    if (!rec) return
    files[abs] = rec
    for (const i of prevByFile.get(abs) ?? []) {
      chunks.push(prev.chunks[i])
      rows.push(prev.chunks[i].v ? prev.vectors.subarray(i * prevDims, (i + 1) * prevDims) : zero)
    }
  }
  for (const f of scan.files) {
    const got = results.get(f.abs)
    if (got) {
      files[f.abs] = got.rec
      got.chunks.forEach((c, i) => {
        chunks.push(c)
        rows.push(c.v ? got.vectors[i] : zero)
      })
    } else if (deferred.includes(f)) {
      files[f.abs] = { abs: f.abs, folder: f.folder, rel: f.rel, name: f.name, ext: f.ext, size: f.size, mtimeMs: f.mtimeMs, sig: fileSig(f.size, f.mtimeMs), status: 'skipped', reason: 'deferred', chunkCount: 0, indexedAt: now() }
    } else {
      keepPrev(f.abs)
    }
  }

  const vectors = new Float32Array(chunks.length * dims)
  rows.forEach((r, i) => vectors.set(r.length === dims ? r : zero, i * dims))
  const data: IndexData = {
    version: 1,
    embedModel: prev.embedModel,
    dims,
    files,
    chunks,
    vectors,
    updatedAt: now(),
    skippedFiles: skippedTotal(scan.skipped) - scan.skipped.hidden - scan.skipped.unsupported + deferred.length + Object.values(files).filter((r) => r.status === 'skipped' && r.reason !== 'deferred').length,
    truncated: scan.truncated,
  }
  deps.store.save(data)
  return { data, total, changed: work.length, removed, unchanged, geminiDeferred: deferred.length, aborted, error: firstError, rejectedFolders }
}
