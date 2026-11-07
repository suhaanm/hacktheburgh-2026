import { mkdirSync, mkdtempSync, realpathSync, symlinkSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { checkPath } from '../../src/main/agency/policy'

// A shared folder with a symlink inside it that points outside (or at a secret) must not be a way out.
function layout() {
  const base = realpathSync(mkdtempSync(path.join(os.tmpdir(), 'agency-link-')))
  const shared = path.join(base, 'shared')
  const outside = path.join(base, 'outside')
  mkdirSync(shared)
  mkdirSync(outside)
  mkdirSync(path.join(base, '.ssh'))
  writeFileSync(path.join(shared, 'recipe.txt'), 'x')
  writeFileSync(path.join(outside, 'diary.txt'), 'x')
  writeFileSync(path.join(base, '.ssh', 'id_rsa'), 'x')
  symlinkSync(outside, path.join(shared, 'escape'))
  symlinkSync(path.join(outside, 'diary.txt'), path.join(shared, 'diary-link.txt'))
  symlinkSync(path.join(base, '.ssh', 'id_rsa'), path.join(shared, 'notes.txt'))
  symlinkSync(path.join(shared, 'recipe.txt'), path.join(shared, 'recipe-alias.txt'))
  // the shared folder itself reached through a symlink
  symlinkSync(shared, path.join(base, 'shortcut'))
  return { base, shared }
}

describe('checkPath and symlinks', () => {
  it('a normal file in the shared folder is fine, also through a link that stays inside', () => {
    const { shared } = layout()
    expect(checkPath(path.join(shared, 'recipe.txt'), [shared], '/nowhere').ok).toBe(true)
    expect(checkPath(path.join(shared, 'recipe-alias.txt'), [shared], '/nowhere').ok).toBe(true)
  })

  it('a symlinked folder that leads outside is refused', () => {
    const { shared } = layout()
    expect(checkPath(path.join(shared, 'escape', 'diary.txt'), [shared], '/nowhere').ok).toBe(false)
  })

  it('a symlinked file that leads outside or at a sensitive file is refused', () => {
    const { shared } = layout()
    expect(checkPath(path.join(shared, 'diary-link.txt'), [shared], '/nowhere').ok).toBe(false)
    expect(checkPath(path.join(shared, 'notes.txt'), [shared], '/nowhere').ok).toBe(false)
  })

  it('a not-yet-existing file below a symlinked folder is judged by where the folder really goes', () => {
    const { shared } = layout()
    expect(checkPath(path.join(shared, 'escape', 'new-file.txt'), [shared], '/nowhere').ok).toBe(false)
    expect(checkPath(path.join(shared, 'new-file.txt'), [shared], '/nowhere').ok).toBe(true)
  })

  it('a shared folder given through a symlink still works for files inside it', () => {
    const { base, shared } = layout()
    expect(checkPath(path.join(shared, 'recipe.txt'), [path.join(base, 'shortcut')], '/nowhere').ok).toBe(true)
    expect(checkPath(path.join(base, 'shortcut', 'recipe.txt'), [shared], '/nowhere').ok).toBe(true)
  })
})
