// Local index in userData/files-index/: meta.json (files + chunk text) and vectors-<gen>.f32 (Float32 rows, one per chunk).
// Atomic writes (temp file in the same folder, then rename), directory 0700, files 0600. meta.json names the vectors file,
// so a crash between the two writes leaves the previous consistent pair in place.
import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import { REDACT_VERSION } from './redact'

export type FileStatusKind = 'ok' | 'unembedded' | 'empty' | 'skipped'

export interface FileRecord {
  abs: string
  folder: string
  rel: string
  name: string
  ext: string
  size: number
  mtimeMs: number
  // sha1(size:mtime): the incremental re-index key.
  sig: string
  status: FileStatusKind
  reason?: string
  chunkCount: number
  indexedAt: number
}

export interface ChunkRec {
  file: string // FileRecord.abs
  ord: number
  text: string
  // 1 when this chunk has a vector in the vectors file.
  v: 0 | 1
}

export interface IndexData {
  version: 1
  embedModel: string
  dims: number
  files: Record<string, FileRecord>
  chunks: ChunkRec[]
  // One row of `dims` floats per chunk (zeros when v === 0).
  vectors: Float32Array
  updatedAt: number
  skippedFiles: number
  truncated: boolean
}

export const fileSig = (size: number, mtimeMs: number): string => crypto.createHash('sha1').update(`${size}:${mtimeMs}`).digest('hex').slice(0, 16)

export function emptyIndex(embedModel: string, dims: number): IndexData {
  return { version: 1, embedModel, dims, files: {}, chunks: [], vectors: new Float32Array(0), updatedAt: 0, skippedFiles: 0, truncated: false }
}

interface MetaFile {
  version: 1
  // Which redaction rules built this index; a different value means stale snippets, so the index is dropped and rebuilt.
  redactVersion?: number
  embedModel: string
  dims: number
  files: Record<string, FileRecord>
  chunks: ChunkRec[]
  vectorsFile: string
  updatedAt: number
  skippedFiles: number
  truncated: boolean
}

function writeAtomic(file: string, data: string | Uint8Array): void {
  const tmp = `${file}.tmp-${process.pid}-${crypto.randomBytes(4).toString('hex')}`
  const fd = fs.openSync(tmp, 'w', 0o600)
  try {
    fs.writeSync(fd, data as never)
    fs.fsyncSync(fd)
  } finally {
    fs.closeSync(fd)
  }
  fs.renameSync(tmp, file)
  fs.chmodSync(file, 0o600)
}

export class IndexStore {
  readonly dir: string

  constructor(userDataDir: string) {
    this.dir = path.join(userDataDir, 'files-index')
  }

  private ensureDir(): void {
    fs.mkdirSync(this.dir, { recursive: true, mode: 0o700 })
    fs.chmodSync(this.dir, 0o700)
  }

  // Returns null when there is no readable, consistent index.
  load(): IndexData | null {
    try {
      const meta = JSON.parse(fs.readFileSync(path.join(this.dir, 'meta.json'), 'utf8')) as MetaFile
      // Built with older redaction rules: delete it now (not just ignore it) so stale snippets cannot linger on disk.
      if (meta.version === 1 && meta.redactVersion !== REDACT_VERSION) {
        this.clear()
        return null
      }
      if (meta.version !== 1 || typeof meta.dims !== 'number' || !Array.isArray(meta.chunks)) return null
      const buf = fs.readFileSync(path.join(this.dir, path.basename(meta.vectorsFile)))
      const expected = meta.chunks.length * meta.dims * 4
      if (buf.byteLength !== expected) return null
      // Copy into an aligned buffer (a Node Buffer can sit at an odd byte offset).
      const vectors = new Float32Array(meta.chunks.length * meta.dims)
      new Uint8Array(vectors.buffer).set(buf)
      return { version: 1, embedModel: meta.embedModel, dims: meta.dims, files: meta.files, chunks: meta.chunks, vectors, updatedAt: meta.updatedAt, skippedFiles: meta.skippedFiles ?? 0, truncated: !!meta.truncated }
    } catch {
      return null
    }
  }

  save(data: IndexData): void {
    this.ensureDir()
    const gen = `${Date.now().toString(36)}-${crypto.randomBytes(3).toString('hex')}`
    const vectorsFile = `vectors-${gen}.f32`
    writeAtomic(path.join(this.dir, vectorsFile), new Uint8Array(data.vectors.buffer, data.vectors.byteOffset, data.vectors.byteLength))
    const meta: MetaFile = {
      version: 1,
      redactVersion: REDACT_VERSION,
      embedModel: data.embedModel,
      dims: data.dims,
      files: data.files,
      chunks: data.chunks,
      vectorsFile,
      updatedAt: data.updatedAt,
      skippedFiles: data.skippedFiles,
      truncated: data.truncated,
    }
    writeAtomic(path.join(this.dir, 'meta.json'), JSON.stringify(meta))
    for (const f of fs.readdirSync(this.dir)) {
      if (f.startsWith('vectors-') && f !== vectorsFile) fs.rmSync(path.join(this.dir, f), { force: true })
      else if (f.includes('.tmp-')) fs.rmSync(path.join(this.dir, f), { force: true })
    }
  }

  // "Delete everything it learned": the whole folder, nothing left behind.
  clear(): void {
    fs.rmSync(this.dir, { recursive: true, force: true })
  }

  exists(): boolean {
    return fs.existsSync(path.join(this.dir, 'meta.json'))
  }
}
