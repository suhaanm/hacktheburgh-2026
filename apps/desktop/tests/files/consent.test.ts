import fs from 'node:fs'
import path from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { checkFolder, scanFolders } from '../../src/main/files/consent'
import { sandbox, type Sandbox } from './helpers'

let sb: Sandbox
afterEach(() => sb?.cleanup())

describe('checkFolder (consent rules)', () => {
  it('accepts a normal folder inside home and returns its real path', () => {
    sb = sandbox()
    const r = checkFolder(sb.docs, { home: sb.home })
    expect(r).toEqual({ ok: true, real: sb.docs, name: 'Documents' })
  })

  it('rejects /, the home folder, and the folder that contains home', () => {
    sb = sandbox()
    for (const p of ['/', sb.home, path.dirname(sb.home), '/Users']) {
      const r = checkFolder(p, { home: sb.home })
      expect(r.ok, p).toBe(false)
    }
  })

  it('rejects system folders', () => {
    sb = sandbox()
    for (const p of ['/System', '/usr', '/etc', '/Library', '/Applications', '/bin']) {
      if (!fs.existsSync(p)) continue
      expect(checkFolder(p, { home: sb.home }).ok, p).toBe(false)
    }
  })

  it('rejects ~/Library, .ssh, hidden and keychain folders, browser profile paths', () => {
    sb = sandbox()
    const library = path.join(sb.home, 'Library')
    fs.mkdirSync(path.join(sb.home, 'Library', 'Keychains'), { recursive: true })
    fs.mkdirSync(path.join(sb.docs, '.hidden'), { recursive: true })
    fs.mkdirSync(path.join(sb.docs, 'Keychains'), { recursive: true })
    fs.mkdirSync(path.join(sb.home, 'Google', 'Chrome', 'Profile 1'), { recursive: true })
    for (const p of [library, path.join(library, 'Cookies'), path.join(library, 'Keychains'), path.join(sb.home, '.ssh'), path.join(sb.docs, '.hidden'), path.join(sb.docs, 'Keychains'), path.join(sb.home, 'Google', 'Chrome', 'Profile 1')]) {
      expect(checkFolder(p, { home: sb.home }).ok, p).toBe(false)
    }
  })

  it('resolves symlinks first: a link to a rejected folder is rejected', () => {
    sb = sandbox()
    const link = path.join(sb.docs, 'innocent-link')
    fs.symlinkSync(path.join(sb.home, '.ssh'), link)
    expect(checkFolder(link, { home: sb.home }).ok).toBe(false)
    const toHome = path.join(sb.root, 'to-home')
    fs.symlinkSync(sb.home, toHome)
    expect(checkFolder(toHome, { home: sb.home }).ok).toBe(false)
  })

  it('rejects files, missing paths, relative paths and odd input', () => {
    sb = sandbox()
    const file = sb.write('a.txt', 'hello world, this is a file')
    for (const p of [file, path.join(sb.docs, 'nope'), 'Documents', '', 'x\0y']) expect(checkFolder(p, { home: sb.home }).ok, p).toBe(false)
  })

  it('never lets the index folder itself be chosen', () => {
    sb = sandbox()
    const idx = path.join(sb.userData, 'files-index')
    fs.mkdirSync(idx, { recursive: true })
    expect(checkFolder(sb.userData, { home: sb.root, extraBlocked: [idx] }).ok).toBe(false)
  })
})

describe('scanFolders', () => {
  it('skips hidden files, symlinks, secrets by name, unsupported types, empty files and files over the size cap', () => {
    sb = sandbox()
    sb.write('keep.txt', 'a normal note about the garden')
    sb.write('.hidden.txt', 'hidden')
    sb.write('.env', 'API_KEY=abc')
    sb.write('passwords.txt', 'bank: hunter2')
    sb.write('secret-notes.md', 'my secret')
    sb.write('photo.heic', 'unsupported')
    sb.write('empty.txt', '')
    sb.write('big.txt', 'x'.repeat(2000))
    sb.write('sub/inner.md', '# inner note about recipes')
    sb.write('.git/config.txt', 'hidden dir content')
    fs.symlinkSync(path.join(sb.docs, 'keep.txt'), path.join(sb.docs, 'link.txt'))
    fs.symlinkSync(sb.home, path.join(sb.docs, 'linkdir'))
    const res = scanFolders([sb.docs], { maxFileBytes: 1000 })
    expect(res.files.map((f) => f.rel).sort()).toEqual(['keep.txt', path.join('sub', 'inner.md')])
    expect(res.skipped.too_big).toBe(1)
    expect(res.skipped.sensitive_name).toBe(2)
    expect(res.skipped.empty).toBe(1)
    expect(res.skipped.hidden).toBeGreaterThanOrEqual(3)
  })

  it('stops at the file cap and the total size cap and says so', () => {
    sb = sandbox()
    for (let i = 0; i < 10; i++) sb.write(`f${i}.txt`, 'a'.repeat(100))
    const byCount = scanFolders([sb.docs], { maxFiles: 4 })
    expect(byCount.files).toHaveLength(4)
    expect(byCount.truncated).toBe(true)
    const byBytes = scanFolders([sb.docs], { maxTotalBytes: 350 })
    expect(byBytes.files).toHaveLength(3)
    expect(byBytes.truncated).toBe(true)
  })

  it('is breadth-first so shallow files win when a cap is hit', () => {
    sb = sandbox()
    sb.write('deep/er/est/z.txt', 'deep file text here')
    sb.write('top.txt', 'top file text here')
    const res = scanFolders([sb.docs], { maxFiles: 1 })
    expect(res.files[0].rel).toBe('top.txt')
  })

  it('never descends into the index folder', () => {
    sb = sandbox()
    const idx = path.join(sb.docs, 'files-index')
    sb.write('files-index/meta.txt', 'index internals')
    sb.write('real.txt', 'a real document here')
    const res = scanFolders([sb.docs], { exclude: [idx] })
    expect(res.files.map((f) => f.rel)).toEqual(['real.txt'])
  })
})
