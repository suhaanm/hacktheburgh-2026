import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { tokenize } from '../../src/main/files/bm25'
import { EmbedError, l2normalize, type Embedder } from '../../src/main/files/embed'
import type { GeminiExtractor } from '../../src/main/files/extract'
import { createFilesService, type FilesCtx } from '../../src/main/files/service'
import { SettingsStore } from '../../src/main/settings'

export const DIMS = 256

function hash(s: string): number {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619)
  return h >>> 0
}

// Bag-of-words hashing: texts that share words share direction, so cosine ranking is meaningful without a network.
export function embedText(text: string): Float32Array {
  const v = new Float32Array(DIMS)
  for (const t of tokenize(text)) v[hash(t) % DIMS] += 1
  return l2normalize(v)
}

export interface FakeEmbedder extends Embedder {
  docCalls: number
  docTexts: number
  queryCalls: number
  failWith: EmbedError | null
}

export function fakeEmbedder(model = 'fake-embed'): FakeEmbedder {
  const e: FakeEmbedder = {
    model,
    dims: DIMS,
    thresholds: { min: 0.2, weak: 0.35 },
    docCalls: 0,
    docTexts: 0,
    queryCalls: 0,
    failWith: null,
    async embedDocuments(items) {
      e.docCalls++
      if (e.failWith) throw e.failWith
      e.docTexts += items.length
      return items.map((i) => embedText(`${i.title} ${i.text}`))
    },
    async embedQuery(q) {
      e.queryCalls++
      if (e.failWith) throw e.failWith
      return embedText(q)
    },
  }
  return e
}

export function fakeExtractor(textFor: (file: string) => string | null = (f) => `Scanned text of ${path.basename(f)} about appointments`): GeminiExtractor & { calls: number } {
  const x = {
    calls: 0,
    async extract(file: { abs: string }) {
      x.calls++
      const t = textFor(file.abs)
      return t ? { ok: true as const, text: t } : { ok: false as const, reason: 'no text found' }
    },
  }
  return x
}

export interface Sandbox {
  root: string
  home: string
  userData: string
  docs: string
  write(rel: string, content: string | Buffer, base?: string): string
  cleanup(): void
}

// A fake home directory with a Documents folder, a Library folder and a .ssh folder, plus a separate userData dir.
export function sandbox(): Sandbox {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'files-test-')))
  const home = path.join(root, 'home')
  const userData = path.join(root, 'userData')
  const docs = path.join(home, 'Documents')
  for (const d of [docs, path.join(home, 'Library', 'Cookies'), path.join(home, '.ssh'), userData]) fs.mkdirSync(d, { recursive: true })
  return {
    root,
    home,
    userData,
    docs,
    write(rel, content, base = docs) {
      const abs = path.join(base, rel)
      fs.mkdirSync(path.dirname(abs), { recursive: true })
      fs.writeFileSync(abs, content)
      return abs
    },
    cleanup: () => fs.rmSync(root, { recursive: true, force: true }),
  }
}

export function makeCtx(userDataDir: string | null): FilesCtx & { settings: SettingsStore; patches: unknown[] } {
  const settings = new SettingsStore(null)
  const patches: unknown[] = []
  return { settings, patches, userDataDir, state: { patch: (p) => void patches.push(p) }, log: () => undefined }
}

export function makeService(sb: Sandbox, opts: { embedder?: Embedder | null; extractor?: GeminiExtractor | null; filesEnabled?: boolean; run?: Parameters<typeof createFilesService>[0]['run']; searchesPerMinute?: number } = {}) {
  const ctx = makeCtx(sb.userData)
  const embedder = opts.embedder === undefined ? fakeEmbedder() : opts.embedder
  const service = createFilesService({ ctx, home: sb.home, embedder, extractor: opts.extractor ?? null, run: opts.run, searchesPerMinute: opts.searchesPerMinute })
  if (opts.filesEnabled !== false) ctx.settings.patch({ filesEnabled: false })
  return { ctx, service, embedder }
}
