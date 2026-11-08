import { describe, expect, it } from 'vitest'
import { ASK_CARD, ASK_MAX_HEIGHT, ASK_MAX_TEXT, ASK_PAD, askBarBounds, askUnavailableLine, askWindowHeight, cleanAsk, keyLabel } from './ask-ipc'

const wa = { x: 0, y: 25, width: 1440, height: 875 }

describe('where the bar goes', () => {
  it('is centred across the work area and its card starts a fifth of the way down (the upper third)', () => {
    const b = askBarBounds(wa, ASK_CARD.height + 2 * ASK_PAD)
    expect(b.width).toBe(ASK_CARD.width + 2 * ASK_PAD)
    expect(b.x + ASK_PAD + ASK_CARD.width / 2).toBe(wa.x + wa.width / 2)
    const cardTop = b.y + ASK_PAD
    expect(cardTop).toBe(Math.round(wa.y + wa.height * 0.2))
    expect(cardTop).toBeLessThan(wa.y + wa.height / 3)
  })
  it('follows a second display at an offset', () => {
    const second = { x: 1440, y: 0, width: 1920, height: 1080 }
    const b = askBarBounds(second, 80)
    expect(b.x + ASK_PAD + ASK_CARD.width / 2).toBe(second.x + second.width / 2)
    expect(b.y).toBeGreaterThanOrEqual(second.y)
  })
})

describe('the height the page may ask for', () => {
  it('adds the padding to a card height inside the limits and refuses anything else', () => {
    expect(askWindowHeight(64)).toBe(64 + 2 * ASK_PAD)
    expect(askWindowHeight(100.2)).toBe(101 + 2 * ASK_PAD)
    for (const bad of [10, ASK_MAX_HEIGHT + 1, NaN, Infinity, '80', null, undefined]) expect(askWindowHeight(bad)).toBeNull()
  })
})

describe('what is typed', () => {
  it('becomes one trimmed line, cut at the limit, and nothing when empty or not text', () => {
    expect(cleanAsk('  open the\n calculator   please ')).toBe('open the calculator please')
    expect(cleanAsk('x'.repeat(ASK_MAX_TEXT + 40))).toHaveLength(ASK_MAX_TEXT)
    for (const bad of ['', '   \n ', 7, null, undefined, {}, ['a']]) expect(cleanAsk(bad)).toBeNull()
  })
})

describe('the sentence when typing cannot be answered', () => {
  it('says what to do, with the talk key as people say it', () => {
    expect(keyLabel('Alt+Space')).toBe('Option-Space')
    expect(keyLabel('CommandOrControl+Shift+T')).toBe('Command-Shift-T')
    expect(askUnavailableLine('Alt+Space')).toBe('Typing is not on yet. Hold Option-Space and speak.')
  })
  it('never says demo or mock', () => {
    expect(askUnavailableLine('Alt+Space')).not.toMatch(/demo|mock/i)
  })
})
