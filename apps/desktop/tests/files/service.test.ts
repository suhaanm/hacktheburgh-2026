import fs from 'node:fs'
import path from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { FILE_DATA_NOTICE } from '../../src/shared/files'
import { fakeEmbedder, fakeExtractor, makeService, sandbox, type Sandbox } from './helpers'

let sb: Sandbox
afterEach(() => sb?.cleanup())

const settle = async (service: { status(): { indexing: boolean } }) => {
  for (let i = 0; i < 200 && service.status().indexing; i++) await new Promise((r) => setTimeout(r, 10))
  await new Promise((r) => setTimeout(r, 20))
}

function setup(over: Parameters<typeof makeService>[1] = {}) {
  sb = sandbox()
  sb.write('Health/GP letter.txt', 'Riverside Surgery appointment with Dr Okafor on Wednesday at 10:30.')
  sb.write('Recipes/banana.md', 'Banana bread: mash ripe bananas, add butter and flour.')
  return makeService(sb, over)
}

describe('FilesService: consent and scope', () => {
  it('is off by default: no folders, search refuses and nothing is indexed', async () => {
    const { ctx, service } = setup()
    expect(ctx.settings.get().filesEnabled).toBe(false)
    expect(ctx.settings.get().fileFolders).toEqual([])
    const r = await service.search('doctor')
    expect(r).toMatchObject({ ok: false, reason: 'files_off', results: [], data_notice: FILE_DATA_NOTICE })
    expect(fs.existsSync(path.join(sb.userData, 'files-index'))).toBe(false)
  })

  it('addFolder rejects broad, system and private folders and adds nothing', async () => {
    const { ctx, service } = setup()
    for (const p of [sb.home, '/', path.join(sb.home, 'Library'), path.join(sb.home, '.ssh')]) {
      const r = await service.addFolder(p)
      expect(r.ok, p).toBe(false)
      expect(r.error).toBeTruthy()
    }
    expect(ctx.settings.get().fileFolders).toEqual([])
  })

  it('addFolder stores the REAL path, de-duplicates, and replaces children when a parent is added', async () => {
    const { ctx, service } = setup()
    const link = path.join(sb.root, 'docs-link')
    fs.symlinkSync(sb.docs, link)
    const first = await service.addFolder(path.join(sb.docs, 'Health'))
    expect(first).toMatchObject({ ok: true, path: path.join(sb.docs, 'Health'), name: 'Health' })
    expect((await service.addFolder(path.join(sb.docs, 'Health'))).ok).toBe(false)
    expect((await service.addFolder(link)).ok).toBe(true)
    expect(ctx.settings.get().fileFolders).toEqual([sb.docs])
  })

  it('a tampered setting (home folder) is ignored: nothing is read and status shows no indexed files', async () => {
    const { ctx, service } = setup()
    ctx.settings.patch({ fileFolders: [sb.home], filesEnabled: true })
    await settle(service)
    expect(service.status().indexedFiles).toBe(0)
    expect(service.status().folders).toEqual([])
    expect((await service.search('doctor')).reason).toBe('no_folders')
  })

  it('refused folders (/, home, .ssh) are never listed in status, but a folder that went missing still is', async () => {
    const { ctx, service } = setup()
    await service.addFolder(sb.docs)
    const gone = path.join(sb.root, 'gone')
    ctx.settings.patch({ fileFolders: [sb.docs, '/', sb.home, path.join(sb.home, '.ssh'), gone] })
    expect(service.status().folders.map((f) => f.path)).toEqual([sb.docs, gone])
  })

  it('indexing starts when the switch and a folder are set, and search then works', async () => {
    const { ctx, service } = setup()
    await service.addFolder(sb.docs)
    expect(service.status().indexedFiles).toBe(0)
    ctx.settings.patch({ filesEnabled: true })
    await settle(service)
    const st = service.status()
    expect(st.indexedFiles).toBe(2)
    expect(st.mode).toBe('semantic')
    expect(st.lastIndexedAt).toBeGreaterThan(0)
    const r = await service.search('doctor appointment at the surgery')
    expect(r.ok).toBe(true)
    expect(r.mode).toBe('semantic')
    expect(r.results[0].relPath).toBe(path.join('Health', 'GP letter.txt'))
    expect(r.results.length).toBeLessThanOrEqual(3)
    expect(r.data_notice).toBe(FILE_DATA_NOTICE)
  })

  it('publishes progress and counts into state', async () => {
    const { ctx, service } = setup()
    await service.addFolder(sb.docs)
    ctx.settings.patch({ filesEnabled: true })
    await settle(service)
    const last = ctx.patches.at(-1) as { files: { indexedFiles: number; indexing: boolean } }
    expect(last.files.indexedFiles).toBe(2)
    expect(last.files.indexing).toBe(false)
  })

  it('removeFolder drops that folder from the index immediately and from search', async () => {
    const { ctx, service } = setup()
    await service.addFolder(path.join(sb.docs, 'Health'))
    await service.addFolder(path.join(sb.docs, 'Recipes'))
    ctx.settings.patch({ filesEnabled: true })
    await settle(service)
    expect(service.status().indexedFiles).toBe(2)
    await service.removeFolder(path.join(sb.docs, 'Health'))
    expect(service.status().indexedFiles).toBe(1)
    const r = await service.search('doctor appointment surgery')
    expect(r.results.every((h) => !h.relPath.includes('GP letter'))).toBe(true)
    await service.removeFolder(path.join(sb.docs, 'Recipes'))
    expect(fs.existsSync(path.join(sb.userData, 'files-index'))).toBe(false)
  })

  it('deleteIndex removes everything it learned but keeps the folders and the switch', async () => {
    const { ctx, service } = setup()
    await service.addFolder(sb.docs)
    ctx.settings.patch({ filesEnabled: true })
    await settle(service)
    expect(fs.existsSync(path.join(sb.userData, 'files-index'))).toBe(true)
    const st = await service.deleteIndex()
    expect(fs.existsSync(path.join(sb.userData, 'files-index'))).toBe(false)
    expect(st.indexedFiles).toBe(0)
    expect(st.mode).toBe('none')
    expect(ctx.settings.get().fileFolders).toEqual([sb.docs])
    expect((await service.search('doctor')).reason).toBe('not_indexed')
  })

  it('switching off stops searching but keeps the index until it is deleted', async () => {
    const { ctx, service } = setup()
    await service.addFolder(sb.docs)
    ctx.settings.patch({ filesEnabled: true })
    await settle(service)
    ctx.settings.patch({ filesEnabled: false })
    expect((await service.search('doctor')).reason).toBe('files_off')
    expect(fs.existsSync(path.join(sb.userData, 'files-index'))).toBe(true)
  })

  it('resolveIndexedPath only vouches for indexed files in consented folders', async () => {
    const { ctx, service } = setup()
    const secret = sb.write('Elsewhere/secret.txt', 'not in a chosen folder at all', sb.home)
    await service.addFolder(sb.docs)
    ctx.settings.patch({ filesEnabled: true })
    await settle(service)
    const indexed = path.join(sb.docs, 'Health', 'GP letter.txt')
    expect(service.resolveIndexedPath(indexed)).toBe(indexed)
    expect(service.resolveIndexedPath(secret)).toBeNull()
    expect(service.resolveIndexedPath(path.join(sb.docs, 'Health', '..', '..', 'Elsewhere', 'secret.txt'))).toBeNull()
    expect(service.resolveIndexedPath('relative/path.txt')).toBeNull()
    expect(service.resolveIndexedPath(path.join(sb.docs, 'nope.txt'))).toBeNull()
    const link = path.join(sb.docs, 'sneaky.txt')
    fs.symlinkSync(secret, link)
    expect(service.resolveIndexedPath(link)).toBeNull()
    ctx.settings.patch({ filesEnabled: false })
    expect(service.resolveIndexedPath(indexed)).toBeNull()
  })

  it('rate-limits searches so a model cannot enumerate the index by looping', async () => {
    const { ctx, service } = setup({ searchesPerMinute: 3 })
    await service.addFolder(sb.docs)
    ctx.settings.patch({ filesEnabled: true })
    await settle(service)
    for (let i = 0; i < 3; i++) expect((await service.search(`banana ${i}`)).reason).not.toBe('rate_limited')
    expect((await service.search('banana again')).reason).toBe('rate_limited')
  })

  it('handles an empty query and a very long query', async () => {
    const { ctx, service } = setup()
    await service.addFolder(sb.docs)
    ctx.settings.patch({ filesEnabled: true })
    await settle(service)
    expect((await service.search('   ')).reason).toBe('empty_query')
    expect((await service.search('banana '.repeat(500))).results.length).toBeLessThanOrEqual(3)
  })

  it('falls back to keyword search, flagged, when there is no embedder', async () => {
    const { ctx, service } = setup({ embedder: null })
    await service.addFolder(sb.docs)
    ctx.settings.patch({ filesEnabled: true })
    await settle(service)
    expect(service.status().mode).toBe('keyword')
    const r = await service.search('banana bread')
    expect(r.mode).toBe('keyword')
    expect(r.results[0].name).toBe('banana.md')
  })

  it('reads PDFs and images through the extractor (store:false path) and makes them searchable', async () => {
    const ex = fakeExtractor((f) => (f.endsWith('scan.pdf') ? 'Letter from the council about parking permits and the renewal date.' : null))
    const { ctx, service } = setup({ extractor: ex })
    sb.write('scan.pdf', Buffer.from('%PDF-1.4 fake'))
    sb.write('photo.png', Buffer.from('fakepng'))
    await service.addFolder(sb.docs)
    ctx.settings.patch({ filesEnabled: true })
    await settle(service)
    expect(ex.calls).toBe(2)
    const r = await service.search('council parking permit renewal')
    expect(r.results[0].name).toBe('scan.pdf')
  })

  it('refresh after editing a file picks up the change', async () => {
    const emb = fakeEmbedder()
    const { ctx, service } = setup({ embedder: emb })
    await service.addFolder(sb.docs)
    ctx.settings.patch({ filesEnabled: true })
    await settle(service)
    const f = path.join(sb.docs, 'Recipes', 'banana.md')
    fs.writeFileSync(f, 'Now this file is about the greenhouse tomatoes and watering schedule.')
    fs.utimesSync(f, new Date(), new Date(Date.now() + 5000))
    await service.reindex()
    expect((await service.search('greenhouse tomatoes watering')).results[0].name).toBe('banana.md')
  })
})
