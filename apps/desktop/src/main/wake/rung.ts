// The rung record: `<data dir>/rung_cleared.json`, written ONLY by the R1 command-line check (services/agent mac_check, after a passing real run
// with the owner present, postcondition read back). While it is absent, Knack's `do_it_for_me` never offers a click (`first_supervised_test_pending`).
// This file only READS it and fails closed: a missing, unreadable, malformed, wrong-rung or tampered record counts as "not cleared".
//
// Honest limit: the digest catches an edit by mistake, not by someone who can run code as the owner; that person can click for themselves.
// What the record clears: the targets listed in it (R1 clears TextEdit only). The sandbox is cleared by the same record. Nothing wider.
import { createHash } from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'

export interface RungRecord {
  schema: 1
  rung: 'R1'
  at: string
  targets: string[]
  postcondition: 'passed'
  real: true
  digest: string
}

export type RungReading = { cleared: true; targets: string[]; at: string } | { cleared: false; why: 'absent' | 'unreadable' | 'malformed' | 'wrong_rung' | 'not_passed' | 'digest' }

/** The digest both writers use: sha256 over the fields, in this order, joined by a bar. */
export function rungDigest(r: Pick<RungRecord, 'schema' | 'rung' | 'at' | 'targets' | 'postcondition' | 'real'>): string {
  return createHash('sha256').update(`${r.schema}|${r.rung}|${r.at}|${[...r.targets].sort().join(',')}|${r.postcondition}|${r.real}`).digest('hex')
}

export function readRung(dataDir: string, read: (file: string) => string = (f) => fs.readFileSync(f, 'utf8')): RungReading {
  let text: string
  try {
    text = read(path.join(dataDir, 'rung_cleared.json'))
  } catch (err) {
    return { cleared: false, why: (err as NodeJS.ErrnoException)?.code === 'ENOENT' ? 'absent' : 'unreadable' }
  }
  let v: unknown
  try {
    v = JSON.parse(text)
  } catch {
    return { cleared: false, why: 'malformed' }
  }
  if (typeof v !== 'object' || v === null) return { cleared: false, why: 'malformed' }
  const o = v as Record<string, unknown>
  if (o.schema !== 1 || typeof o.at !== 'string' || !Array.isArray(o.targets) || !o.targets.every((t) => typeof t === 'string') || typeof o.digest !== 'string') return { cleared: false, why: 'malformed' }
  if (o.rung !== 'R1') return { cleared: false, why: 'wrong_rung' }
  if (o.postcondition !== 'passed' || o.real !== true) return { cleared: false, why: 'not_passed' }
  const rec = { schema: 1 as const, rung: 'R1' as const, at: o.at, targets: o.targets as string[], postcondition: 'passed' as const, real: true as const }
  if (rungDigest(rec) !== o.digest) return { cleared: false, why: 'digest' }
  return { cleared: true, targets: [...rec.targets], at: rec.at }
}
