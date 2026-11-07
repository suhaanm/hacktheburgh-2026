import { describe, expect, it } from 'vitest'
import type { Annotation } from '../../shared/protocol'
import { DEFAULT_ANNOTATION_STYLE } from '../design/annotation-style'
import { advance, captionLingerMs, EMPTY_OVERLAY_STATE, nextDeadline, reduceOverlay, STALE_GUARD_MS, type ReduceContext } from './store'

const style = DEFAULT_ANNOTATION_STYLE
const ctx = (now: number): ReduceContext => ({ now, viewport: { width: 1728, height: 1117 }, style })
const ring: Annotation = { id: 'r1', kind: 'ring', tone: 'guide', box: { xmin: 100, ymin: 100, xmax: 200, ymax: 200 } }
const tick: Annotation = { id: 't1', kind: 'tick', tone: 'success', box: { xmin: 100, ymin: 100, xmax: 200, ymax: 200 }, ok: true }

describe('overlay store', () => {
  it('show adds, same id updates in place without replaying the entrance', () => {
    let s = reduceOverlay(EMPTY_OVERLAY_STATE, { type: 'show', annotations: [ring] }, ctx(1000))
    expect(s.annotations).toHaveLength(1)
    expect(s.annotations[0].shownAt).toBe(1000)
    s = reduceOverlay(s, { type: 'show', annotations: [{ ...ring, label: 'Start' } as Annotation] }, ctx(2000))
    expect(s.annotations).toHaveLength(1)
    expect(s.annotations[0].shownAt).toBe(1000)
    expect(s.annotations[0].expiresAt).toBe(2000 + STALE_GUARD_MS)
  })
  it('clear with ids exits only those; without ids exits all annotations but not the caption', () => {
    let s = reduceOverlay(EMPTY_OVERLAY_STATE, { type: 'show', annotations: [ring, tick] }, ctx(0))
    s = reduceOverlay(s, { type: 'caption', speaker: 'assistant', text: 'Hello', final: true }, ctx(0))
    s = reduceOverlay(s, { type: 'clear', ids: ['r1'] }, ctx(100))
    expect(s.annotations.find((a) => a.annotation.id === 'r1')?.exitingAt).toBe(100)
    expect(s.annotations.find((a) => a.annotation.id === 't1')?.exitingAt).toBeNull()
    s = reduceOverlay(s, { type: 'clear' }, ctx(200))
    expect(s.annotations.every((a) => a.exitingAt !== null)).toBe(true)
    expect(s.caption?.exitingAt).toBeNull()
  })
  it('exited annotations are removed after exitMs', () => {
    let s = reduceOverlay(EMPTY_OVERLAY_STATE, { type: 'show', annotations: [ring] }, ctx(0))
    s = reduceOverlay(s, { type: 'clear' }, ctx(100))
    expect(advance(s, ctx(100 + style.transition.exitMs - 1)).annotations).toHaveLength(1)
    expect(advance(s, ctx(100 + style.transition.exitMs)).annotations).toHaveLength(0)
  })
  it('ticks expire by default and ttlMs overrides', () => {
    let s = reduceOverlay(EMPTY_OVERLAY_STATE, { type: 'show', annotations: [tick, { ...ring, ttlMs: 500 }] }, ctx(0))
    s = advance(s, ctx(600))
    expect(s.annotations.find((a) => a.annotation.id === 'r1')?.exitingAt).toBe(600)
    expect(s.annotations.find((a) => a.annotation.id === 't1')?.exitingAt).toBeNull()
    s = advance(s, ctx(4000))
    expect(s.annotations.find((a) => a.annotation.id === 't1')?.exitingAt).toBe(4000)
  })
  it('stale guard removes annotations nobody cleared', () => {
    let s = reduceOverlay(EMPTY_OVERLAY_STATE, { type: 'show', annotations: [ring] }, ctx(0))
    s = advance(s, ctx(STALE_GUARD_MS + 1))
    expect(s.annotations[0].exitingAt).not.toBeNull()
  })
  it('ghost cursor lives for its flight plus an afterglow', () => {
    const ghost: Annotation = { id: 'g', kind: 'ghostCursor', tone: 'guide', path: [{ x: 100, y: 100 }, { x: 800, y: 600 }] }
    const s = reduceOverlay(EMPTY_OVERLAY_STATE, { type: 'show', annotations: [ghost] }, ctx(0))
    const ttl = s.annotations[0].expiresAt!
    expect(ttl).toBeGreaterThan(style.ghostCursor.flight.minMs + style.ghostCursor.flight.dwellMs)
    expect(ttl).toBeLessThan(15_000)
  })
  it('captions: streaming updates replace, final lingers, empty text dismisses', () => {
    let s = reduceOverlay(EMPTY_OVERLAY_STATE, { type: 'caption', speaker: 'assistant', text: 'Click the', final: false }, ctx(0))
    s = reduceOverlay(s, { type: 'caption', speaker: 'assistant', text: 'Click the blue button', final: true }, ctx(500))
    expect(s.caption?.text).toBe('Click the blue button')
    expect(s.caption?.expiresAt).toBe(500 + captionLingerMs('Click the blue button'))
    s = reduceOverlay(s, { type: 'caption', speaker: 'assistant', text: '  ', final: true }, ctx(900))
    expect(s.caption?.exitingAt).toBe(900)
  })
  it('chip is shown, then fades', () => {
    let s = reduceOverlay(EMPTY_OVERLAY_STATE, { type: 'chip', level: 2, label: 'Walk with me' }, ctx(0))
    expect(s.chip?.label).toBe('Walk with me')
    s = advance(s, ctx(7000))
    expect(s.chip?.exitingAt).toBe(7000)
    s = advance(s, ctx(8000))
    expect(s.chip).toBeNull()
  })
  it('chip remembers the previous level (even after it faded) so the echo can animate the change', () => {
    let s = reduceOverlay(EMPTY_OVERLAY_STATE, { type: 'chip', level: 1, label: 'Watch me' }, ctx(0))
    expect(s.chip?.from).toBeNull()
    s = reduceOverlay(s, { type: 'chip', level: 3, label: 'Nudge me' }, ctx(1000))
    expect(s.chip?.from).toEqual({ level: 1, label: 'Watch me' })
    s = advance(s, ctx(20_000))
    s = advance(s, ctx(21_000))
    expect(s.chip).toBeNull()
    s = reduceOverlay(s, { type: 'chip', level: 4, label: 'On my own' }, ctx(30_000))
    expect(s.chip?.from).toEqual({ level: 3, label: 'Nudge me' })
    // Same level again: nothing to animate.
    s = reduceOverlay(s, { type: 'chip', level: 4, label: 'On my own' }, ctx(31_000))
    expect(s.chip?.from).toBeNull()
  })
  it('advance returns the same object when idle; nextDeadline reports the earliest event', () => {
    const s = reduceOverlay(EMPTY_OVERLAY_STATE, { type: 'show', annotations: [{ ...ring, ttlMs: 1000 }] }, ctx(0))
    expect(advance(s, ctx(10))).toBe(s)
    expect(nextDeadline(s, style.transition.exitMs)).toBe(1000)
    expect(nextDeadline(EMPTY_OVERLAY_STATE, 200)).toBeNull()
  })
})
