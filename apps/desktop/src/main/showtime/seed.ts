// The tour runs on the seeded demo profile. A real profile.md is NEVER overwritten without a backup: it is moved
// aside first, put back at the end (even after a crash, on the next start), and a missing profile is removed again.
import { copyFile, readFile, rename, rm, stat, writeFile } from 'node:fs/promises'
import path from 'node:path'

export const PROFILE_FILE = 'profile.md'
export const BACKUP_FILE = 'profile.md.showtime-backup'
export const NONE_MARKER = 'profile.md.showtime-none'

const exists = (p: string): Promise<boolean> =>
  stat(p).then(
    () => true,
    () => false,
  )

async function atomicWrite(file: string, text: string): Promise<void> {
  const tmp = `${file}.showtime-tmp`
  await writeFile(tmp, text, { mode: 0o600 })
  await rename(tmp, file)
}

export type RestoreResult = 'restored' | 'removed' | 'nothing'

// Puts the real profile back (or removes the seed when there was none). Safe to call at any time and more than once.
export async function restoreProfile(dir: string): Promise<RestoreResult> {
  const file = path.join(dir, PROFILE_FILE)
  const backup = path.join(dir, BACKUP_FILE)
  const none = path.join(dir, NONE_MARKER)
  if (await exists(backup)) {
    await rename(backup, file)
    await rm(none, { force: true })
    return 'restored'
  }
  if (await exists(none)) {
    await rm(file, { force: true })
    await rm(none, { force: true })
    return 'removed'
  }
  return 'nothing'
}

export interface SeedResult {
  recovered: RestoreResult
  backedUp: boolean
}

export async function seedProfile(dir: string, seed: string): Promise<SeedResult> {
  // A leftover backup from a crashed run is the real profile: restore it before backing anything up again.
  const recovered = await restoreProfile(dir)
  const file = path.join(dir, PROFILE_FILE)
  const backup = path.join(dir, BACKUP_FILE)
  let backedUp = false
  if (await exists(file)) {
    await copyFile(file, backup)
    backedUp = true
  } else {
    await writeFile(path.join(dir, NONE_MARKER), 'no profile existed before the walkthrough\n', { mode: 0o600 })
  }
  await atomicWrite(file, seed)
  return { recovered, backedUp }
}

export async function readIfExists(file: string): Promise<string | null> {
  try {
    return await readFile(file, 'utf8')
  } catch {
    return null
  }
}
