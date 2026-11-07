// The Swift matcher (native/knack-wake/Matcher.swift) must agree with matching.ts on every string of the corpus, in both modes (settled and partial).
// It compiles the matcher with a tiny stdin harness that imports NO audio or speech framework and opens no device, then feeds it offline strings.
// Skipped where there is no Swift compiler (not a Mac). Takes a few seconds to compile.
import { execFileSync, spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { NEGATIVES_DEV, POSITIVES_DEV } from './corpus-dev'
import { NEGATIVES_HELDOUT, POSITIVES_HELDOUT } from './corpus-heldout'
import { matchWake } from './matching'

const haveSwiftc = ((): boolean => {
  if (process.platform !== 'darwin') return false
  try {
    execFileSync('swiftc', ['--version'], { stdio: 'ignore' })
    return true
  } catch {
    return false
  }
})()

const HOSTILE = ['hey ' + 'knack '.repeat(50), 'HEY\tKNACK', "hey' knack'", 'hey‮knack', 'hey knacḱ', 'HÉY knack', 'hey\nknack', 'hey. knack', 'hey, nack', 'Hey knock, can you', '', ' ', 'hey', "hey knock what's up", 'hey nack where’s the tab']

describe.skipIf(!haveSwiftc)('Swift matcher parity with matching.ts', () => {
  it('gives the same verdict and variant on the whole corpus in both modes', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'wake-parity-'))
    const here = path.resolve(__dirname, '../../..', 'native/knack-wake')
    const bin = path.join(dir, 'matcher-test')
    execFileSync('swiftc', ['-O', '-swift-version', '5', path.join(here, 'Matcher.swift'), path.join(here, 'matcher-test/main.swift'), '-o', bin], { stdio: 'ignore', timeout: 240_000 })
    const strings = [...NEGATIVES_DEV, ...NEGATIVES_HELDOUT, ...POSITIVES_DEV, ...POSITIVES_HELDOUT, ...HOSTILE]
    const lines: string[] = []
    const expected: string[] = []
    for (const s of strings) {
      for (const settled of [true, false]) {
        lines.push(`${settled ? 'S' : 'P'}\t${s.replace(/[\n\r\t]/g, ' ')}`)
        const m = matchWake(s.replace(/[\n\r\t]/g, ' '), { settled })
        expected.push(m.variant ? `${m.verdict}:${m.variant}` : m.verdict)
      }
    }
    const r = spawnSync(bin, [], { input: lines.join('\n') + '\n', encoding: 'utf8', maxBuffer: 16 * 1024 * 1024 })
    expect(r.status).toBe(0)
    const got = r.stdout.trimEnd().split('\n')
    expect(got).toHaveLength(expected.length)
    const diffs = got.map((g, i) => (g === expected[i] ? null : `${lines[i]} => swift ${g}, ts ${expected[i]}`)).filter((x) => x !== null)
    expect(diffs).toEqual([])
    fs.rmSync(dir, { recursive: true, force: true })
  }, 300_000)
})
