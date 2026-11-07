import { mkdtemp, readFile, rm, stat, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { BACKUP_FILE, NONE_MARKER, PROFILE_FILE, restoreProfile, seedProfile } from './seed'

let dir = ''
beforeEach(async () => {
  dir = await mkdtemp(path.join(os.tmpdir(), 'showtime-seed-'))
})
afterEach(async () => {
  await rm(dir, { recursive: true, force: true })
})
const read = (f: string): Promise<string> => readFile(path.join(dir, f), 'utf8')
const has = (f: string): Promise<boolean> => stat(path.join(dir, f)).then(() => true, () => false)

describe('profile seeding', () => {
  it('backs up a real profile, seeds, and restores it byte for byte', async () => {
    await writeFile(path.join(dir, PROFILE_FILE), '# real profile\n- my own line\n')
    const r = await seedProfile(dir, '# demo seed\n')
    expect(r.backedUp).toBe(true)
    expect(await read(PROFILE_FILE)).toBe('# demo seed\n')
    expect(await read(BACKUP_FILE)).toBe('# real profile\n- my own line\n')
    expect(await restoreProfile(dir)).toBe('restored')
    expect(await read(PROFILE_FILE)).toBe('# real profile\n- my own line\n')
    expect(await has(BACKUP_FILE)).toBe(false)
  })

  it('removes the seed again when there was no profile', async () => {
    await seedProfile(dir, '# demo seed\n')
    expect(await has(NONE_MARKER)).toBe(true)
    expect(await restoreProfile(dir)).toBe('removed')
    expect(await has(PROFILE_FILE)).toBe(false)
  })

  it('after a crash the next run restores the real profile first and never backs up the seed over it', async () => {
    await writeFile(path.join(dir, PROFILE_FILE), '# real\n')
    await seedProfile(dir, '# demo seed\n')
    // crash: no restore. Next start:
    const second = await seedProfile(dir, '# demo seed\n')
    expect(second.recovered).toBe('restored')
    expect(await read(BACKUP_FILE)).toBe('# real\n')
    await restoreProfile(dir)
    expect(await read(PROFILE_FILE)).toBe('# real\n')
  })

  it('restore with nothing to restore is a no-op', async () => {
    expect(await restoreProfile(dir)).toBe('nothing')
  })
})
