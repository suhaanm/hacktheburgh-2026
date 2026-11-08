import { describe, expect, it } from 'vitest'
import { CARD_INSET, STACK_GAP, cardBounds, cardWorkArea, isRealMouseClick } from './card-ipc'

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

describe('stacking above the Knack corner column', () => {
  const wa = { x: 0, y: 25, width: 1440, height: 875 }
  const column = { x: 1100, y: 840, width: 324, height: 44 } // the pill, bottom-right
  it('with the column showing, the card sits 8 px above it instead of over it', () => {
    const b = cardBounds(wa, { w: 348, h: 150 }, undefined, column)
    expect(b.y + b.height).toBe(column.y - STACK_GAP)
    expect(b.y + b.height).toBeLessThan(column.y)
    expect(b.x).toBe(1440 - 348 - CARD_INSET)
  })
  it('without it the card keeps its place in the corner', () => {
    expect(cardBounds(wa, { w: 348, h: 150 }, undefined, null)).toEqual(cardBounds(wa, { w: 348, h: 150 }))
  })
  it('a column higher than the corner does not push the card below the corner, and nothing goes above the work area', () => {
    const low = cardBounds(wa, { w: 348, h: 150 }, undefined, { ...column, y: 950 })
    expect(low.y + low.height).toBe(25 + 875 - CARD_INSET) // the column is below the card's home: the home stays
    expect(cardBounds(wa, { w: 348, h: 150 }, undefined, { ...column, y: 100 }).y).toBe(wa.y)
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

describe('which display a stacked card goes to', () => {
  const first = { x: 0, y: 33, width: 1728, height: 999 }
  const second = { x: 1728, y: -155, width: 1920, height: 1055 }
  const displays = [{ workArea: first }, { workArea: second }]
  it('the display that holds the column, even when the pointer is on another one', () => {
    const column = { x: 3365, y: 840, width: 267, height: 44 }
    expect(cardWorkArea(displays, column, first)).toEqual(second)
    // the card then stacks above the column and never floats in the middle of the first display
    const b = cardBounds(cardWorkArea(displays, column, first), { w: 348, h: 150 }, undefined, column)
    expect(b.x).toBeGreaterThanOrEqual(second.x)
    expect(b.y + b.height + STACK_GAP).toBeLessThanOrEqual(column.y)
  })
  it('with no column, or one that is on no display, the pointer display', () => {
    expect(cardWorkArea(displays, null, second)).toEqual(second)
    expect(cardWorkArea(displays, { x: 99999, y: 0, width: 10, height: 10 }, first)).toEqual(first)
  })
})
