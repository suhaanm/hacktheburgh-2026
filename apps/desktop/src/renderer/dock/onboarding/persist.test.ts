import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { levelEngine } from '../../../main/teaching/levels'
import { PROFILE_FILE, TeachingLearnerStore } from '../../../main/teaching/learner-store'
import type { MarkdownEditRequest, MarkdownEditResult } from '../../../shared/protocol'
import { parseProfile } from '../profile'
import { initialAnswers, profileLines, reduce, startFlow } from './flow'
import { applyProfileLines, finishOnboarding, saveProfileLines, type PersistApi } from './persist'
import type { OnboardingSettingsPatch } from './flow'

let dir: string
beforeEach(() => {
  dir = fs.mkdtempSync(path.join(os.tmpdir(), 'alongside-onboard-'))
})
afterEach(() => fs.rmSync(dir, { recursive: true, force: true }))

const makeStore = (): TeachingLearnerStore =>
  new TeachingLearnerStore({ dir, now: () => Date.UTC(2026, 9, 31, 14), engine: levelEngine, getSettings: () => ({ demoMode: true, helpLevelMode: 'auto', carerSharing: false }) })

// Fake IPC in front of the real learner store, recording settings patches.
function fakeApi(store: TeachingLearnerStore, before?: (req: MarkdownEditRequest) => Promise<void>) {
  const patches: OnboardingSettingsPatch[] = []
  const api: PersistApi = {
    patchSettings: async (patch) => void patches.push(patch),
    learnerMarkdown: async (req): Promise<MarkdownEditResult> => {
      await before?.(req)
      return store.editMarkdown(req)
    },
  }
  return { api, patches }
}

const answered = () =>
  reduce(startFlow(initialAnswers({}, 'marcus')), {
    type: 'set',
    patch: { userName: 'Peggy', topics: ['calls', 'photos'], comfort: 2, pacing: 'gentle', dyslexiaFont: true, theme: 'dark', glass: true, glassOpacity: 0.6, agency: 'ask_each' },
  })

describe('applyProfileLines', () => {
  it('replaces what a previous run wrote and keeps everything else, including the learner\'s own words', () => {
    const base = ['# My Alongside profile', '', '## About me & accessibility', '', '- Call me Peg', '- I get anxious when a window pops up', '', '## Goals', '', '- I want help with photos', '- Learn to use my new tablet', '', '## Notes I wrote', '', '- Keep this', ''].join('\n')
    const s = answered()
    const out = applyProfileLines(base, profileLines(s.answers, s.touched))
    const sections = parseProfile(out)
    const about = sections.find((x) => x.key === 'about')!.lines.map((l) => l.text)
    const goals = sections.find((x) => x.key === 'goals')!.lines.map((l) => l.text)
    expect(about).toContain('Call me Peggy')
    expect(about).not.toContain('Call me Peg')
    expect(about).toContain('I get anxious when a window pops up')
    expect(goals).toEqual(['Learn to use my new tablet', 'I want help with video calls', 'I want help with photos'])
    expect(out).toContain('## Notes I wrote')
    expect(out).toContain('- Keep this')
  })

  it('does not pile up blank lines when a re-run changes answers', () => {
    const a = answered()
    const first = applyProfileLines('# My Alongside profile\n', profileLines(a.answers, a.touched))
    const b = reduce(a, { type: 'set', patch: { topics: ['shopping'], textScale: 1.5 } })
    const second = applyProfileLines(first, profileLines(b.answers, b.touched))
    expect(second).not.toMatch(/\n{3,}/)
    expect(second).toContain('I want help with shopping')
    expect(second).not.toContain('I want help with video calls')
  })

  it('is idempotent: running twice changes nothing', () => {
    const s = answered()
    const lines = profileLines(s.answers, s.touched)
    const once = applyProfileLines('# My Alongside profile\n', lines)
    expect(applyProfileLines(once, lines)).toBe(once)
  })
})

describe('saving into the real learner store', () => {
  it('writes the About / What I want to do / What works sections and the file is accepted', async () => {
    const store = makeStore()
    const { api } = fakeApi(store)
    const s = answered()
    expect(await saveProfileLines(api, profileLines(s.answers, s.touched))).toBe(true)
    const text = fs.readFileSync(path.join(dir, PROFILE_FILE), 'utf8')
    expect(text).toContain('- Call me Peggy')
    expect(text).toContain('- I want help with video calls')
    expect(text).toContain('- Gentle and slow help works for me')
    expect(text).toContain('- I find a dyslexia-friendly font easier to read')
  })

  it('survives a stale revision: re-reads the latest and keeps the note written in between', async () => {
    const store = makeStore()
    let interfered = false
    const { api } = fakeApi(store, async (req) => {
      if (req.op === 'write' && !interfered) {
        interfered = true
        await store.addNote('I find small text hard to read')
      }
    })
    const s = answered()
    expect(await saveProfileLines(api, profileLines(s.answers, s.touched))).toBe(true)
    const text = fs.readFileSync(path.join(dir, PROFILE_FILE), 'utf8')
    expect(text).toContain('I find small text hard to read')
    expect(text).toContain('- Call me Peggy')
  })

  it('gives up after repeated conflicts without writing partial data', async () => {
    const store = makeStore()
    const api: PersistApi = {
      patchSettings: async () => undefined,
      learnerMarkdown: async (req) => {
        const latest = await store.editMarkdown({ op: 'read' })
        return req.op === 'read' ? latest : { ok: false, conflict: true, content: latest.content, revision: latest.revision }
      },
    }
    const s = answered()
    expect(await saveProfileLines(api, profileLines(s.answers, s.touched))).toBe(false)
    expect(fs.existsSync(path.join(dir, PROFILE_FILE)) ? fs.readFileSync(path.join(dir, PROFILE_FILE), 'utf8') : '').not.toContain('Peggy')
  })

  it('does not touch the profile at all when nothing was answered', async () => {
    const store = makeStore()
    let calls = 0
    const { api } = fakeApi(store, async () => void calls++)
    const s = startFlow(initialAnswers({}, 'marcus'))
    expect(await saveProfileLines(api, profileLines(s.answers, s.touched))).toBe(true)
    expect(calls).toBe(0)
  })
})

describe('finishOnboarding', () => {
  it('writes the profile, then marks onboarding done with exactly the answers given', async () => {
    const store = makeStore()
    const { api, patches } = fakeApi(store)
    const s = answered()
    const res = await finishOnboarding(api, s.answers, s.touched)
    expect(res.profileSaved).toBe(true)
    const last = patches.at(-1)!
    expect(last.onboardingDone).toBe(true)
    expect(last).toMatchObject({ userName: 'Peggy', theme: 'dark', glass: true, glassOpacity: 0.6, agency: 'ask_each', dyslexiaFont: true })
    expect(last).not.toHaveProperty('persona')
    expect(last).not.toHaveProperty('filesEnabled')
  })

  it('skipping with nothing answered only sets onboardingDone', async () => {
    const store = makeStore()
    const { api, patches } = fakeApi(store)
    const s = startFlow(initialAnswers({}, 'marcus'))
    await finishOnboarding(api, s.answers, s.touched)
    expect(patches).toEqual([{ onboardingDone: true }])
  })

  it('still finishes when the profile cannot be written', async () => {
    const patches: OnboardingSettingsPatch[] = []
    const api: PersistApi = {
      patchSettings: async (p) => void patches.push(p),
      learnerMarkdown: async () => {
        throw new Error('disk full')
      },
    }
    const s = answered()
    const res = await finishOnboarding(api, s.answers, s.touched)
    expect(res.profileSaved).toBe(false)
    expect(patches.at(-1)!.onboardingDone).toBe(true)
  })
})
