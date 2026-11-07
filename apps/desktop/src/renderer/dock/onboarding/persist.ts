// Saving what the person told us. Preferences go through the settings patch; the get-to-know-you answers go into
// their own profile.md (revision-safe, so anything they edited or the assistant wrote is never overwritten).
import type { MarkdownEditRequest, MarkdownEditResult } from '../../../shared/protocol'
import { addLine, parseProfile, removeLines, type ListKey } from '../profile'
import { answersToSettings, hasProfileLines, isOwnedLine, profileLines, type Answers, type OnboardingSettingsPatch, type ProfileLines, type Touched } from './flow'

export interface PersistApi {
  patchSettings(patch: OnboardingSettingsPatch): Promise<unknown>
  learnerMarkdown(req: MarkdownEditRequest): Promise<MarkdownEditResult>
}

const SECTION_FOR: Readonly<Record<keyof ProfileLines, ListKey>> = { about: 'about', goals: 'goals', whatWorks: 'whatWorks' }
const MAX_ATTEMPTS = 3

/** Replaces the lines a previous run wrote and adds the new ones; every other line and section is carried over untouched. */
export function applyProfileLines(markdown: string, lines: ProfileLines): string {
  const owned: number[] = []
  const present: Record<keyof ProfileLines, string[]> = { about: [], goals: [], whatWorks: [] }
  for (const section of parseProfile(markdown)) {
    if (section.key !== 'about' && section.key !== 'goals' && section.key !== 'whatWorks') continue
    for (const line of section.lines) {
      if (!isOwnedLine(line.text)) continue
      owned.push(line.index)
      present[section.key].push(line.text.trim())
    }
  }
  const same = (a: string[], b: string[]): boolean => a.length === b.length && [...a].sort().join('\n') === [...b].sort().join('\n')
  if (same(present.about, lines.about) && same(present.goals, lines.goals) && same(present.whatWorks, lines.whatWorks)) return markdown
  let out = owned.length > 0 ? removeLines(markdown, owned) : markdown

  const have = new Set(
    parseProfile(out)
      .filter((s) => s.key === 'about' || s.key === 'goals' || s.key === 'whatWorks')
      .flatMap((s) => s.lines.map((l) => `${s.key}:${l.text.trim().toLowerCase()}`)),
  )
  for (const field of ['about', 'goals', 'whatWorks'] as const) {
    for (const text of lines[field]) {
      const key = SECTION_FOR[field]
      if (have.has(`${key}:${text.toLowerCase()}`)) continue
      out = addLine(out, key, text)
    }
  }
  // Removing and re-adding lines leaves empty ones behind; keep the file tidy for the person who reads it.
  return out.replace(/\n{3,}/g, '\n\n')
}

/** Reads, applies, writes with the revision just read. A stale revision returns the latest text, so we re-apply to that. */
export async function saveProfileLines(api: PersistApi, lines: ProfileLines): Promise<boolean> {
  if (!hasProfileLines(lines)) return true
  let current = await api.learnerMarkdown({ op: 'read' })
  for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
    const next = applyProfileLines(current.content, lines)
    if (next === current.content) return true
    const result = await api.learnerMarkdown({ op: 'write', content: next, revision: current.revision })
    if (result.ok) return true
    if (!result.conflict) return false
    current = result
  }
  return false
}

export interface FinishResult {
  profileSaved: boolean
}

/** Always marks onboarding done, even if the profile cannot be written, so a broken disk never traps the person in setup. */
export async function finishOnboarding(api: PersistApi, answers: Answers, touched: Touched): Promise<FinishResult> {
  let profileSaved = false
  try {
    profileSaved = await saveProfileLines(api, profileLines(answers, touched))
  } catch {
    profileSaved = false
  }
  const given = Object.fromEntries((Object.keys(touched) as (keyof Answers)[]).map((key) => [key, answers[key]])) as Partial<Answers>
  await api.patchSettings({ ...answersToSettings(given), onboardingDone: true })
  return { profileSaved }
}
