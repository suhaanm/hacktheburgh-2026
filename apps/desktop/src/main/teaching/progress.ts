// Data for the Progress view: skills with levels, "things you can do now", the confidence trend and the
// hints-per-task series (the anti-dependency proof). Pure and serialisable: no node imports, so the dock
// renderer can import it directly, or it can travel over IPC as JSON.
import type { HelpLevel, LearnerSnapshot, SkillId } from '../../shared/protocol'
import { BUILTIN_SKILL_IDS, SKILL_IDS } from '../../shared/protocol'
import { LEVEL_LABEL, isMastered } from './levels'
import { SKILLS } from './skills/definitions'

export type SkillMode = 'not_started' | 'with_help' | 'mostly_alone' | 'on_my_own'

export interface SkillProgress {
  skillId: SkillId
  name: string
  level: HelpLevel
  levelLabel: string
  mode: SkillMode
  lastPractised: number | null
  nextReview: number | null
  reviewDue: boolean
  attempts: number
  mastered: boolean
}

export interface CanDoItem {
  skillId: SkillId
  text: string
  mode: Exclude<SkillMode, 'not_started'>
  since: number
}

export interface HintPoint {
  attempt: number // 1-based, per skill
  at: number
  hints: number
  errors: number
  stalls: number
  level: HelpLevel
  clean: boolean
}

export interface ProgressData {
  generatedAt: number
  skills: SkillProgress[]
  canDoNow: CanDoItem[]
  confidence: { points: { at: number; skillId: SkillId; rating: number }[]; first: number | null; latest: number | null }
  hintsPerTask: { skillId: SkillId; name: string; series: HintPoint[] }[]
  overall: {
    attempts: number
    firstAttemptHints: number | null
    latestAttemptHints: number | null
    trend: 'down' | 'flat' | 'up' | 'not_enough_data'
    headline: string
  }
  nextSuggested: { skillId: SkillId; reason: string } | null
  // Times the assistant did something for the learner (dependency, shown honestly); only present when it happened.
  doneForMe?: { total: number; text: string }
}

function modeFor(level: HelpLevel, practised: boolean): SkillMode {
  if (!practised) return 'not_started'
  if (level <= 2) return 'with_help'
  return level === 3 ? 'mostly_alone' : 'on_my_own'
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}

export function buildProgress(snapshot: LearnerSnapshot, opts: { now: number; demoMode?: boolean }): ProgressData {
  const attempts = [...snapshot.attempts].sort((a, b) => a.endedAt - b.endedAt)

  const shown: SkillId[] = snapshot.skills.custom ? [...BUILTIN_SKILL_IDS, 'custom'] : [...BUILTIN_SKILL_IDS]
  const skills: SkillProgress[] = shown.map((id) => {
    const s = snapshot.skills[id] as LearnerSnapshot['skills'][SkillId] & object
    const mine = attempts.filter((a) => a.skillId === id)
    return {
      skillId: id,
      name: SKILLS[id].name,
      level: s.level,
      levelLabel: LEVEL_LABEL[s.level],
      mode: modeFor(s.level, s.lastSeen !== null || mine.length > 0),
      lastPractised: s.lastSeen,
      nextReview: s.nextReview,
      reviewDue: s.nextReview !== null && s.nextReview <= opts.now,
      attempts: mine.length,
      mastered: isMastered(s, opts.demoMode ?? true),
    }
  })

  const canDoNow: CanDoItem[] = []
  for (const sk of skills) {
    const done = attempts.filter((a) => a.skillId === sk.skillId && a.completed)
    if (!done.length || sk.mode === 'not_started') continue
    canDoNow.push({ skillId: sk.skillId, text: SKILLS[sk.skillId].canDo, mode: sk.mode, since: done[0].endedAt })
  }

  const hintsPerTask = SKILL_IDS.map((id) => ({
    skillId: id,
    name: SKILLS[id].name,
    series: attempts
      .filter((a) => a.skillId === id)
      .map<HintPoint>((a, i) => ({ attempt: i + 1, at: a.endedAt, hints: a.hintsUsed, errors: a.errors, stalls: a.stalls, level: a.levelAtStart, clean: a.clean })),
  })).filter((s) => s.series.length > 0)

  // Compare like with like: the skill practised most often (ties go to the earlier skill in the list).
  const focus = [...hintsPerTask].sort((a, b) => b.series.length - a.series.length)[0]
  const first = focus?.series[0]
  const latest = focus?.series[focus.series.length - 1]
  const enough = !!focus && focus.series.length >= 2
  const trend: ProgressData['overall']['trend'] =
    !enough || !first || !latest ? 'not_enough_data' : latest.hints < first.hints ? 'down' : latest.hints > first.hints ? 'up' : 'flat'
  const headline =
    !first || !latest
      ? 'Nothing practised yet.'
      : !enough
        ? `Your first practice needed ${plural(first.hints, 'hint')}. Do one more and we can compare.`
        : trend === 'down'
          ? `You needed ${plural(first.hints, 'hint')} on your first task and ${plural(latest.hints, 'hint')} on your latest.`
          : trend === 'flat'
            ? `You needed ${plural(latest.hints, 'hint')} on your first task and on your latest.`
            : `Your latest task needed ${plural(latest.hints, 'hint')}, up from ${first.hints}. That is fine: harder tasks need more help.`

  const confidencePoints = [...snapshot.confidenceLog].sort((a, b) => a.at - b.at)

  // Suggestions are built-in lessons; "something new" is whatever the learner asks for next.
  const builtins = skills.filter((s) => s.skillId !== 'custom')
  const due = builtins.filter((s) => s.reviewDue).sort((a, b) => (a.nextReview ?? 0) - (b.nextReview ?? 0))[0]
  const untried = builtins.find((s) => s.attempts === 0 && s.mode === 'not_started')
  const lowest = [...builtins].filter((s) => !s.mastered).sort((a, b) => a.level - b.level)[0]
  const nextSuggested: ProgressData['nextSuggested'] = due
    ? { skillId: due.skillId, reason: 'A quick refresher is due.' }
    : untried
      ? { skillId: untried.skillId, reason: 'Something new to try.' }
      : lowest
        ? { skillId: lowest.skillId, reason: 'The one with the most room to grow.' }
        : null

  const doneTotal = Object.values(snapshot.doneForMe ?? {}).reduce((a, b) => a + b, 0)

  return {
    generatedAt: opts.now,
    skills,
    canDoNow,
    confidence: {
      points: confidencePoints.map((p) => ({ at: p.at, skillId: p.skillId, rating: p.rating })),
      first: confidencePoints[0]?.rating ?? null,
      latest: confidencePoints[confidencePoints.length - 1]?.rating ?? null,
    },
    hintsPerTask,
    overall: { attempts: attempts.length, firstAttemptHints: first?.hints ?? null, latestAttemptHints: latest?.hints ?? null, trend, headline },
    nextSuggested,
    ...(doneTotal > 0 ? { doneForMe: { total: doneTotal, text: `Done for you: ${doneTotal} time${doneTotal === 1 ? '' : 's'}. Ask to be shown and you will need this less.` } } : {}),
  }
}
