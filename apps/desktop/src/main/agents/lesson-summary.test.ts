import { describe, expect, it } from 'vitest'
import { createAgents } from './index'
import { buildCarerNote, writeExport } from './lesson-summary'
import { makeFakes, makeLearner, until } from './fakes.test-util'
import type { AttemptRecord } from '../../shared/protocol'

function attempt(over: Partial<AttemptRecord> = {}): AttemptRecord {
  return {
    id: 'a1', skillId: 'video_call', lessonId: 'l1', startedAt: 1_000, endedAt: 2_000, levelAtStart: 2, levelAtEnd: 3,
    completed: true, hintsUsed: 1, errors: 0, stalls: 0, safetyFlag: false, anxietyPhrase: false, teachBackScore: 0.9, confidence: 4, clean: true, ...over,
  }
}

async function runSummary(f: ReturnType<typeof makeFakes>) {
  const rt = createAgents(f.deps)
  await rt.spawn('lesson_summary', 'write a note for my daughter')
  await until(() => rt.list()[0]?.status !== 'running')
  return rt.list()[0]!
}

describe('lesson_summary agent', () => {
  it('refuses politely unless carer sharing is on, and writes nothing', async () => {
    const f = makeFakes({ carerSharing: false })
    f.set.learner = makeLearner({ attempts: [attempt()] })
    const chip = await runSummary(f)
    expect(chip.status).toBe('done')
    expect(chip.summary).toMatch(/Carer sharing is switched off/)
    expect(f.files.size).toBe(0)
  })

  it('writes a short markdown note under exports/ and returns the path', async () => {
    const f = makeFakes({ carerSharing: true })
    f.set.learner = makeLearner({
      attempts: [attempt(), attempt({ id: 'a0', endedAt: 500, completed: false })],
      whatWorks: ['Likes one step at a time'],
      avoidJargon: ['browser'],
      lastSession: { at: 2_000, skillId: 'video_call', summary: 'Joined a video call with help from a few hints.' },
    })
    const chip = await runSummary(f)
    expect(chip.status).toBe('done')
    const [file, text] = [...f.files.entries()][0]!
    expect(file).toMatch(/^\/tmp\/alongside-test\/exports\/lesson-summary-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}\.md$/)
    expect(chip.summary).toContain(file)
    expect(text).toContain('# Lesson summary: Video calls')
    expect(text).toContain('Finished the task: yes')
    expect(text).toContain('Likes one step at a time')
    expect(text).toContain('never includes screens or messages')
    expect(chip.result).toMatchObject({ kind: 'lesson_summary' })
    expect(f.injected[0]!.text).toMatch(/do not read out the file path/)
  })

  it('redacts digit runs, emails and passwords from free-text notes', () => {
    const md = buildCarerNote(
      makeLearner({
        attempts: [attempt()],
        whatWorks: ['Card 4111 1111 1111 1111 was on screen', 'email me at gran@example.com', 'password is hunter2'],
      }),
      new Date('2026-10-31T12:00:00Z'),
    )!
    expect(md).not.toMatch(/4111|gran@example|hunter2/)
  })

  it('says so kindly when there is no lesson to summarise', async () => {
    const f = makeFakes({ carerSharing: true })
    const chip = await runSummary(f)
    expect(chip.summary).toMatch(/do not have a finished lesson/)
    expect(f.files.size).toBe(0)
  })

  it('can only write .md files directly inside the exports folder', async () => {
    const written: string[] = []
    const deps = { exportsDir: '/tmp/x/exports', fs: { mkdir: async () => undefined, writeFile: async (file: string) => void written.push(file) } }
    await writeExport(deps, '../../etc/passwd.md', 'x')
    await writeExport(deps, 'a/b/c.md', 'x')
    expect(written).toEqual(['/tmp/x/exports/passwd.md', '/tmp/x/exports/c.md'])
    await expect(writeExport(deps, 'evil.sh', 'x')).rejects.toThrow()
  })
})
