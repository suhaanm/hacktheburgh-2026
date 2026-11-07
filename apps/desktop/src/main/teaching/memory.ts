// The "memory callback": one warm, concrete line about last time, built from the learner snapshot. Pure.
import type { LearnerSnapshot, SkillId, SkillState } from '../../shared/protocol'
import { DAY_MS } from './levels'
import { SKILLS } from './skills/definitions'

export function describeWhen(at: number, now: number): string {
  const ms = now - at
  if (ms < 0) return 'recently'
  const startOfDay = (t: number): number => Math.floor(t / DAY_MS)
  const days = startOfDay(now) - startOfDay(at)
  if (days <= 0) return 'earlier today'
  if (days === 1) return 'yesterday'
  if (days < 7) return `${days} days ago`
  if (days < 14) return 'last week'
  return `${Math.round(days / 7)} weeks ago`
}

function plainSkill(id: SkillId | undefined): string {
  return id ? SKILLS[id].name.toLowerCase() : 'something new'
}

// Returns null when there is nothing honest to say (first ever session).
export function memoryCallback(snapshot: LearnerSnapshot, now: number): string | null {
  const last = snapshot.lastSession
  if (!last) return null
  const when = describeWhen(last.at, now)
  const hint = snapshot.whatWorks[snapshot.whatWorks.length - 1]
  const tail = hint ? ` Something that helped: ${hint}.` : ''
  const lead = last.skillId && last.skillId !== 'custom' ? `${when.charAt(0).toUpperCase()}${when.slice(1)} you practised "${plainSkill(last.skillId)}".` : `${when.charAt(0).toUpperCase()}${when.slice(1)}:`
  return `${lead} ${last.summary}${tail}`.replace(/\s+/g, ' ').trim()
}

// "Remember" nudge for a skill that is due for review.
export function reviewNudge(snapshot: LearnerSnapshot, now: number): { skillId: SkillId; text: string } | null {
  let best: { skillId: SkillId; due: number } | null = null
  for (const [id, s] of Object.entries(snapshot.skills) as [SkillId, SkillState | undefined][]) {
    if (s && s.nextReview !== null && s.nextReview <= now && (!best || s.nextReview < best.due)) best = { skillId: id, due: s.nextReview }
  }
  if (!best) return null
  return { skillId: best.skillId, text: `A quick refresher on "${plainSkill(best.skillId)}" is due. Offer it, don't insist.` }
}
