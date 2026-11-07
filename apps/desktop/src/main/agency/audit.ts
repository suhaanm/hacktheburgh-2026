// Adapted from farzaa/clicky (MIT) — hermes-clicky-plugin/audit_log.py (append-only JSONL, redact by default)
// Append-only audit of everything the assistant did or refused to do: time, tool, label or host, the decision, the outcome.
// Never screenshots, never typed text, never other screen content. File mode 0600, same file as the single-click flow
// (userData/actions.log), one JSON object per line.
import { appendFile, chmod, readFile } from 'node:fs/promises'
import path from 'node:path'

export type AuditDecision = 'allowed' | 'blocked' | 'declined' | 'stopped' | 'refused' | 'unavailable'

export interface AgencyAuditEntry {
  tool: 'open_for_me' | 'act_for_me'
  decision: AuditDecision
  ok: boolean
  code: string
  // Plain label of the target ("website", "Safari", "Click: Start call"). Truncated; sensitive-looking text is dropped.
  label?: string
  host?: string
  step?: number
  dryRun?: boolean
  // Set only when no confirmation click was needed because the owner had opted in and was away.
  approval?: 'auto-away'
  // The frontmost application (name only) when the entry was written: shows the task stayed in scope.
  app?: string
}

const SENSITIVE = /\b(password|passcode|token|api[_ -]?key|secret|private[_ -]?key|seed phrase|recovery phrase)\b|\bsk-[a-z0-9_-]{6,}|\bxox[baprs]-[a-z0-9-]+|\b(?:\d[ -]?){13,19}\b/i

export function redactLabel(value: string | undefined, max = 80): string | undefined {
  if (!value) return undefined
  const text = value.replace(/\s+/g, ' ').trim()
  if (!text) return undefined
  if (SENSITIVE.test(text)) return '[redacted]'
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}

export const auditFile = (userDataDir: string): string => path.join(userDataDir, 'actions.log')

export function auditLine(entry: AgencyAuditEntry, now: () => number = Date.now): string {
  return JSON.stringify({
    t: new Date(now()).toISOString(),
    tool: entry.tool,
    decision: entry.decision,
    ok: entry.ok,
    code: entry.code,
    ...(entry.label ? { label: redactLabel(entry.label) } : {}),
    ...(entry.host ? { host: entry.host.slice(0, 120) } : {}),
    ...(entry.step !== undefined ? { step: entry.step } : {}),
    ...(entry.dryRun ? { dryRun: true } : {}),
    ...(entry.approval ? { approval: entry.approval } : {}),
    ...(entry.app ? { app: redactLabel(entry.app, 40) } : {}),
  })
}

export async function appendAgencyAudit(userDataDir: string | null, entry: AgencyAuditEntry, now: () => number = Date.now): Promise<string | null> {
  if (!userDataDir) return null
  const file = auditFile(userDataDir)
  await appendFile(file, `${auditLine(entry, now)}\n`, { mode: 0o600 })
  await chmod(file, 0o600)
  return file
}

// The last line of the audit log (for the "what did you just do?" bubble and the showtime tour), or null.
export async function lastAuditLine(userDataDir: string | null): Promise<string | null> {
  if (!userDataDir) return null
  try {
    const text = await readFile(auditFile(userDataDir), 'utf8')
    const lines = text.split('\n').filter((l) => l.trim())
    return lines.length ? lines[lines.length - 1] : null
  } catch {
    return null
  }
}
