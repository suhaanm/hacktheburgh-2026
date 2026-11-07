// Query side: embed the query, cosine top-k over the stored vectors (best chunk per file), at most 3 short snippets back.
// If embeddings are unavailable the same chunks are searched with BM25 and the result is flagged mode:'keyword'.
import path from 'node:path'
import { FILES_LIMITS, type FileHit, type FilesSearchReason } from '../../shared/files'
import { bm25Search, normaliseBm25, tokenize } from './bm25'
import { EmbedError, type Embedder } from './embed'
import { cleanSnippet, looksLikeInjection } from './safety'
import type { FileRecord, IndexData } from './store'

// Calibrated on fixtures/files-demo with gemini-embedding-2 at 768-d (see docs/FILES.md): unrelated chunks sit around 0.50,
// a real match is 0.65 and up. Below MIN nothing is returned; below WEAK the result is marked unverified.
export const SEMANTIC_MIN = 0.56
export const SEMANTIC_WEAK = 0.64
const KEYWORD_WEAK = 0.34

export interface SearchOutcome {
  mode: 'semantic' | 'keyword'
  unverified: boolean
  hits: FileHit[]
  reason?: FilesSearchReason
  // Plain-English note about a fallback (shown to the person, not a stack trace).
  note?: string
}

export interface SearchInput {
  data: IndexData
  embedder: Embedder | null
  query: string
  k?: number
  // Only files from folders that are still consented are returned.
  allowed: (rec: FileRecord) => boolean
  signal?: AbortSignal
}

const tokenCache = new WeakMap<IndexData, string[][]>()
function chunkTokens(data: IndexData): string[][] {
  let t = tokenCache.get(data)
  if (!t) {
    t = data.chunks.map((c) => {
      const rec = data.files[c.file]
      const title = rec ? `${rec.name.replace(/\.[^.]+$/, '')} ${path.dirname(rec.rel)}` : ''
      return tokenize(`${title} ${title} ${c.text}`)
    })
    tokenCache.set(data, t)
  }
  return t
}

// The 400-char window of the chunk with the most query words (or its start).
export function pickSnippet(text: string, query: string, max: number = FILES_LIMITS.snippetChars): string {
  const flat = text.replace(/\s+/g, ' ').trim()
  if (flat.length <= max) return cleanSnippet(flat, max)
  const terms = new Set(tokenize(query))
  const words = flat.split(' ')
  let best = 0
  let bestScore = -1
  let pos = 0
  const starts: number[] = []
  for (const w of words) {
    starts.push(pos)
    pos += w.length + 1
  }
  for (let i = 0; i < words.length; i += 3) {
    const slice = flat.slice(starts[i], starts[i] + max)
    let score = 0
    for (const t of tokenize(slice)) if (terms.has(t)) score++
    if (score > bestScore) {
      bestScore = score
      best = starts[i]
    }
  }
  const slice = flat.slice(best, best + max)
  return (best > 0 ? '…' : '') + cleanSnippet(slice, max - (best > 0 ? 1 : 0))
}

function makeHit(rec: FileRecord, chunkText: string, score: number, query: string): FileHit {
  const snippet = pickSnippet(chunkText, query)
  return {
    name: rec.name,
    folder: path.basename(rec.folder) || rec.folder,
    relPath: rec.rel,
    path: rec.abs,
    modified: new Date(rec.mtimeMs).toISOString(),
    score: Math.round(score * 1000) / 1000,
    snippet,
    ...(looksLikeInjection(chunkText) ? { suspicious: true } : {}),
  }
}

export async function searchIndex(input: SearchInput): Promise<SearchOutcome> {
  const { data, embedder, query, allowed } = input
  const k = Math.max(1, Math.min(input.k ?? FILES_LIMITS.maxResults, FILES_LIMITS.maxResults))
  let note: string | undefined

  const semanticReady = !!embedder && embedder.model === data.embedModel && embedder.dims === data.dims && data.chunks.some((c) => c.v === 1)
  if (semanticReady) {
    try {
      const q = await (embedder as Embedder).embedQuery(query, input.signal)
      const dims = data.dims
      const minScore = embedder?.thresholds?.min ?? SEMANTIC_MIN
      const weakScore = embedder?.thresholds?.weak ?? SEMANTIC_WEAK
      const bestByFile = new Map<string, { score: number; i: number }>()
      for (let i = 0; i < data.chunks.length; i++) {
        const c = data.chunks[i]
        if (!c.v) continue
        const rec = data.files[c.file]
        if (!rec || !allowed(rec)) continue
        let dot = 0
        const off = i * dims
        for (let d = 0; d < dims; d++) dot += q[d] * data.vectors[off + d]
        const cur = bestByFile.get(c.file)
        if (!cur || dot > cur.score) bestByFile.set(c.file, { score: dot, i })
      }
      const ranked = [...bestByFile.entries()].sort((a, b) => b[1].score - a[1].score)
      const kept = ranked.filter(([, v]) => v.score >= minScore).slice(0, k)
      const hits = kept.map(([file, v]) => makeHit(data.files[file], data.chunks[v.i].text, v.score, query))
      if (hits.length === 0) return { mode: 'semantic', unverified: true, hits, reason: 'no_match' }
      return { mode: 'semantic', unverified: hits[0].score < SEMANTIC_WEAK, hits }
    } catch (e) {
      if (e instanceof EmbedError && e.code === 'aborted') throw e
      note = e instanceof EmbedError ? e.plain : 'I could not use my online helper, so I searched by words only.'
    }
  } else if (!embedder) {
    note = 'I searched by words only, because my online helper is not available.'
  }

  // Keyword fallback over the same chunks.
  const tokens = chunkTokens(data)
  const docs = data.chunks.map((c, id) => ({ id, tokens: tokens[id] })).filter((d) => {
    const rec = data.files[data.chunks[d.id].file]
    return rec && allowed(rec)
  })
  const qTerms = new Set(tokenize(query)).size
  const raw = bm25Search(docs, query, 200)
  const bestByFile = new Map<string, { score: number; matched: number; i: number }>()
  for (const h of raw) {
    const c = data.chunks[h.id]
    const score = normaliseBm25(h.raw, qTerms)
    const cur = bestByFile.get(c.file)
    if (!cur || score > cur.score) bestByFile.set(c.file, { score, matched: h.matched, i: h.id })
  }
  const ranked = [...bestByFile.entries()].sort((a, b) => b[1].score - a[1].score).slice(0, k)
  const hits = ranked.map(([file, v]) => makeHit(data.files[file], data.chunks[v.i].text, v.score, query))
  if (hits.length === 0) return { mode: 'keyword', unverified: true, hits, reason: 'no_match', note }
  const top = ranked[0][1]
  return { mode: 'keyword', unverified: top.score < KEYWORD_WEAK || top.matched < Math.max(1, Math.ceil(qTerms / 2)), hits, note }
}
