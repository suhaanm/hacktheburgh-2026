// LearnerStore: ONE human-readable, user-editable Markdown file (profile.md in userData).
// Design rules: the user's edits always win (stale-revision writes are rejected, external edits are re-read
// before every machine write); unknown sections and lines are preserved; if a value is unclear it is omitted
// rather than guessed; writes are atomic (temp file + rename); the whole file is deletable ("forget").
import { createHash } from 'node:crypto'
import fs from 'node:fs/promises'
import path from 'node:path'
import type {
  AttemptRecord,
  ConfidencePoint,
  HelpLevel,
  LearnerSnapshot,
  MarkdownEditRequest,
  MarkdownEditResult,
  SkillId,
  SkillState,
} from '../../shared/protocol'
import { BUILTIN_SKILL_IDS, SKILL_IDS } from '../../shared/protocol'
import type { LearnerStore, LevelDecision } from '../../shared/contracts'
import type { Settings } from '../../shared/settings'
import { DAY_MS, LEVEL_LABEL, clampLevel, createLevelEngine, evaluateAttempt as evaluate } from './levels'
import type { OverrideKind, TeachingLevelEngine } from './levels'
import { SKILLS, matchSkillName } from './skills/definitions'

export const PROFILE_FILE = 'profile.md'
const MAX_FILE_BYTES = 200_000
const MAX_ATTEMPTS = 200
const MAX_CONFIDENCE = 100
const MAX_NOTE_CHARS = 160
const MAX_LIST_ITEMS = 25

type ListKey = 'about' | 'goals' | 'whatWorks' | 'jargon' | 'safety' | 'sharing'
type MachineKey = 'skills' | 'confidence' | 'attempts' | 'lastSession' | 'doneForMe'
type SectionKey = ListKey | MachineKey

const CANONICAL: { key: SectionKey; heading: string; match: RegExp }[] = [
  { key: 'about', heading: 'About me & accessibility', match: /^about me|^about\b|^accessib/ },
  { key: 'goals', heading: 'Goals', match: /^goals?\b|^what i want/ },
  { key: 'skills', heading: 'Skills', match: /^skills?\b/ },
  { key: 'confidence', heading: 'Confidence log', match: /^confidence/ },
  { key: 'attempts', heading: 'Attempt history', match: /^attempt/ },
  { key: 'doneForMe', heading: 'Done for me', match: /^done for me/ },
  { key: 'whatWorks', heading: 'What works for me', match: /^what works/ },
  { key: 'jargon', heading: 'Jargon to avoid', match: /^jargon/ },
  { key: 'safety', heading: 'Safety notes', match: /^safety/ },
  { key: 'sharing', heading: 'Who can see what', match: /^who can see|^sharing|^privacy/ },
  { key: 'lastSession', heading: 'Last session', match: /^last session/ },
]

const DEFAULT_SHARING = [
  '- Nobody sees anything unless you switch on carer sharing in Settings.',
  '- A carer only ever sees a short summary of your skills and confidence. Never your screen, never your messages.',
]

const PREAMBLE_DEFAULT = [
  '# My Alongside profile',
  '',
  '> This file is yours. Read it, change it, or delete any line and Alongside will follow what it says here.',
  '> Times are UTC. Say "forget that" and the last thing written down is removed.',
]

interface RawSection {
  key: SectionKey | null
  heading: string
  lines: string[]
}

interface Model {
  preamble: string[]
  // Section order as the file has it; unknown sections stay where they were.
  sections: RawSection[]
  skills: Partial<Record<SkillId, SkillState>>
  extraSkillRows: string[]
  confidence: ConfidencePoint[]
  attempts: AttemptRecord[]
  lastSession?: { at: number; skillId?: SkillId; summary: string }
  // Things the assistant did on the learner's behalf (open_for_me / act_for_me), by skill or by what was done: dependency, shown honestly.
  doneForMe: Record<string, number>
}

export function sha256(text: string): string {
  return createHash('sha256').update(text).digest('hex')
}

// ---------- tolerant parsing helpers ----------
export function parseLevelCell(cell: string): HelpLevel | undefined {
  const t = cell.trim().toLowerCase()
  const m = /(?:^|\b|l)([1-4])(?!\d)/.exec(t)
  if (m) return Number(m[1]) as HelpLevel
  for (const lvl of [1, 2, 3, 4] as HelpLevel[]) {
    if (t.includes(LEVEL_LABEL[lvl].toLowerCase())) return lvl
  }
  return undefined
}

const ISO_RE = /^(\d{4})-(\d{2})-(\d{2})(?:[ t](\d{2}):(\d{2})(?::(\d{2}))?)?z?$/i

// undefined = "unsure": the caller keeps what it had. null = explicitly nothing ("never", dash).
export function parseDateCell(cell: string, now: number): number | null | undefined {
  const t = cell.trim().toLowerCase()
  if (t === '' || t === '-' || t === '—' || t === '–' || t === 'never' || t === 'none' || t === 'n/a') return null
  if (t === 'today') return now
  if (t === 'tomorrow') return now + DAY_MS
  if (t === 'yesterday') return now - DAY_MS
  const m = ISO_RE.exec(t)
  if (!m) return undefined
  const ms = Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4] ?? 0), Number(m[5] ?? 0), Number(m[6] ?? 0))
  return Number.isNaN(ms) ? undefined : ms
}

export function formatDate(ms: number | null, withTime = true): string {
  if (ms === null) return '—'
  const iso = new Date(ms).toISOString()
  return withTime ? `${iso.slice(0, 10)} ${iso.slice(11, 16)}` : iso.slice(0, 10)
}

function splitRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, '').replace(/\|$/, '')
  return trimmed.split('|').map((c) => c.trim())
}

function isSeparatorRow(line: string): boolean {
  return /^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(line.trim())
}

interface Table {
  header: string[]
  rows: string[][]
  extra: string[]
}

function parseTable(lines: string[]): Table {
  const out: Table = { header: [], rows: [], extra: [] }
  let seenHeader = false
  for (const line of lines) {
    const t = line.trim()
    if (t === '') continue
    if (t.startsWith('|')) {
      if (isSeparatorRow(t)) continue
      if (!seenHeader) {
        out.header = splitRow(t).map((h) => h.toLowerCase())
        seenHeader = true
      } else out.rows.push(splitRow(t))
    } else out.extra.push(line)
  }
  return out
}

function col(header: string[], ...needles: string[]): number {
  return header.findIndex((h) => needles.some((n) => h.includes(n)))
}

function matchHeading(heading: string): SectionKey | null {
  const h = heading.toLowerCase().replace(/[^a-z0-9& ]+/g, ' ').replace(/\s+/g, ' ').trim()
  return CANONICAL.find((c) => c.match.test(h))?.key ?? null
}

function parseSections(md: string): { preamble: string[]; sections: RawSection[] } {
  const lines = md.replace(/\r\n?/g, '\n').split('\n')
  const preamble: string[] = []
  const sections: RawSection[] = []
  let current: RawSection | null = null
  const seen = new Set<SectionKey>()
  for (const line of lines) {
    const h = /^##\s+(.*?)\s*#*\s*$/.exec(line)
    if (h) {
      const key = matchHeading(h[1])
      const usable = key && !seen.has(key) ? key : null
      if (usable) seen.add(usable)
      current = { key: usable, heading: h[1], lines: [] }
      sections.push(current)
    } else if (current) current.lines.push(line)
    else preamble.push(line)
  }
  for (const s of sections) while (s.lines.length && s.lines[s.lines.length - 1].trim() === '') s.lines.pop()
  while (preamble.length && preamble[preamble.length - 1].trim() === '') preamble.pop()
  return { preamble, sections }
}

function parseSkills(section: RawSection | undefined, now: number): { skills: Model['skills']; extraRows: string[] } {
  const skills: Model['skills'] = {}
  const extraRows: string[] = []
  if (!section) return { skills, extraRows }
  const table = parseTable(section.lines)
  const iSkill = Math.max(col(table.header, 'skill'), 0)
  const iLevel = col(table.header, 'level')
  const iStreak = col(table.header, 'clean', 'streak')
  const iLast = col(table.header, 'last', 'practis', 'practic')
  const iNext = col(table.header, 'next', 'review')
  for (const row of table.rows) {
    const id = matchSkillName(row[iSkill] ?? '')
    if (!id) {
      extraRows.push(`| ${row.join(' | ')} |`)
      continue
    }
    const level = iLevel >= 0 ? parseLevelCell(row[iLevel] ?? '') : undefined
    if (level === undefined) continue // unsure -> omit (the skill starts fresh)
    const streak = iStreak >= 0 ? Number.parseInt(row[iStreak] ?? '', 10) : 0
    const last = iLast >= 0 ? parseDateCell(row[iLast] ?? '', now) : null
    const next = iNext >= 0 ? parseDateCell(row[iNext] ?? '', now) : null
    skills[id] = {
      level,
      streakClean: Number.isFinite(streak) && streak > 0 ? streak : 0,
      lastSeen: last === undefined ? null : last,
      nextReview: next === undefined ? null : next,
    }
  }
  return { skills, extraRows }
}

const DATE_WORD = '(\\d{4}-\\d{2}-\\d{2}(?:[ t]\\d{2}:\\d{2})?|today|yesterday)'
const CONF_RE = new RegExp(`^[-*]\\s*${DATE_WORD}\\s*[\\u00b7|,;]\\s*([^\\u00b7|,;]+?)\\s*[\\u00b7|,;]\\s*([1-5])\\s*(?:\\/\\s*5)?\\b`, 'i')

function parseConfidence(section: RawSection | undefined, now: number): ConfidencePoint[] {
  if (!section) return []
  const out: ConfidencePoint[] = []
  for (const line of section.lines) {
    const m = CONF_RE.exec(line.trim())
    if (!m) continue
    const at = parseDateCell(m[1], now)
    const skillId = matchSkillName(m[2])
    if (typeof at !== 'number' || !skillId) continue
    out.push({ at, skillId, rating: Number(m[3]) })
  }
  return out
}

function parseAttempts(section: RawSection | undefined, now: number): AttemptRecord[] {
  if (!section) return []
  const table = parseTable(section.lines)
  const iWhen = Math.max(col(table.header, 'started', 'when'), 0)
  const iSkill = col(table.header, 'skill')
  const iLevel = col(table.header, 'level')
  const iHints = col(table.header, 'hint')
  const iErrors = col(table.header, 'error')
  const iStalls = col(table.header, 'stall')
  const iTb = col(table.header, 'teach')
  const iConf = col(table.header, 'confidence')
  const iMins = col(table.header, 'min')
  const iResult = col(table.header, 'result')
  const iFlags = col(table.header, 'flag')
  const out: AttemptRecord[] = []
  for (const row of table.rows) {
    const startedAt = parseDateCell(row[iWhen] ?? '', now)
    const skillId = iSkill >= 0 ? matchSkillName(row[iSkill] ?? '') : null
    if (typeof startedAt !== 'number' || !skillId) continue
    const num = (i: number): number => {
      const n = i >= 0 ? Number.parseInt(row[i] ?? '', 10) : 0
      return Number.isFinite(n) && n > 0 ? n : 0
    }
    const lv = (row[iLevel] ?? '').match(/([1-4])\D*([1-4])?/)
    const levelAtStart = (lv ? Number(lv[1]) : 1) as HelpLevel
    const levelAtEnd = (lv?.[2] ? Number(lv[2]) : levelAtStart) as HelpLevel
    const tbRaw = iTb >= 0 ? Number.parseFloat(row[iTb] ?? '') : Number.NaN
    const confRaw = iConf >= 0 ? Number.parseInt(row[iConf] ?? '', 10) : Number.NaN
    const result = (iResult >= 0 ? row[iResult] ?? '' : '').toLowerCase()
    const flags = (iFlags >= 0 ? row[iFlags] ?? '' : '').toLowerCase()
    out.push({
      id: `att-${startedAt}-${skillId}`,
      skillId,
      lessonId: `att-${startedAt}-${skillId}`,
      startedAt,
      endedAt: startedAt + num(iMins) * 60_000,
      levelAtStart,
      levelAtEnd,
      completed: !result.includes('stopped'),
      hintsUsed: num(iHints),
      errors: num(iErrors),
      stalls: num(iStalls),
      safetyFlag: flags.includes('safety'),
      anxietyPhrase: flags.includes('worried'),
      teachBackScore: Number.isFinite(tbRaw) && tbRaw >= 0 && tbRaw <= 1 ? tbRaw : null,
      confidence: Number.isFinite(confRaw) && confRaw >= 1 && confRaw <= 5 ? confRaw : null,
      clean: result.includes('clean'),
    })
  }
  return out
}

const LAST_RE = new RegExp(`^[-*]\\s*${DATE_WORD}\\s*[\\u00b7|]\\s*([^\\u00b7|]*?)\\s*[\\u00b7|]\\s*(.+)$`, 'i')

function parseLastSession(section: RawSection | undefined, now: number): Model['lastSession'] {
  if (!section) return undefined
  for (const line of section.lines) {
    const m = LAST_RE.exec(line.trim())
    if (!m) continue
    const at = parseDateCell(m[1], now)
    if (typeof at !== 'number') continue
    const skillId = matchSkillName(m[2]) ?? undefined
    return { at, skillId, summary: m[3].trim() }
  }
  return undefined
}

const DONE_RE = /^[-*]\s*(.+?)\s*[\u00b7|]\s*(\d{1,6})\s*$/
const MAX_DONE_KEYS = 20

function parseDoneForMe(section: RawSection | undefined): Record<string, number> {
  const out: Record<string, number> = {}
  for (const line of section?.lines ?? []) {
    const m = DONE_RE.exec(line.trim())
    if (m && Object.keys(out).length < MAX_DONE_KEYS) out[m[1]] = Number(m[2])
  }
  return out
}

function parseModel(md: string, now: number): Model {
  const { preamble, sections } = parseSections(md)
  const byKey = (k: SectionKey): RawSection | undefined => sections.find((s) => s.key === k)
  const { skills, extraRows } = parseSkills(byKey('skills'), now)
  return {
    preamble,
    sections,
    skills,
    extraSkillRows: extraRows,
    confidence: parseConfidence(byKey('confidence'), now),
    attempts: parseAttempts(byKey('attempts'), now),
    lastSession: parseLastSession(byKey('lastSession'), now),
    doneForMe: parseDoneForMe(byKey('doneForMe')),
  }
}

function emptyModel(): Model {
  return { preamble: [...PREAMBLE_DEFAULT], sections: [], skills: {}, extraSkillRows: [], confidence: [], attempts: [], doneForMe: {} }
}

// ---------- rendering ----------
function skillTable(model: Model): string[] {
  const rows = SKILL_IDS.filter((id) => model.skills[id]).map((id) => {
    const s = model.skills[id] as SkillState
    return `| ${SKILLS[id].name} | ${s.level} — ${LEVEL_LABEL[s.level]} | ${s.streakClean} | ${formatDate(s.lastSeen)} | ${formatDate(s.nextReview)} |`
  })
  return ['| Skill | Level | Clean in a row | Last practised | Next review |', '|---|---|---|---|---|', ...rows, ...model.extraSkillRows]
}

function attemptTable(model: Model): string[] {
  const rows = model.attempts.slice(-MAX_ATTEMPTS).map((a) => {
    const mins = Math.max(0, Math.round((a.endedAt - a.startedAt) / 60_000))
    const result = !a.completed ? 'stopped' : a.clean ? 'clean' : 'finished'
    const flags = [a.safetyFlag ? 'safety' : '', a.anxietyPhrase ? 'worried' : ''].filter(Boolean).join(' ')
    return `| ${formatDate(a.startedAt)} | ${SKILLS[a.skillId].name} | ${a.levelAtStart}→${a.levelAtEnd} | ${a.hintsUsed} | ${a.errors} | ${a.stalls} | ${a.teachBackScore === null ? '—' : a.teachBackScore.toFixed(2)} | ${a.confidence ?? '—'} | ${mins} | ${result} | ${flags || '—'} |`
  })
  return ['| Started | Skill | Level | Hints | Errors | Stalls | Teach-back | Confidence | Mins | Result | Flags |', '|---|---|---|---|---|---|---|---|---|---|---|', ...rows]
}

function render(model: Model): string {
  const out: string[] = [...model.preamble]
  const present = new Set(model.sections.map((s) => s.key).filter((k): k is SectionKey => k !== null))
  const ordered: RawSection[] = [...model.sections]
  for (const c of CANONICAL) {
    if (present.has(c.key)) continue
    if (c.key === 'lastSession' && !model.lastSession) continue
    if (c.key === 'doneForMe' && Object.keys(model.doneForMe).length === 0) continue
    ordered.push({ key: c.key, heading: c.heading, lines: c.key === 'sharing' ? [...DEFAULT_SHARING] : [] })
  }
  for (const s of ordered) {
    out.push('', `## ${s.heading}`, '')
    let body: string[]
    switch (s.key) {
      case 'skills':
        body = [...skillTable(model), ...parseTable(s.lines).extra]
        break
      case 'attempts':
        body = [...attemptTable(model), ...parseTable(s.lines).extra]
        break
      case 'confidence':
        body = [
          ...model.confidence
            .slice(-MAX_CONFIDENCE)
            .map((p) => `- ${formatDate(p.at)} · ${SKILLS[p.skillId].name} · ${p.rating}/5`),
          ...s.lines.filter((l) => l.trim() !== '' && !CONF_RE.test(l.trim())),
        ]
        break
      case 'lastSession':
        body = model.lastSession
          ? [`- ${formatDate(model.lastSession.at)} · ${model.lastSession.skillId ? SKILLS[model.lastSession.skillId].name : 'general'} · ${model.lastSession.summary}`]
          : []
        break
      case 'doneForMe':
        body = Object.entries(model.doneForMe).map(([k, n]) => `- ${k} \u00b7 ${n}`)
        break
      default:
        body = s.lines
    }
    out.push(...body)
  }
  return `${out.join('\n').replace(/\n{3,}/g, '\n\n').trimEnd()}\n`
}

// ---------- notes ----------
const UNCERTAIN = /^(?:maybe|might|possibly|perhaps|probably|unsure|not sure|i think|i guess|seems? like)\b/i
const INJECTION = /\b(?:ignore|disregard|forget) (?:all |any |the |your |previous |prior )*(?:instructions?|rules?|prompt)|system prompt|you (?:must|should) (?:now )?(?:always|never|tell|send|reveal)|developer message|<\/?[a-z]/i

export function sanitizeNote(raw: string): string | null {
  let t = raw.replace(/[\u0000-\u001f\u007f]+/g, ' ').replace(/[<>`]/g, '').replace(/\[/g, '(').replace(/\]/g, ')').replace(/\s+/g, ' ').trim()
  t = t.replace(/^[-*#>\s]+/, '').trim()
  if (t.length < 3) return null
  if (UNCERTAIN.test(t)) return null // unsure -> omit
  if (INJECTION.test(t)) return null
  if (t.length > MAX_NOTE_CHARS) t = `${t.slice(0, MAX_NOTE_CHARS - 1).trimEnd()}…`
  return t
}

const NOTE_ROUTES: { re: RegExp; list: ListKey }[] = [
  { re: /^(?:works?|analogy|helped|helps)\s*:\s*/i, list: 'whatWorks' },
  { re: /^(?:avoid[- ]?jargon|jargon|avoid)\s*:\s*/i, list: 'jargon' },
  { re: /^goals?\s*:\s*/i, list: 'goals' },
  { re: /^safety\s*:\s*/i, list: 'safety' },
  { re: /^(?:access(?:ibility)?|about)\s*:\s*/i, list: 'about' },
]

function bulletText(line: string): string | null {
  const m = /^\s*[-*]\s+(.*\S)\s*$/.exec(line)
  return m ? m[1] : null
}

// ---------- the store ----------
export interface LearnerStoreOptions {
  // null keeps everything in memory (tests); otherwise profile.md lives here.
  dir: string | null
  now?: () => number
  engine?: TeachingLevelEngine
  getSettings?: () => Pick<Settings, 'demoMode' | 'helpLevelMode' | 'carerSharing'>
}

export interface RecordAttemptExtras {
  // When the runner already evaluated the attempt it passes its decision; otherwise the store evaluates.
  decision?: LevelDecision
  override?: OverrideKind | null
  // One plain sentence for the memory callback ("last time ...").
  summary?: string
}

export interface CarerDigest {
  ok: boolean
  reason?: 'carer_sharing_off'
  markdown?: string
  data?: {
    generatedAt: number
    preferredName?: string
    skills: { skillId: SkillId; name: string; level: HelpLevel; levelLabel: string; lastPractised: number | null }[]
    confidence: { first: number | null; latest: number | null; points: number }
    hints: { firstAttemptAvg: number | null; latestAttemptAvg: number | null }
    attempts: number
    scamChecks: number
  }
}

export function resolveUserDataDir(fallback: string | null): string | null {
  return process.env.ALONGSIDE_USERDATA || fallback
}

export class TeachingLearnerStore implements LearnerStore {
  private model: Model = emptyModel()
  private revision = ''
  private loaded = false
  private queue: Promise<unknown> = Promise.resolve()
  private lastNote: { list: ListKey; line: string } | null = null
  private readonly file: string | null
  private readonly now: () => number
  private readonly engine: TeachingLevelEngine
  private readonly getSettings: NonNullable<LearnerStoreOptions['getSettings']>
  private memoryDoc: string | null = null
  private diskText: string | null = null

  constructor(opts: LearnerStoreOptions) {
    this.file = opts.dir ? path.join(opts.dir, PROFILE_FILE) : null
    this.now = opts.now ?? Date.now
    this.engine = opts.engine ?? createLevelEngine()
    this.getSettings = opts.getSettings ?? (() => ({ demoMode: true, helpLevelMode: 'auto', carerSharing: false }))
  }

  get filePath(): string | null {
    return this.file
  }

  // ----- contract -----
  async load(): Promise<LearnerSnapshot> {
    await this.serial(() => this.reloadFromDisk(true))
    this.loaded = true
    return this.snapshot()
  }

  // Pick up edits made to profile.md outside the app (a text editor, the demo seed) before the next session or lesson.
  async refresh(): Promise<void> {
    await this.serial(() => this.reloadFromDisk(!this.loaded))
    this.loaded = true
  }

  async save(): Promise<void> {
    await this.serial(() => this.persist())
  }

  snapshot(): LearnerSnapshot {
    const now = this.now()
    const skills = {} as LearnerSnapshot['skills']
    for (const id of BUILTIN_SKILL_IDS) {
      const raw = this.model.skills[id] ?? this.engine.initial(now)
      skills[id] = this.engine.decay(raw, now)
    }
    // The generic skill behind Argon-planned lessons only shows once it has been used.
    if (this.model.skills.custom) skills.custom = this.engine.decay(this.model.skills.custom, now)
    return {
      skills,
      confidenceLog: this.model.confidence.map((c) => ({ ...c })),
      attempts: this.model.attempts.map((a) => ({ ...a })),
      whatWorks: this.listItems('whatWorks'),
      avoidJargon: this.listItems('jargon').flatMap((t) => t.split(/\s*,\s*/)).filter(Boolean),
      lastSession: this.model.lastSession ? { ...this.model.lastSession } : undefined,
      ...(Object.keys(this.model.doneForMe).length ? { doneForMe: { ...this.model.doneForMe } } : {}),
    }
  }

  preferredName(): string | null {
    return this.aboutField('Preferred name')
  }

  // Skill states as stored (before the derived absence decay); the runner stores what it evaluated.
  storedSkill(id: SkillId): SkillState | undefined {
    return this.model.skills[id] ? { ...(this.model.skills[id] as SkillState) } : undefined
  }

  async recordAttempt(attempt: AttemptRecord, extras: RecordAttemptExtras = {}): Promise<LearnerSnapshot> {
    await this.serial(async () => {
      await this.reloadFromDisk(false)
      if (this.model.attempts.some((a) => a.id === attempt.id)) return
      const base = this.snapshot().skills[attempt.skillId] ?? this.engine.initial(attempt.endedAt)
      const settings = this.getSettings()
      const history = this.model.attempts.filter((a) => a.skillId === attempt.skillId)
      const decision =
        extras.decision ??
        evaluate(attempt, base, {
          demoMode: settings.demoMode,
          now: attempt.endedAt,
          recentAttempts: history,
          override: extras.override ?? null,
          locked: settings.helpLevelMode === 'locked',
        })
      const stored: AttemptRecord = { ...attempt, levelAtEnd: decision.state.level }
      this.model.attempts = [...this.model.attempts, stored].slice(-MAX_ATTEMPTS)
      this.model.skills[attempt.skillId] = { ...decision.state }
      if (attempt.confidence !== null) {
        this.model.confidence = [...this.model.confidence, { at: attempt.endedAt, skillId: attempt.skillId, rating: attempt.confidence }].slice(-MAX_CONFIDENCE)
      }
      this.model.lastSession = {
        at: attempt.endedAt,
        skillId: attempt.skillId,
        summary: sanitizeNote(extras.summary ?? '') ?? defaultSummary(stored),
      }
      await this.persist()
    })
    return this.snapshot()
  }

  // Counts one thing the assistant did FOR the learner (key = skill id, `open:<host>` or `task:<goal>`), so the progress view can show dependency.
  async recordDoneForMe(key: string): Promise<void> {
    const clean = sanitizeNote(key)?.slice(0, 60).replace(/[\u00b7|]/g, ' ').trim()
    if (!clean) return
    await this.serial(async () => {
      await this.reloadFromDisk(false)
      const known = this.model.doneForMe
      if (!(clean in known) && Object.keys(known).length >= MAX_DONE_KEYS) delete known[Object.keys(known)[0]]
      known[clean] = (known[clean] ?? 0) + 1
      await this.persist()
    })
  }

  async addNote(note: string): Promise<void> {
    await this.serial(async () => {
      await this.reloadFromDisk(false)
      const raw = note.trim()
      const forget = /^forget\s*:?\s*(.*)$/i.exec(raw)
      if (forget) {
        this.removeMatching(forget[1].trim())
        await this.persist()
        return
      }
      const name = /^(?:name|call me|preferred name)\s*:\s*(.+)$/i.exec(raw)
      if (name) {
        const value = sanitizeNote(name[1])
        if (value) this.setAboutField('Preferred name', value)
        await this.persist()
        return
      }
      let list: ListKey = 'whatWorks'
      let body = raw
      for (const route of NOTE_ROUTES) {
        if (route.re.test(raw)) {
          list = route.list
          body = raw.replace(route.re, '')
          break
        }
      }
      const clean = sanitizeNote(body)
      if (!clean) return
      const line = list === 'safety' ? `- ${formatDate(this.now(), false)}: ${clean}` : `- ${clean}`
      const section = this.ensureList(list)
      const exists = section.lines.some((l) => bulletText(l)?.toLowerCase() === line.slice(2).toLowerCase())
      if (exists) return
      section.lines.push(line)
      this.trimList(section)
      this.lastNote = { list, line }
      await this.persist()
    })
  }

  async editMarkdown(req: MarkdownEditRequest): Promise<MarkdownEditResult> {
    return this.serial(async () => {
      await this.reloadFromDisk(!this.loaded)
      this.loaded = true
      const current = this.currentText()
      const currentRev = sha256(current)
      if (req.op === 'read') return { ok: true, content: current, revision: currentRev }
      if (typeof req.content !== 'string' || req.revision === undefined || req.revision !== currentRev) {
        return { ok: false, conflict: true, content: current, revision: currentRev }
      }
      if (Buffer.byteLength(req.content, 'utf8') > MAX_FILE_BYTES) return { ok: false, content: current, revision: currentRev }
      this.adopt(req.content)
      await this.writeRaw(req.content)
      return { ok: true, content: req.content, revision: this.revision }
    })
  }

  // ----- beyond the contract -----
  // Seed or correct a skill (demo seeding, a carer's edit through the UI). Keeps the file consistent.
  async setSkillLevel(skillId: SkillId, level: HelpLevel, opts: { lastSeen?: number | null; streakClean?: number } = {}): Promise<void> {
    await this.serial(async () => {
      await this.reloadFromDisk(false)
      const now = this.now()
      const prev = this.model.skills[skillId] ?? this.engine.initial(now)
      const lastSeen = opts.lastSeen === undefined ? prev.lastSeen : opts.lastSeen
      this.model.skills[skillId] = { level: clampLevel(level), streakClean: opts.streakClean ?? 0, lastSeen, nextReview: lastSeen === null ? null : lastSeen + DAY_MS }
      await this.persist()
    })
  }

  // "Forget that": text removes every bullet containing it; empty / "that" / "last" removes the last note written.
  async forget(what: string): Promise<{ removed: string[] }> {
    return this.serial(async () => {
      await this.reloadFromDisk(false)
      const removed = this.removeMatching(what)
      await this.persist()
      return { removed }
    })
  }

  // "Clear my data": the whole profile goes back to a blank file.
  async forgetAll(): Promise<void> {
    await this.serial(async () => {
      this.model = emptyModel()
      this.lastNote = null
      await this.persist()
    })
  }

  exportCarerDigest(): CarerDigest {
    const settings = this.getSettings()
    if (!settings.carerSharing) return { ok: false, reason: 'carer_sharing_off' }
    const snap = this.snapshot()
    const now = this.now()
    const name = this.aboutField('Preferred name')
    const skills = SKILL_IDS.filter((id) => this.model.skills[id]).map((id) => {
      const st = snap.skills[id] as SkillState
      return { skillId: id, name: SKILLS[id].name, level: st.level, levelLabel: LEVEL_LABEL[st.level], lastPractised: st.lastSeen }
    })
    const hints = snap.attempts.map((a) => a.hintsUsed)
    const avg = (xs: number[]): number | null => (xs.length ? Math.round((xs.reduce((a, b) => a + b, 0) / xs.length) * 10) / 10 : null)
    const k = Math.min(3, Math.max(1, Math.floor(hints.length / 2)))
    const data: NonNullable<CarerDigest['data']> = {
      generatedAt: now,
      preferredName: name ?? undefined,
      skills,
      confidence: {
        first: snap.confidenceLog[0]?.rating ?? null,
        latest: snap.confidenceLog[snap.confidenceLog.length - 1]?.rating ?? null,
        points: snap.confidenceLog.length,
      },
      hints: { firstAttemptAvg: avg(hints.slice(0, k)), latestAttemptAvg: avg(hints.slice(-k)) },
      attempts: snap.attempts.length,
      scamChecks: snap.attempts.filter((a) => a.skillId === 'spot_scam').length,
    }
    const who = name ?? 'The learner'
    const lines = [
      `# Weekly summary for ${who}`,
      '',
      `Shared because ${who} switched carer sharing on. This is a summary only: no screens and no messages.`,
      '',
      ...(skills.length ? skills.map((s) => `- ${s.name}: ${s.levelLabel} (last practised ${formatDate(s.lastPractised, false)})`) : ['- Nothing practised yet.']),
      '',
      `- Practice sessions: ${data.attempts}`,
      ...(data.hints.firstAttemptAvg !== null && data.hints.latestAttemptAvg !== null
        ? [`- Hints needed per task: ${data.hints.firstAttemptAvg} at the start, ${data.hints.latestAttemptAvg} lately`]
        : []),
      ...(data.confidence.latest !== null ? [`- Confidence (1 to 5): ${data.confidence.first} at the start, ${data.confidence.latest} lately`] : []),
      `- Scam checks practised: ${data.scamChecks}`,
      '',
      `How to help without taking over: ask before touching the screen, and let ${who} do the tapping.`,
    ]
    return { ok: true, markdown: lines.join('\n'), data }
  }

  // ----- internals -----
  private serial<T>(fn: () => Promise<T>): Promise<T> {
    const run = this.queue.then(fn, fn)
    this.queue = run.catch(() => undefined)
    return run
  }

  private currentText(): string {
    if (this.file) return this.diskText ?? render(this.model)
    return this.memoryDoc ?? render(this.model)
  }

  // Re-read the file; if it differs from what we last wrote the user (or their editor) changed it: their text wins.
  private async reloadFromDisk(first: boolean): Promise<void> {
    if (!this.file) {
      if (first && this.memoryDoc === null) {
        this.model = emptyModel()
        this.memoryDoc = render(this.model)
        this.revision = sha256(this.memoryDoc)
      }
      return
    }
    let text: string | null = null
    try {
      text = await fs.readFile(this.file, 'utf8')
    } catch {
      text = null
    }
    if (text === null) {
      // First run, or the user deleted the file: either way they get a fresh blank profile.
      if (first || this.diskText !== null) {
        this.model = emptyModel()
        this.diskText = null
        await this.persist()
      }
      return
    }
    if (text.length > MAX_FILE_BYTES) return
    if (first || sha256(text) !== this.revision) this.adopt(text)
    this.diskText = text
    this.revision = sha256(text)
  }

  private adopt(md: string): void {
    this.model = parseModel(md, this.now())
  }

  private async persist(): Promise<void> {
    await this.writeRaw(render(this.model))
  }

  private async writeRaw(text: string): Promise<void> {
    this.revision = sha256(text)
    if (!this.file) {
      this.memoryDoc = text
      return
    }
    this.diskText = text
    try {
      await fs.mkdir(path.dirname(this.file), { recursive: true })
      const tmp = `${this.file}.${process.pid}.${Date.now()}.tmp`
      await fs.writeFile(tmp, text, 'utf8')
      await fs.rename(tmp, this.file)
    } catch (err) {
      console.error('[learner-store] write failed:', err)
    }
  }

  private section(key: SectionKey): RawSection | undefined {
    return this.model.sections.find((s) => s.key === key)
  }

  private ensureList(key: ListKey): RawSection {
    const existing = this.section(key)
    if (existing) return existing
    const def = CANONICAL.find((c) => c.key === key)
    const created: RawSection = { key, heading: def?.heading ?? key, lines: key === 'sharing' ? [...DEFAULT_SHARING] : [] }
    this.model.sections.push(created)
    return created
  }

  private listItems(key: ListKey): string[] {
    return (this.section(key)?.lines ?? []).map(bulletText).filter((t): t is string => t !== null).map((t) => t.replace(/^\d{4}-\d{2}-\d{2}:\s*/, ''))
  }

  private trimList(section: RawSection): void {
    const bullets = section.lines.filter((l) => bulletText(l) !== null)
    if (bullets.length <= MAX_LIST_ITEMS) return
    const drop = new Set(bullets.slice(0, bullets.length - MAX_LIST_ITEMS))
    section.lines = section.lines.filter((l) => !drop.has(l))
  }

  private aboutField(label: string): string | null {
    for (const line of this.section('about')?.lines ?? []) {
      const m = new RegExp(`^\\s*[-*]\\s*${label}\\s*:\\s*(.+)$`, 'i').exec(line)
      if (m) return m[1].trim()
    }
    return null
  }

  private setAboutField(label: string, value: string): void {
    const section = this.ensureList('about')
    const re = new RegExp(`^\\s*[-*]\\s*${label}\\s*:`, 'i')
    const line = `- ${label}: ${value}`
    const idx = section.lines.findIndex((l) => re.test(l))
    if (idx >= 0) section.lines[idx] = line
    else section.lines.unshift(line)
  }

  private removeMatching(what: string): string[] {
    const removed: string[] = []
    const needle = what.trim().toLowerCase()
    const generic = needle === '' || needle === 'that' || needle === 'it' || needle === 'last' || needle === 'the last one'
    const lists: ListKey[] = ['about', 'goals', 'whatWorks', 'jargon', 'safety']
    if (generic) {
      const last = this.lastNote
      if (last) {
        const section = this.section(last.list)
        if (section) {
          const i = section.lines.lastIndexOf(last.line)
          if (i >= 0) {
            section.lines.splice(i, 1)
            removed.push(last.line.slice(2))
          }
        }
        this.lastNote = null
      }
      return removed
    }
    for (const key of lists) {
      const section = this.section(key)
      if (!section) continue
      section.lines = section.lines.filter((line) => {
        const text = bulletText(line)
        if (text !== null && text.toLowerCase().includes(needle)) {
          removed.push(text)
          return false
        }
        return true
      })
    }
    return removed
  }
}

function defaultSummary(a: AttemptRecord): string {
  const skill = SKILLS[a.skillId]
  if (!a.completed) return `Started "${skill.name}" and stopped part way. No pressure.`
  const hints = a.hintsUsed === 0 ? 'with no hints' : a.hintsUsed === 1 ? 'with one hint' : `with ${a.hintsUsed} hints`
  return `Finished "${skill.name}" ${hints}.`
}

export function createLearnerStore(opts: LearnerStoreOptions): TeachingLearnerStore {
  return new TeachingLearnerStore(opts)
}
