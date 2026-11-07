// Pure text helpers for the learner profile (profile.md). Every edit is a minimal change to the file text, so
// anything we do not understand (unknown sections, tables, the learner's own words) is carried over untouched.

export type ListKey = 'about' | 'goals' | 'whatWorks' | 'jargon' | 'safety' | 'sharing'
type MachineKey = 'skills' | 'confidence' | 'attempts' | 'lastSession'
export type SectionKey = ListKey | MachineKey | 'other'

const MATCHERS: { key: Exclude<SectionKey, 'other'>; heading: string; match: RegExp }[] = [
  { key: 'about', heading: 'About me & accessibility', match: /^about me|^about\b|^accessib/ },
  { key: 'goals', heading: 'Goals', match: /^goals?\b|^what i want/ },
  { key: 'skills', heading: 'Skills', match: /^skills?\b/ },
  { key: 'confidence', heading: 'Confidence log', match: /^confidence/ },
  { key: 'attempts', heading: 'Attempt history', match: /^attempt/ },
  { key: 'whatWorks', heading: 'What works for me', match: /^what works/ },
  { key: 'jargon', heading: 'Jargon to avoid', match: /^jargon/ },
  { key: 'safety', heading: 'Safety notes', match: /^safety/ },
  { key: 'sharing', heading: 'Who can see what', match: /^who can see|^sharing|^privacy/ },
  { key: 'lastSession', heading: 'Last session', match: /^last session/ },
]

export interface ProfileLine {
  /** Zero-based line number in the file. */
  index: number
  text: string
}

export interface ProfileSection {
  key: SectionKey
  heading: string
  /** Zero-based line number of the `## heading` line. */
  headingIndex: number
  lines: ProfileLine[]
}

const BULLET = /^\s*[-*]\s+(.*\S)\s*$/
const HEADING = /^##\s+(.*?)\s*$/

function classify(heading: string): SectionKey {
  const h = heading.trim().toLowerCase()
  return MATCHERS.find((m) => m.match.test(h))?.key ?? 'other'
}

export function parseProfile(markdown: string): ProfileSection[] {
  const sections: ProfileSection[] = []
  markdown.split('\n').forEach((line, index) => {
    const h = HEADING.exec(line)
    if (h) {
      sections.push({ key: classify(h[1]!), heading: h[1]!, headingIndex: index, lines: [] })
      return
    }
    const b = BULLET.exec(line)
    const current = sections[sections.length - 1]
    if (b && current) current.lines.push({ index, text: b[1]! })
  })
  return sections
}

/** Plain-words notes only: one line, no markdown markers, short. */
export function cleanNote(raw: string): string | null {
  const text = raw.replace(/\s+/g, ' ').replace(/^[-*#>|\s]+/, '').trim().slice(0, 160)
  return text.length > 0 ? text : null
}

export function removeLines(markdown: string, indices: readonly number[]): string {
  const drop = new Set(indices)
  return markdown
    .split('\n')
    .filter((_, i) => !drop.has(i))
    .join('\n')
}

export function addLine(markdown: string, key: ListKey, text: string): string {
  const lines = markdown.split('\n')
  const start = lines.findIndex((l) => {
    const h = HEADING.exec(l)
    return h !== null && classify(h[1]!) === key
  })
  if (start === -1) {
    const heading = MATCHERS.find((m) => m.key === key)!.heading
    const body = markdown.endsWith('\n') ? markdown : `${markdown}\n`
    return `${body}\n## ${heading}\n\n- ${text}\n`
  }
  let end = lines.length
  for (let i = start + 1; i < lines.length; i++) {
    if (HEADING.test(lines[i]!)) {
      end = i
      break
    }
  }
  let last = start
  for (let i = start + 1; i < end; i++) if (lines[i]!.trim() !== '') last = i
  lines.splice(last + 1, 0, ...(last === start ? ['', `- ${text}`] : [`- ${text}`]))
  return lines.join('\n')
}

export function blankProfile(): string {
  return [
    '# My Alongside profile',
    '',
    '> This file is yours. Read it, change it, or delete any line and Alongside will follow what it says here.',
    '> Times are UTC. Say "forget that" and the last thing written down is removed.',
    '',
  ].join('\n')
}

export const SECTION_COPY: Readonly<Partial<Record<SectionKey, { title: string; hint: string }>>> = {
  about: { title: 'About me', hint: 'Your name, and anything that makes the screen hard to use.' },
  goals: { title: 'What I want to do', hint: 'I teach toward these.' },
  whatWorks: { title: 'What works for me', hint: 'Ways of explaining that helped.' },
  jargon: { title: 'Words to avoid', hint: 'I use plain words instead.' },
  safety: { title: 'Safety notes', hint: 'Things I should always watch for.' },
  other: { title: 'Other notes', hint: 'Kept exactly as you wrote them.' },
}

/** Sections the learner can add to and forget from, in display order. */
export const EDITABLE_KEYS: readonly ListKey[] = ['about', 'goals', 'whatWorks', 'jargon', 'safety']
