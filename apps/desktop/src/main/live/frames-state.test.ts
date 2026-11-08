import { describe, expect, it } from 'vitest'
import { FRAMES_BACK_LINE, FRAMES_MODEL_REASON, FRAMES_PROBLEM, MAX_FRAMES_LINES, createFramesTracker, framesLostLine, isFramesReason } from './frames-state'
import { problemFromNotice } from './manager'
import { INFO_CARDS, infoCardFor } from '../wake/texts'

describe('what is said when frames are wanted and the screen cannot be seen', () => {
  it('the line for the model is one short sentence with one closed reason, never anything from the screen', () => {
    expect(framesLostLine('denylisted_app')).toBe('You cannot see the screen right now: a private app is in front. Say so and give spoken guidance only.')
    for (const [r, why] of Object.entries(FRAMES_MODEL_REASON)) {
      const line = framesLostLine(r as never)
      expect(line).toContain(why)
      expect(line.split(/\s+/).length).toBeLessThanOrEqual(24)
      expect(line).not.toMatch(/mock|demo|sample|synthetic|example/i)
    }
  })

  it('the card is said once per conversation; the model is told for each new reason (at most three times) and told when it can see again', () => {
    const t = createFramesTracker()
    expect(t.lost('denylisted_app')).toEqual({ notice: 'denylisted_app', tell: framesLostLine('denylisted_app') })
    expect(t.lost('denylisted_app')).toEqual({ notice: null, tell: null }) // same reason: nothing more
    expect(t.lost('secure_input')).toEqual({ notice: null, tell: framesLostLine('secure_input') }) // no second card
    expect(t.back()).toBe(FRAMES_BACK_LINE)
    expect(t.back()).toBeNull()
    expect(t.lost('locked').tell).toBe(framesLostLine('locked'))
    expect(t.lost('stale').tell).toBeNull() // the third line was used up
    expect(MAX_FRAMES_LINES).toBe(3)
    expect(t.back()).toBe(FRAMES_BACK_LINE) // the model still thinks it cannot see
  })

  it('a kill, an agent acting, no consent and a missing ledger are not "cannot see" reasons, and unknown words are ignored', () => {
    const t = createFramesTracker()
    for (const r of ['killed', 'unattended', 'no_consent', 'ledger_unavailable', 'anything']) expect(t.lost(r)).toEqual({ notice: null, tell: null })
    expect(t.unavailable()).toBeNull()
    expect(isFramesReason('screen_recording_missing')).toBe(true)
    expect(isFramesReason('killed')).toBe(false)
  })

  it('a permission refusal counts at once; an empty capture counts only the second time in a row, and a good frame starts the count again', () => {
    const t = createFramesTracker()
    expect(t.miss(true)).toBe('screen_recording_missing')
    const u = createFramesTracker()
    expect(u.miss(false)).toBeNull()
    expect(u.miss(false)).toBe('capture_failed')
    const v = createFramesTracker()
    expect(v.miss(false)).toBeNull()
    v.clearMisses()
    expect(v.miss(false)).toBeNull()
  })

  it('every reason has a closed problem code that the manager maps and a card that says it in plain words', () => {
    for (const [reason, code] of Object.entries(FRAMES_PROBLEM)) {
      expect(problemFromNotice({ kind: 'frames', reason })).toBe(code)
      const card = infoCardFor(code)
      expect(card, code).not.toBeNull()
      expect(`${card?.title} ${card?.body}`).not.toMatch(/mock|demo|sample|synthetic|example|UNDERSTUDY_|GEMINI_/i)
    }
    expect(problemFromNotice({ kind: 'frames', reason: 'killed' })).toBeNull()
    expect(problemFromNotice({ kind: 'frames', reason: 'made_up' })).toBeNull()
    // The screen card for a missing permission offers the ask-first button (the same treatment as the microphone), and says to reopen Knack.
    expect(INFO_CARDS.screen_missing.buttons.map((b) => b.label)).toEqual(['Allow screen help', 'Close'])
    expect(INFO_CARDS.screen_missing.action).toBe('screen_ask')
    expect(INFO_CARDS.screen_missing.body).toContain('reopen Knack')
    // The others say talking still works, and need no button.
    for (const code of ['screen_secure_input', 'screen_private_app', 'screen_locked', 'screen_shared', 'screen_stale']) expect(INFO_CARDS[code].action).toBeNull()
  })
})
