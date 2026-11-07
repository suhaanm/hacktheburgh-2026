import { describe, expect, it } from 'vitest'
import { nextSegmentIndex } from './Switch'

describe('nextSegmentIndex', () => {
  it('moves with arrows and wraps at both ends', () => {
    expect(nextSegmentIndex('ArrowRight', 0, 3)).toBe(1)
    expect(nextSegmentIndex('ArrowDown', 2, 3)).toBe(0)
    expect(nextSegmentIndex('ArrowLeft', 1, 3)).toBe(0)
    expect(nextSegmentIndex('ArrowUp', 0, 3)).toBe(2)
  })
  it('jumps with Home and End', () => {
    expect(nextSegmentIndex('Home', 2, 4)).toBe(0)
    expect(nextSegmentIndex('End', 0, 4)).toBe(3)
  })
  it('ignores other keys and empty groups', () => {
    expect(nextSegmentIndex('Tab', 1, 3)).toBe(-1)
    expect(nextSegmentIndex('a', 1, 3)).toBe(-1)
    expect(nextSegmentIndex('ArrowRight', 0, 0)).toBe(-1)
  })
})
