import { describe, expect, it } from 'vitest'
import { CARD_INSET, cardBounds, isRealMouseClick } from './card-ipc'

describe('where the card goes', () => {
  it('bottom-right of the work area, 16 px in, on whichever display it is given', () => {
    expect(cardBounds({ x: 0, y: 25, width: 1440, height: 875 }, { w: 348, h: 150 })).toEqual({ x: 1440 - 348 - CARD_INSET, y: 25 + 875 - 150 - CARD_INSET, width: 348, height: 150 })
    // a second display to the left and above: the card follows its work area, not the primary one
    expect(cardBounds({ x: -1920, y: -200, width: 1920, height: 1055 }, { w: 348, h: 150 })).toEqual({ x: -348 - CARD_INSET, y: -200 + 1055 - 150 - CARD_INSET, width: 348, height: 150 })
  })
  it('a card taller than the area is cut to stay on it', () => {
    const b = cardBounds({ x: 0, y: 0, width: 400, height: 300 }, { w: 500, h: 900 })
    expect(b.width).toBe(368)
    expect(b.height).toBe(268)
    expect(b.x).toBeGreaterThanOrEqual(0)
    expect(b.y).toBeGreaterThanOrEqual(0)
  })
})

describe('a real mouse click', () => {
  it('needs the browser to have produced it, from a mouse, with a click count, on the main button', () => {
    expect(isRealMouseClick({ isTrusted: true, detail: 1, pointerType: 'mouse', button: 0 })).toBe(true)
    expect(isRealMouseClick({ isTrusted: false, detail: 1, pointerType: 'mouse', button: 0 })).toBe(false) // a script
    expect(isRealMouseClick({ isTrusted: true, detail: 0, pointerType: '', button: 0 })).toBe(false) // Enter or Space on a focused button
    expect(isRealMouseClick({ isTrusted: true, detail: 1, pointerType: 'touch', button: 0 })).toBe(false)
    expect(isRealMouseClick({ isTrusted: true, detail: 1, pointerType: 'mouse', button: 2 })).toBe(false)
  })
})
