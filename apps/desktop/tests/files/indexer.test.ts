import fs from 'node:fs'
import path from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { EmbedError } from '../../src/main/files/embed'
import { runIndex, type IndexerDeps } from '../../src/main/files/indexer'
import { IndexStore } from '../../src/main/files/store'
import { fakeEmbedder, fakeExtractor, sandbox, type Sandbox } from './helpers'

let sb: Sandbox
afterEach(() => sb?.cleanup())

function deps(over: Partial<IndexerDeps> = {}): IndexerDeps {
  return { store: new IndexStore(sb.userData), embedder: fakeEmbedder(), extractor: null, home: sb.home, ...over }
}

describe('runIndex', () => {
  it('indexes text files, redacts before embedding, and stores chunks plus vectors', async () => {
    sb = sandbox()
    sb.write('letter.txt', 'Your appointment is on Wednesday. Bank card 4417 0293 8851 7720\nWifi password: hunter2\nBring your glasses please.')
    const d = deps()
    const res = await runIndex([sb.docs], d)
    expect(res.changed).toBe(1)
    const stored = d.store.load()
    expect(stored).not.toBeNull()
    const all = (stored?.chunks ?? []).map((c) => c.text).join(' ')
    expect(all).toContain('appointment')
    expect(all).not.toMatch(/4417|hunter2|password/i)
    expect(stored?.chunks.every((c) => c.v === 1)).toBe(true)
    expect(stored?.vectors.length).toBe((stored?.chunks.length ?? 0) * (stored?.dims ?? 0))
  })

  it('drops an index built with older redaction rules, so stale snippets are never served', async () => {
    sb = sandbox()
    sb.write('bank.txt', 'Statement. Account number: 87654321 and sort code 12-34-56. Thank you for banking with us.')
    const d = deps()
    await runIndex([sb.docs], d)
    const metaPath = path.join(sb.userData, 'files-index', 'meta.json')
    const meta = JSON.parse(fs.readFileSync(metaPath, 'utf8')) as Record<string, unknown>
    expect(JSON.stringify(meta)).not.toMatch(/87654321|12-34-56/)
    expect(d.store.load()).not.toBeNull()
    delete meta.redactVersion
    meta.chunks = [{ ...(meta.chunks as object[])[0], text: 'Account number: 87654321' }]
    fs.writeFileSync(metaPath, JSON.stringify(meta))
    expect(d.store.load()).toBeNull()
    expect(fs.existsSync(metaPath)).toBe(false)
  })

  it('is incremental: unchanged files are not re-read or re-embedded; changed and deleted files are handled', async () => {
    sb = sandbox()
    const a = sb.write('a.txt', 'Alpha note about gardening tools and the shed.')
    sb.write('b.txt', 'Beta note about the electricity bill and payments.')
    const emb = fakeEmbedder()
    const d = deps({ embedder: emb })
    await runIndex([sb.docs], d)
    expect(emb.docTexts).toBe(2)

    const again = await runIndex([sb.docs], d)
    expect(again.changed).toBe(0)
    expect(again.unchanged).toBe(2)
    expect(emb.docTexts).toBe(2)

    fs.writeFileSync(a, 'Alpha note, now rewritten to talk about the greenhouse instead.')
    fs.utimesSync(a, new Date(), new Date(Date.now() + 5000))
    const third = await runIndex([sb.docs], d)
    expect(third.changed).toBe(1)
    expect(emb.docTexts).toBe(3)
    const text = (d.store.load()?.chunks ?? []).map((c) => c.text).join(' ')
    expect(text).toContain('greenhouse')
    expect(text).not.toContain('gardening')

    fs.rmSync(path.join(sb.docs, 'b.txt'))
    const fourth = await runIndex([sb.docs], d)
    expect(fourth.removed).toBe(1)
    expect(Object.keys(d.store.load()?.files ?? {})).toEqual([a])
  })

  it('keeps text for keyword search when embeddings fail, then re-embeds on the next run', async () => {
    sb = sandbox()
    sb.write('a.txt', 'Doctor appointment letter for Wednesday morning.')
    const emb = fakeEmbedder()
    emb.failWith = new EmbedError('network', 'offline')
    const d = deps({ embedder: emb })
    const first = await runIndex([sb.docs], d)
    expect(first.error).toMatch(/internet/i)
    const stored = d.store.load()
    expect(stored?.chunks).toHaveLength(1)
    expect(stored?.chunks[0].v).toBe(0)
    expect(Object.values(stored?.files ?? {})[0].status).toBe('unembedded')

    emb.failWith = null
    const second = await runIndex([sb.docs], d)
    expect(second.changed).toBe(1)
    expect(d.store.load()?.chunks[0].v).toBe(1)
  })

  it('stops embedding after the first failure instead of hammering the API', async () => {
    sb = sandbox()
    for (let i = 0; i < 6; i++) sb.write(`f${i}.txt`, `Note number ${i} with some words in it.`)
    const emb = fakeEmbedder()
    emb.failWith = new EmbedError('rate_limit', 'busy')
    await runIndex([sb.docs], deps({ embedder: emb }), { concurrency: 1 })
    expect(emb.docCalls).toBe(1)
  })

  it('works with no embedder at all (keyword only)', async () => {
    sb = sandbox()
    sb.write('a.txt', 'Plain note about banana bread and butter.')
    const d = deps({ embedder: null })
    const res = await runIndex([sb.docs], d)
    expect(res.changed).toBe(1)
    expect(d.store.load()?.chunks[0].v).toBe(0)
  })

  it('caps PDF and image reads at 25 per run and picks the rest up next time', async () => {
    sb = sandbox()
    for (let i = 0; i < 30; i++) sb.write(`scan${i}.pdf`, Buffer.from(`%PDF-1.4 fake ${i}`))
    const ex = fakeExtractor()
    const d = deps({ extractor: ex })
    const first = await runIndex([sb.docs], d)
    expect(ex.calls).toBe(25)
    expect(first.geminiDeferred).toBe(5)
    expect(Object.values(d.store.load()?.files ?? {}).filter((f) => f.reason === 'deferred')).toHaveLength(5)
    const second = await runIndex([sb.docs], d)
    expect(ex.calls).toBe(30)
    expect(second.geminiDeferred).toBe(0)
    expect(Object.values(d.store.load()?.files ?? {}).every((f) => f.status === 'ok')).toBe(true)
  })

  it('defers PDFs and images when there is no extractor (offline) instead of dropping them', async () => {
    sb = sandbox()
    sb.write('scan.pdf', Buffer.from('%PDF-1.4 fake'))
    const d = deps({ extractor: null })
    const res = await runIndex([sb.docs], d)
    expect(res.geminiDeferred).toBe(1)
    const ex = fakeExtractor()
    await runIndex([sb.docs], deps({ extractor: ex }))
    expect(ex.calls).toBe(1)
  })

  it('re-embeds everything when the embedding model changes', async () => {
    sb = sandbox()
    sb.write('a.txt', 'Some words about the doctor and the surgery.')
    await runIndex([sb.docs], deps({ embedder: fakeEmbedder('model-one') }))
    const emb2 = fakeEmbedder('model-two')
    await runIndex([sb.docs], deps({ embedder: emb2 }))
    expect(emb2.docTexts).toBe(1)
    expect(new IndexStore(sb.userData).load()?.embedModel).toBe('model-two')
  })

  it('re-checks consent on every run: a folder that is now too broad is skipped and never read', async () => {
    sb = sandbox()
    sb.write('a.txt', 'Some words about the doctor and the surgery.')
    const d = deps()
    const res = await runIndex([sb.home, sb.docs], d)
    expect(res.rejectedFolders).toEqual([sb.home])
    expect(Object.keys(d.store.load()?.files ?? {})).toHaveLength(1)
  })

  it('stops launching new work when aborted and still saves what it has', async () => {
    sb = sandbox()
    for (let i = 0; i < 8; i++) sb.write(`f${i}.txt`, `Note number ${i} with some words in it.`)
    const ctl = new AbortController()
    const d = deps()
    const res = await runIndex([sb.docs], d, { concurrency: 1, signal: ctl.signal, onProgress: (p) => p.done === 2 && ctl.abort() })
    expect(res.aborted).toBe(true)
    expect(Object.keys(d.store.load()?.files ?? {}).length).toBeLessThan(8)
  })

  it('reports progress', async () => {
    sb = sandbox()
    for (let i = 0; i < 3; i++) sb.write(`f${i}.txt`, `Note number ${i} with some words in it.`)
    const seen: Array<[number, number]> = []
    await runIndex([sb.docs], deps(), { onProgress: (p) => seen.push([p.done, p.total]) })
    expect(seen[0]).toEqual([0, 3])
    expect(seen.at(-1)).toEqual([3, 3])
  })
})

describe('IndexStore', () => {
  it('writes with owner-only permissions and replaces atomically, leaving no temp or stale files', async () => {
    sb = sandbox()
    sb.write('a.txt', 'Words about the doctor and the surgery visit.')
    const d = deps()
    await runIndex([sb.docs], d)
    await runIndex([sb.docs], deps())
    const dir = d.store.dir
    expect(fs.statSync(dir).mode & 0o777).toBe(0o700)
    const files = fs.readdirSync(dir)
    expect(files.filter((f) => f.startsWith('vectors-'))).toHaveLength(1)
    expect(files.some((f) => f.includes('.tmp-'))).toBe(false)
    for (const f of files) expect(fs.statSync(path.join(dir, f)).mode & 0o777).toBe(0o600)
  })

  it('refuses a torn index (vectors file the wrong size) instead of returning garbage', async () => {
    sb = sandbox()
    sb.write('a.txt', 'Words about the doctor and the surgery visit.')
    const d = deps()
    await runIndex([sb.docs], d)
    const vec = fs.readdirSync(d.store.dir).find((f) => f.startsWith('vectors-')) as string
    fs.writeFileSync(path.join(d.store.dir, vec), Buffer.alloc(7))
    expect(d.store.load()).toBeNull()
  })

  it('clear() removes everything', async () => {
    sb = sandbox()
    sb.write('a.txt', 'Words about the doctor and the surgery visit.')
    const d = deps()
    await runIndex([sb.docs], d)
    d.store.clear()
    expect(fs.existsSync(d.store.dir)).toBe(false)
    expect(d.store.load()).toBeNull()
  })
})
