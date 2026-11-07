import { describe, expect, it } from 'vitest'
import {
  boxArea,
  boxAroundPoint,
  boxCenter,
  boxProblem,
  fromComputerUsePoint,
  fromGeminiBox,
  iou,
  pointInBox,
} from './grounding-utils'

describe('fromGeminiBox', () => {
  it('converts [ymin,xmin,ymax,xmax] to a NormBox object', () => {
    expect(fromGeminiBox([356, 107, 403, 268])).toEqual({ xmin: 107, ymin: 356, xmax: 268, ymax: 403 })
  })
  it('clamps out-of-range values into 0-1000', () => {
    expect(fromGeminiBox([-20, -5, 1040, 1200])).toEqual({ xmin: 0, ymin: 0, xmax: 1000, ymax: 1000 })
  })
  it('fixes swapped corners', () => {
    expect(fromGeminiBox([403, 268, 356, 107])).toEqual({ xmin: 107, ymin: 356, xmax: 268, ymax: 403 })
  })
  it('rejects malformed input and the all-zero "not found" placeholder', () => {
    expect(fromGeminiBox(null)).toBeNull()
    expect(fromGeminiBox([1, 2, 3])).toBeNull()
    expect(fromGeminiBox([1, 2, Number.NaN, 4])).toBeNull()
    expect(fromGeminiBox([0, 0, 0, 0])).toBeNull()
  })
})

describe('boxProblem', () => {
  it('accepts a normal button', () => {
    expect(boxProblem({ xmin: 107, ymin: 356, xmax: 268, ymax: 403 })).toBeNull()
  })
  it('rejects boxes covering more than half the screen', () => {
    expect(boxArea({ xmin: 0, ymin: 0, xmax: 800, ymax: 800 })).toBeCloseTo(0.64)
    expect(boxProblem({ xmin: 0, ymin: 0, xmax: 800, ymax: 800 })).toBe('oversize')
  })
  it('accepts an exactly-half-screen box but rejects just over it', () => {
    expect(boxProblem({ xmin: 0, ymin: 0, xmax: 1000, ymax: 500 })).toBeNull()
    expect(boxProblem({ xmin: 0, ymin: 0, xmax: 1000, ymax: 510 })).toBe('oversize')
  })
  it('rejects degenerate boxes', () => {
    expect(boxProblem({ xmin: 10, ymin: 10, xmax: 11, ymax: 50 })).toBe('degenerate')
  })
})

describe('points and boxes', () => {
  it('converts computer_use 0-999 ints', () => {
    expect(fromComputerUsePoint(188, 380)).toEqual({ x: 188, y: 380 })
    expect(fromComputerUsePoint(1200, -3)).toEqual({ x: 1000, y: 0 })
    expect(fromComputerUsePoint(Number.NaN, 4)).toBeNull()
  })
  it('centre, containment, and IoU', () => {
    const a = { xmin: 100, ymin: 100, xmax: 200, ymax: 200 }
    expect(boxCenter(a)).toEqual({ x: 150, y: 150 })
    expect(pointInBox({ x: 150, y: 150 }, a)).toBe(true)
    expect(pointInBox({ x: 250, y: 150 }, a)).toBe(false)
    expect(iou(a, a)).toBe(1)
    expect(iou(a, { xmin: 300, ymin: 300, xmax: 400, ymax: 400 })).toBe(0)
    expect(iou(a, { xmin: 150, ymin: 100, xmax: 250, ymax: 200 })).toBeCloseTo(1 / 3)
  })
  it('boxAroundPoint stays inside the screen', () => {
    expect(boxAroundPoint({ x: 5, y: 995 })).toEqual({ xmin: 0, ymin: 970, xmax: 30, ymax: 1000 })
  })
})
