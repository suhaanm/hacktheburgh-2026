import path from 'node:path'
import type { AttemptRecord, HelpLevel, LearnerSnapshot, SkillId } from '../../shared/protocol'
import { AgentUserError } from './errors'
import { defineAgent } from './ports'
import type { AgentDeps, AgentOutcome, ExportFs, SummaryPorts } from './ports'
import { inlineSafe, redactSensitive } from './text-safety'

export const SUMMARY_TIMEOUT_MS = 30_000

const REFUSAL_SHARING_OFF =
  'Carer sharing is switched off, so I have not written a summary. You can turn it on in settings and ask me again.'
const NOTHING_TO_SUMMARISE = 'I do not have a finished lesson to write up yet. Let us finish one first.'

const SKILL_NAMES: Record<SkillId, string> = {
  video_call: 'Video calls',
  spot_scam: 'Spotting scam messages',
  bigger_text: 'Making text bigger',
  custom: 'Something new',
}

const LEVEL_NAMES: Record<HelpLevel, string> = {
  1: 'Watch me (I showed them)',
  2: 'Walk with me (step by step)',
  3: 'Nudge me (a small clue when stuck)',
  4: 'On my own (they did it themselves)',
}

function note(text: string): string {
  return redactSensitive(inlineSafe(text, 160))
}

function teachBackWords(score: number | null): string {
  if (score === null) return 'not asked this time'
  if (score >= 0.8) return 'explained it well in their own words'
  if (score >= 0.5) return 'explained most of it in their own words'
  return 'found it hard to explain, so it is worth a second go'
}

function lastAttempt(snapshot: LearnerSnapshot): AttemptRecord | undefined {
  return [...snapshot.attempts].sort((a, b) => b.endedAt - a.endedAt)[0]
}

export function buildCarerNote(snapshot: LearnerSnapshot, at: Date): string | undefined {
  const attempt = lastAttempt(snapshot)
  const session = snapshot.lastSession
  if (!attempt && !session) return undefined
  const skillId = attempt?.skillId ?? session?.skillId
  const skill = skillId ? SKILL_NAMES[skillId] : 'A practice session'
  const lines: string[] = [
    `# Lesson summary: ${skill}`,
    '',
    `Written on ${at.toDateString()} by Alongside, an AI helper. This note holds summaries only. It never includes screens or messages.`,
    '',
  ]
  if (session?.summary) lines.push('## What happened', '', note(session.summary), '')
  if (attempt) {
    lines.push('## How it went', '')
    lines.push(`- Finished the task: ${attempt.completed ? 'yes' : 'not yet'}`)
    lines.push(`- Hints needed: ${attempt.hintsUsed}`)
    lines.push(`- Slips along the way: ${attempt.errors}`)
    lines.push(`- Help level: started with "${LEVEL_NAMES[attempt.levelAtStart]}", ended with "${LEVEL_NAMES[attempt.levelAtEnd]}"`)
    lines.push(`- Explaining it back: ${teachBackWords(attempt.teachBackScore)}`)
    if (attempt.confidence !== null) lines.push(`- How confident they felt: ${attempt.confidence} out of 5`)
    lines.push('')
  }
  const works = snapshot.whatWorks.slice(0, 6).map(note).filter(Boolean)
  if (works.length > 0) lines.push('## What helps them', '', ...works.map((w) => `- ${w}`), '')
  const avoid = snapshot.avoidJargon.slice(0, 8).map(note).filter(Boolean)
  if (avoid.length > 0) lines.push('## Words that confuse them', '', ...avoid.map((w) => `- ${w}`), '')
  lines.push(
    '## How you can help',
    '',
    '- Let them try first, and wait a few seconds before stepping in.',
    '- Praise the effort, not just the result.',
    '- Anything involving money or passwords stays with them. Please never ask them to share those.',
    '',
  )
  return lines.join('\n')
}

export function exportFileName(at: Date): string {
  const stamp = at.toISOString().slice(0, 16).replace(/[:T]/g, '-')
  return `lesson-summary-${stamp}.md`
}

export async function writeExport(deps: Pick<AgentDeps, 'exportsDir' | 'fs'>, fileName: string, markdown: string): Promise<string> {
  const fsApi: ExportFs = deps.fs ?? (await import('node:fs/promises'))
  const dir = path.resolve(deps.exportsDir)
  const file = path.resolve(dir, path.basename(fileName).replace(/[^A-Za-z0-9._-]/g, '_'))
  // Exports are summaries as .md files inside exports/ and nowhere else.
  if (path.dirname(file) !== dir || path.extname(file) !== '.md') throw new AgentUserError('I could not save that note.')
  await fsApi.mkdir(dir, { recursive: true })
  await fsApi.writeFile(file, markdown, { encoding: 'utf8', mode: 0o600 })
  return file
}

export const lessonSummaryAgent = defineAgent<SummaryPorts>({
  kind: 'lesson_summary',
  timeoutMs: SUMMARY_TIMEOUT_MS,
  title: () => 'Writing a note for your carer',

  createPorts: (deps, scope) => ({
    settings: () => deps.settings(),
    learnerSnapshot: () => deps.learner.snapshot(),
    saveExport: (fileName, markdown) => writeExport(deps, fileName, markdown),
    now: scope.now,
  }),

  async run({ ports }): Promise<AgentOutcome> {
    if (!ports.settings().carerSharing) {
      return { summary: REFUSAL_SHARING_OFF, tell: `${REFUSAL_SHARING_OFF} Tell the user this plainly.` }
    }
    const at = new Date(ports.now())
    const markdown = buildCarerNote(ports.learnerSnapshot(), at)
    if (!markdown) return { summary: NOTHING_TO_SUMMARISE, tell: `${NOTHING_TO_SUMMARISE} Say so kindly.` }
    const file = await ports.saveExport(exportFileName(at), markdown)
    const summary = `I saved a short note for your carer. It has summaries only: no screens or messages. File: ${file}`
    return {
      summary,
      result: { kind: 'lesson_summary', text: markdown },
      tell: 'A short carer note was saved in the exports folder. It has summaries only, no screens or messages. Tell the user it is saved, and do not read out the file path.',
    }
  },
})
