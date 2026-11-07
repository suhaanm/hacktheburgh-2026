// Append-only audit of every "do it for me" attempt: time, element label, whether the learner approved, whether the
// click happened. No screenshots, no typed text, no other screen content. File mode 0600.
import { appendFile, chmod } from 'node:fs/promises'
import path from 'node:path'

export interface AuditEntry {
  label: string
  approved: boolean
  ok: boolean
  code: string
  dryRun?: boolean
}

export async function appendAudit(userDataDir: string | null, entry: AuditEntry, now: () => number = Date.now): Promise<string | null> {
  if (!userDataDir) return null
  const file = path.join(userDataDir, 'actions.log')
  const line = JSON.stringify({ t: new Date(now()).toISOString(), label: entry.label.slice(0, 80), approved: entry.approved, ok: entry.ok, code: entry.code, ...(entry.dryRun ? { dryRun: true } : {}) })
  await appendFile(file, `${line}\n`, { mode: 0o600 })
  await chmod(file, 0o600)
  return file
}
