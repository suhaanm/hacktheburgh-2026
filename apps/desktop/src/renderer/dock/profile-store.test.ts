// The dock edits profile.md as text; this proves the real LearnerStore accepts those edits and keeps the learner's data.
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { levelEngine } from '../../main/teaching/levels'
import { PROFILE_FILE, TeachingLearnerStore } from '../../main/teaching/learner-store'
import { addLine, blankProfile, parseProfile, removeLines } from './profile'

let dir: string
beforeEach(() => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'alongside-profile-'))
})
afterEach(() => fs.rmSync(dir, { recursive: true, force: true }))

const make = (): TeachingLearnerStore =>
  new TeachingLearnerStore({ dir, now: () => Date.UTC(2026, 9, 31, 14), engine: levelEngine, getSettings: () => ({ demoMode: true, helpLevelMode: 'auto', carerSharing: false }) })

describe('dock profile edits against the real LearnerStore', () => {
  it('adds and forgets lines with the revision from the last read', async () => {
    const store = make()
    const first = await store.editMarkdown({ op: 'read' })
    const added = await store.editMarkdown({ op: 'write', content: addLine(first.content, 'goals', 'Send photos to my son'), revision: first.revision })
    expect(added.ok).toBe(true)
    const goals = parseProfile(added.content).find((s) => s.key === 'goals')!
    expect(goals.lines.map((l) => l.text)).toContain('Send photos to my son')
    expect(fs.readFileSync(path.join(dir, PROFILE_FILE), 'utf8')).toContain('Send photos to my son')

    const forgotten = await store.editMarkdown({ op: 'write', content: removeLines(added.content, goals.lines.map((l) => l.index)), revision: added.revision })
    expect(forgotten.ok).toBe(true)
    expect(forgotten.content).not.toContain('Send photos to my son')
  })

  it('rejects a stale revision, returns the latest, and writes nothing', async () => {
    const store = make()
    const first = await store.editMarkdown({ op: 'read' })
    await store.addNote('I find small text hard to read')
    const stale = await store.editMarkdown({ op: 'write', content: addLine(first.content, 'goals', 'My late edit'), revision: first.revision })
    expect(stale.ok).toBe(false)
    expect(stale.conflict).toBe(true)
    expect(stale.content).toContain('I find small text hard to read')
    expect(fs.readFileSync(path.join(dir, PROFILE_FILE), 'utf8')).not.toContain('My late edit')
  })

  it('"delete everything" writes a blank profile the store accepts', async () => {
    const store = make()
    await store.addNote('Call me Peggy')
    const current = await store.editMarkdown({ op: 'read' })
    const res = await store.editMarkdown({ op: 'write', content: blankProfile(), revision: current.revision })
    expect(res.ok).toBe(true)
    const after = await store.editMarkdown({ op: 'read' })
    expect(after.content).not.toContain('Call me Peggy')
    expect(store.snapshot().attempts).toEqual([])
  })
})
