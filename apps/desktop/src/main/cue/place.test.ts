import { describe, expect, it } from 'vitest'
import { CARD_SIDES, CHIP_SIDES, overlapArea, placePanel, placeWindow, PANEL_PAD, type Rect } from './place'
import { CUE_TOKENS } from './tokens'

const work: Rect = { x: 0, y: 25, w: 1440, h: 800 }
const target: Rect = { x: 500, y: 400, w: 140, h: 46 }
const air = CUE_TOKENS.placement.contentAir

// A page: a line of text just under the target, one just above it, and some to the left. Free space to the right.
const page: Rect[] = [
  { x: 490, y: 452, w: 200, h: 18 }, // a label right under the target
  { x: 490, y: 360, w: 200, h: 18 }, // a label right above it
  { x: 100, y: 380, w: 380, h: 120 }, // a block of text to its left
]

describe('placement beside the page content', () => {
  it('nothing known about the page: the chip sits below the target, the card docks in a bottom corner above the Dock', () => {
    const chip = placePanel({ w: 200, h: 26 }, target, work, { kind: 'chip' })
    expect(chip.side).toBe('below')
    expect(chip.freeExists).toBeNull()
    const card = placePanel({ w: 280, h: 190 }, target, work, { kind: 'card' })
    expect(card.side).toBe('corner')
    expect(card.rect.y + card.rect.h).toBe(work.y + work.h - CUE_TOKENS.placement.margin)
    // The nearer corner first: the target is on the left half of a 1440-wide screen.
    expect(card.rect.x).toBe(CUE_TOKENS.placement.margin)
    // And on the other side when the target is on the right.
    expect(placePanel({ w: 280, h: 190 }, { ...target, x: 1100 }, work, { kind: 'card' }).rect.x + 280).toBe(1440 - CUE_TOKENS.placement.margin)
  })

  it('a docked card never sits on the target, even when the target is in that corner', () => {
    const inCorner: Rect = { x: 20, y: 700, w: 160, h: 90 }
    const card = placePanel({ w: 280, h: 190 }, inCorner, work, { kind: 'card' })
    expect(overlapArea(card.rect, inCorner)).toBe(0)
  })

  it('the chip goes where it covers no text: below is covered, so it slides or moves beside the ring', () => {
    const chip = placePanel({ w: 200, h: 26 }, target, work, { kind: 'chip', prefer: CHIP_SIDES, content: page })
    expect(chip.cover).toBe(0)
    expect(chip.freeExists).toBe(true)
    for (const c of page) expect(overlapArea(chip.rect, c)).toBe(0)
    expect(overlapArea(chip.rect, target)).toBe(0)
    // It is still attached to the ring: within a chip's width of it.
    expect(Math.abs(chip.rect.x - (target.x + target.w))).toBeLessThan(80)
  })

  it('a small chip beside the ring is centred on it', () => {
    const right = placePanel({ w: 200, h: 26 }, target, work, { kind: 'chip', content: [{ x: 490, y: 452, w: 400, h: 18 }, { x: 490, y: 360, w: 400, h: 18 }] })
    expect(right.side).toBe('right')
    expect(right.rect.y + 13).toBeCloseTo(target.y + target.h / 2, 0)
  })

  it('the card takes the nearest spot that covers no content, anywhere on the screen, with air around the text', () => {
    const card = placePanel({ w: 280, h: 190 }, target, work, { kind: 'card', prefer: CARD_SIDES, content: page })
    expect(card.cover).toBe(0)
    for (const c of page) {
      const inflated = { x: c.x - air, y: c.y - air, w: c.w + 2 * air, h: c.h + 2 * air }
      expect(overlapArea(card.rect, inflated)).toBe(0)
    }
    expect(overlapArea(card.rect, target)).toBe(0)
    expect(card.side).not.toBe('corner')
  })

  it('when no free spot exists it covers the least it can and says there was none', () => {
    // Content everywhere except a sliver.
    const wall: Rect[] = []
    for (let y = 25; y < 825; y += 40) wall.push({ x: 0, y, w: 1440, h: 30 })
    const card = placePanel({ w: 280, h: 190 }, target, work, { kind: 'card', content: wall })
    expect(card.freeExists).toBe(false)
    expect(card.cover).toBeGreaterThan(0)
    expect(overlapArea(card.rect, target)).toBe(0)
  })

  it('without a target it goes near the point, in free space when the page is known', () => {
    const near = placePanel({ w: 280, h: 190 }, null, work, { kind: 'card', anchorPoint: { x: 500, y: 410 }, content: page })
    expect(near.cover).toBe(0)
    expect(Math.hypot(near.rect.x + 140 - 500, near.rect.y + 95 - 410)).toBeLessThan(600)
  })

  it('is deterministic: the same inputs give the same place', () => {
    const a = placePanel({ w: 280, h: 190 }, target, work, { kind: 'card', content: page })
    const b = placePanel({ w: 280, h: 190 }, target, work, { kind: 'card', content: page })
    expect(a).toEqual(b)
  })

  it('placeWindow adds the shadow room around the content and keeps the content where placePanel put it', () => {
    const size = { w: 292, h: 202 }
    const w = placeWindow(size, target, work, { kind: 'card', content: page })
    const p = placePanel({ w: size.w - 2 * PANEL_PAD, h: size.h - 2 * PANEL_PAD }, target, work, { kind: 'card', content: page })
    expect(w.rect).toEqual({ x: p.rect.x - PANEL_PAD, y: p.rect.y - PANEL_PAD, w: size.w, h: size.h })
  })
})

describe('a chip with no free spot touching its ring', () => {
  it('goes to a free spot within reach of the ring rather than cover text', () => {
    // Text hugging the ring on every side; free room only a little further out, below.
    const hug: Rect[] = [
      { x: 300, y: 360, w: 500, h: 18 },
      { x: 300, y: 452, w: 500, h: 18 },
      { x: 300, y: 380, w: 190, h: 70 },
      { x: 650, y: 380, w: 150, h: 70 },
      { x: 300, y: 475, w: 500, h: 40 },
    ]
    const chip = placePanel({ w: 160, h: 26 }, target, work, { kind: 'chip', content: hug })
    expect(chip.cover).toBe(0)
    expect(Math.hypot(chip.rect.x + 80 - (target.x + 70), chip.rect.y + 13 - (target.y + 23))).toBeLessThan(CUE_TOKENS.placement.chipReach + 160)
  })
  it('still attaches to the ring when the page has no free room anywhere near it', () => {
    const wall: Rect[] = []
    for (let y = 25; y < 825; y += 30) wall.push({ x: 0, y, w: 1440, h: 26 })
    const chip = placePanel({ w: 160, h: 26 }, target, work, { kind: 'chip', content: wall })
    expect(chip.freeExists).toBe(false)
    expect(overlapArea(chip.rect, target)).toBe(0)
  })
})

describe('keeping clear of another window of ours (the Knack corner column)', () => {
  const column: Rect = { x: 1100, y: 770, w: 324, h: 38 } // bottom-right of the work area
  const size = { w: 280, h: 190 }
  it('with no target and no pointer, the card takes the bottom-right corner when nothing is there', () => {
    const p = placePanel(size, null, work, { kind: 'card' })
    expect(p.rect).toEqual({ x: 1440 - CUE_TOKENS.placement.margin - size.w, y: work.y + work.h - CUE_TOKENS.placement.margin - size.h, w: size.w, h: size.h })
  })
  it('and stacks above the column when the column is there, never over it', () => {
    const p = placePanel(size, null, work, { kind: 'card', avoid: [column] })
    expect(overlapArea(p.rect, column)).toBe(0)
    expect(p.rect.x + p.rect.w).toBe(1440 - CUE_TOKENS.placement.margin) // the same corner
    expect(p.rect.y + p.rect.h).toBeLessThanOrEqual(column.y)
  })
  it('takes another corner when there is no room above the column', () => {
    const tall: Rect = { x: 1000, y: 40, w: 424, h: 760 }
    const p = placePanel(size, null, work, { kind: 'card', avoid: [tall] })
    expect(overlapArea(p.rect, tall)).toBe(0)
  })
})
