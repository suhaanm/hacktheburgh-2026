// Keyword search over the same chunks: the fallback when embeddings are unavailable, and a flagged one (mode 'keyword').
const STOP = new Set(
  'a an and are as at be but by for from has have i if in into is it its me my of on or our so that the their them then there these they this to was we were what when where which who why will with you your did do does how about can could would should save saved find found file files document documents please show tell any some'.split(
    ' ',
  ),
)

export function tokenize(text: string): string[] {
  const out: string[] = []
  for (const raw of text.toLowerCase().split(/[^a-z0-9£$€]+/)) {
    if (!raw || raw.length < 2 || STOP.has(raw)) continue
    out.push(stem(raw))
  }
  return out
}

function stem(w: string): string {
  if (w.length > 4 && w.endsWith('ies')) return `${w.slice(0, -3)}y`
  if (w.length > 4 && w.endsWith('es') && /(ss|x|ch|sh)es$/.test(w)) return w.slice(0, -2)
  if (w.length > 3 && w.endsWith('s') && !w.endsWith('ss')) return w.slice(0, -1)
  return w
}

export interface Bm25Doc {
  id: number
  tokens: string[]
}

export interface Bm25Hit {
  id: number
  raw: number
  matched: number
}

export function bm25Search(docs: Bm25Doc[], query: string, limit = 50): Bm25Hit[] {
  const q = [...new Set(tokenize(query))]
  if (q.length === 0 || docs.length === 0) return []
  const k1 = 1.4
  const b = 0.75
  const avg = docs.reduce((s, d) => s + d.tokens.length, 0) / docs.length || 1
  const df = new Map<string, number>()
  const tfs = docs.map((d) => {
    const tf = new Map<string, number>()
    for (const t of d.tokens) tf.set(t, (tf.get(t) ?? 0) + 1)
    for (const term of q) if (tf.has(term)) df.set(term, (df.get(term) ?? 0) + 1)
    return tf
  })
  const N = docs.length
  const hits: Bm25Hit[] = []
  docs.forEach((d, i) => {
    let raw = 0
    let matched = 0
    for (const term of q) {
      const f = tfs[i].get(term)
      if (!f) continue
      matched++
      const n = df.get(term) ?? 0
      const idf = Math.log(1 + (N - n + 0.5) / (n + 0.5))
      raw += idf * ((f * (k1 + 1)) / (f + k1 * (1 - b + (b * d.tokens.length) / avg)))
    }
    if (raw > 0) hits.push({ id: d.id, raw, matched })
  })
  return hits.sort((a, b2) => b2.raw - a.raw).slice(0, limit)
}

// Squash to 0-1 so keyword scores can sit in the same result shape as cosine scores.
export const normaliseBm25 = (raw: number, queryTerms: number): number => Math.min(1, raw / (raw + 2 + queryTerms))
