import { describe, expect, it } from 'vitest'
import { addLine, blankProfile, cleanNote, parseProfile, removeLines } from './profile'

const sample = `# My Alongside profile

> This file is yours.

## About me & accessibility

## Goals

- See my granddaughter Lily on a video call

## Skills

| Skill | Level |
|---|---|
| Start a video call | 2 |

## What works for me

- Comparing the contacts list to a phone book helped
- Being asked what I would try before being told

## Who can see what

- Nobody sees anything unless you switch on carer sharing in Settings.

## Hobbies

- Gardening

## Last session

- yesterday · Start a video call · Found the button.
`

describe('profile text helpers', () => {
  it('reads sections and bullet lines, ignoring tables', () => {
    const s = parseProfile(sample)
    expect(s.map((x) => x.key)).toEqual(['about', 'goals', 'skills', 'whatWorks', 'sharing', 'other', 'lastSession'])
    expect(s.find((x) => x.key === 'goals')!.lines.map((l) => l.text)).toEqual(['See my granddaughter Lily on a video call'])
    expect(s.find((x) => x.key === 'skills')!.lines).toEqual([])
    expect(s.find((x) => x.key === 'other')!.lines[0]!.text).toBe('Gardening')
  })

  it('forgets exactly the chosen lines and nothing else', () => {
    const works = parseProfile(sample).find((x) => x.key === 'whatWorks')!
    const out = removeLines(sample, [works.lines[0]!.index])
    expect(out).not.toContain('phone book')
    expect(out).toContain('Being asked what I would try')
    expect(out.split('\n').length).toBe(sample.split('\n').length - 1)
  })

  it('forgets a whole section', () => {
    const works = parseProfile(sample).find((x) => x.key === 'whatWorks')!
    const out = removeLines(sample, works.lines.map((l) => l.index))
    expect(parseProfile(out).find((x) => x.key === 'whatWorks')!.lines).toEqual([])
    expect(out).toContain('## Who can see what')
  })

  it('adds a line to a populated section, an empty one, and a missing one', () => {
    const a = addLine(sample, 'goals', 'Send photos')
    expect(parseProfile(a).find((x) => x.key === 'goals')!.lines.map((l) => l.text)).toEqual(['See my granddaughter Lily on a video call', 'Send photos'])
    const b = addLine(sample, 'about', 'Call me Peggy')
    expect(parseProfile(b).find((x) => x.key === 'about')!.lines.map((l) => l.text)).toEqual(['Call me Peggy'])
    expect(b).toContain('## About me & accessibility\n\n- Call me Peggy\n')
    const c = addLine(sample, 'safety', 'Never read out card numbers')
    expect(parseProfile(c).find((x) => x.key === 'safety')!.lines.map((l) => l.text)).toEqual(['Never read out card numbers'])
  })

  it('keeps everything it does not understand', () => {
    const out = addLine(sample, 'goals', 'x')
    expect(out).toContain('| Start a video call | 2 |')
    expect(out).toContain('- Gardening')
  })

  it('cleans notes into one plain line', () => {
    expect(cleanNote('  ## - Call me   Peggy\n')).toBe('Call me Peggy')
    expect(cleanNote('   ')).toBeNull()
    expect(cleanNote('a'.repeat(300))!.length).toBe(160)
  })

  it('a blank profile has no sections', () => {
    expect(parseProfile(blankProfile())).toEqual([])
  })
})
