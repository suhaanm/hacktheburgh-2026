// Embeddings for the files index. The model id comes from src/shared/models.ts (MODELS.embed).
// Verified against this project's key (models.list + embedContent): `gemini-embedding-2` (stable) and `gemini-embedding-001`.
//   - gemini-embedding-2 has no task_type: queries/documents get a text prefix, and several strings in one `contents` array
//     become ONE aggregated vector, so every chunk is wrapped in its own Content object (verified: 100 per request).
//   - gemini-embedding-001 takes taskType and returns one vector per string, but only 3072-d is pre-normalised.
// Vectors are L2-normalised here either way, so cosine similarity is a dot product.
import { GoogleGenAI } from '@google/genai'
import { config as loadEnv } from 'dotenv'
import { MODELS } from '../../shared/models'

export const EMBED_DIMS = 768

export interface Embedder {
  model: string
  dims: number
  // Optional cosine cut-offs for models whose score scale differs from gemini-embedding-2 (used by test fakes).
  thresholds?: { min: number; weak: number }
  embedDocuments(items: Array<{ title: string; text: string }>, signal?: AbortSignal): Promise<Float32Array[]>
  embedQuery(query: string, signal?: AbortSignal): Promise<Float32Array>
}

export class EmbedError extends Error {
  constructor(
    public readonly code: 'auth' | 'rate_limit' | 'network' | 'api' | 'timeout' | 'aborted',
    message: string,
  ) {
    super(message)
    this.name = 'EmbedError'
  }
  get plain(): string {
    switch (this.code) {
      case 'auth':
        return "I can't reach my online helper to learn your files, because it isn't set up yet. I'll search by words instead."
      case 'rate_limit':
        return 'My online helper is busy right now. I searched by words for now; try Refresh in a little while.'
      case 'network':
        return "I can't reach the internet right now, so I searched by words only."
      case 'timeout':
        return 'That took too long, so I searched by words only.'
      default:
        return 'Something went wrong learning your files, so I searched by words only.'
    }
  }
}

export interface EmbedClientLike {
  models: { embedContent(params: Record<string, unknown>): Promise<{ embeddings?: Array<{ values?: number[] }> }> }
}

export function l2normalize(v: ArrayLike<number>): Float32Array {
  const out = new Float32Array(v.length)
  let sum = 0
  for (let i = 0; i < v.length; i++) sum += v[i] * v[i]
  const norm = Math.sqrt(sum) || 1
  for (let i = 0; i < v.length; i++) out[i] = v[i] / norm
  return out
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))
const statusOf = (e: unknown): number | undefined => {
  const s = (e as { status?: unknown; statusCode?: unknown } | null) ?? {}
  return typeof s.status === 'number' ? s.status : typeof s.statusCode === 'number' ? s.statusCode : undefined
}

export interface GeminiEmbedderOptions {
  model?: string
  dims?: number
  batchSize?: number
  timeoutMs?: number
  retries?: number
  log?: (scope: string, ...args: unknown[]) => void
}

const isV2 = (model: string) => /embedding-2/.test(model)

export function createGeminiEmbedder(client: EmbedClientLike, opts: GeminiEmbedderOptions = {}): Embedder {
  const model = opts.model ?? MODELS.embed
  const dims = opts.dims ?? EMBED_DIMS
  const batchSize = opts.batchSize ?? 64
  const timeoutMs = opts.timeoutMs ?? 25_000
  const retries = opts.retries ?? 2
  const v2 = isV2(model)

  async function call(contents: unknown[], taskType: string | undefined, signal?: AbortSignal): Promise<number[][]> {
    let last: unknown
    for (let attempt = 0; attempt <= retries; attempt++) {
      if (signal?.aborted) throw new EmbedError('aborted', 'aborted')
      let timer: ReturnType<typeof setTimeout> | undefined
      try {
        const request = client.models.embedContent({
          model,
          contents,
          config: { outputDimensionality: dims, ...(taskType && !v2 ? { taskType } : {}) },
        })
        request.catch(() => undefined)
        const deadline = new Promise<never>((_, reject) => {
          timer = setTimeout(() => reject(Object.assign(new Error('deadline'), { name: 'TimeoutError' })), timeoutMs)
        })
        const res = await Promise.race([request, deadline])
        const vectors = (res.embeddings ?? []).map((e) => e.values ?? [])
        if (vectors.length !== contents.length || vectors.some((x) => x.length < dims)) {
          throw Object.assign(new Error(`embedding count/size mismatch (${vectors.length}/${contents.length})`), { status: 502 })
        }
        return vectors
      } catch (e) {
        last = e
        const status = statusOf(e)
        if (status === 401 || status === 403 || status === 400 || status === 404) break
        if (attempt < retries) await sleep(Math.min(4000, 400 * 2 ** attempt + Math.random() * 300))
      } finally {
        if (timer) clearTimeout(timer)
      }
    }
    const status = statusOf(last)
    const name = (last as { name?: string } | null)?.name
    if (name === 'TimeoutError') throw new EmbedError('timeout', 'embedding timed out')
    if (status === 401 || status === 403) throw new EmbedError('auth', `embedding refused (${status})`)
    if (status === 429) throw new EmbedError('rate_limit', 'embedding rate limited')
    if (status === undefined) throw new EmbedError('network', 'embedding network error')
    throw new EmbedError('api', `embedding failed (${status})`)
  }

  const asContent = (text: string) => ({ role: 'user', parts: [{ text }] })
  const docText = (d: { title: string; text: string }) => (v2 ? `title: ${d.title || 'none'} | text: ${d.text}` : d.text)

  return {
    model,
    dims,
    async embedDocuments(items, signal) {
      const out: Float32Array[] = []
      for (let i = 0; i < items.length; i += batchSize) {
        const batch = items.slice(i, i + batchSize)
        // v2: one Content per chunk (else the batch collapses into one vector). 001: plain strings are fine.
        const contents = v2 ? batch.map((d) => asContent(docText(d))) : batch.map(docText)
        const vectors = await call(contents, 'RETRIEVAL_DOCUMENT', signal)
        for (const v of vectors) out.push(l2normalize(v.slice(0, dims)))
      }
      return out
    },
    async embedQuery(query, signal) {
      const text = v2 ? `task: search result | query: ${query}` : query
      const [v] = await call([v2 ? asContent(text) : text], 'RETRIEVAL_QUERY', signal)
      return l2normalize(v.slice(0, dims))
    },
  }
}

// The real client. Returns null without a key so the app still runs (keyword search only).
export function createEmbedderFromEnv(log?: GeminiEmbedderOptions['log']): Embedder | null {
  if (!process.env.GEMINI_API_KEY) loadEnv({ path: `${process.cwd()}/.env`, quiet: true })
  const apiKey = process.env.GEMINI_API_KEY
  if (!apiKey) return null
  const sdk = new GoogleGenAI({ apiKey })
  return createGeminiEmbedder({ models: { embedContent: (p) => sdk.models.embedContent(p as never) } }, { log })
}
