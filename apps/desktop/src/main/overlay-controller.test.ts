import { describe, expect, it, vi } from 'vitest'
import type { OverlayCommand } from '../shared/protocol'
import type { ServiceContext } from './context'
import { createOverlayController, sanitizeAnnotation } from './overlay-controller'

function setup(cursor: { x: number; y: number } | null = null) {
  const sent: OverlayCommand[] = []
  const ctx = { sendOverlay: (c: OverlayCommand) => sent.push(c), log: vi.fn() } as unknown as ServiceContext
  return { sent, ctx, controller: createOverlayController(ctx, { cursorNorm: () => cursor }) }
}

describe('sanitizeAnnotation', () => {
  it('clamps out-of-range coordinates and fixes swapped box corners', () => {
    const a = sanitizeAnnotation({ id: 'r', kind: 'ring', tone: 'guide', box: { xmin: 1200, ymin: -10, xmax: 900, ymax: 300 } })
    expect(a).toMatchObject({ box: { xmin: 900, xmax: 1000, ymin: 0, ymax: 300 } })
  })
  it('drops annotations with NaN/Infinity', () => {
    expect(sanitizeAnnotation({ id: 'b', kind: 'badge', tone: 'guide', at: { x: Number.NaN, y: 5 }, n: 1 })).toBeNull()
    expect(sanitizeAnnotation({ id: 'b', kind: 'badge', tone: 'guide', at: { x: 5, y: Infinity }, n: 1 })).toBeNull()
  })
  it('clamps arrow targets and ghost paths', () => {
    expect(sanitizeAnnotation({ id: 'a', kind: 'arrow', tone: 'guide', to: { x: 2000, y: -5 }, from: { x: -1, y: 1001 } })).toMatchObject({ to: { x: 1000, y: 0 }, from: { x: 0, y: 1000 } })
    expect(sanitizeAnnotation({ id: 'g', kind: 'ghostCursor', tone: 'guide', path: [{ x: 1100, y: 1100 }] })).toMatchObject({ path: [{ x: 1000, y: 1000 }] })
  })
})

describe('OverlayController', () => {
  it('forwards commands unchanged in meaning', () => {
    const { controller, sent } = setup()
    controller.show([{ id: 'r', kind: 'ring', tone: 'guide', box: { xmin: 1, ymin: 2, xmax: 3, ymax: 4 } }])
    controller.clear(['r'])
    controller.clear()
    controller.caption('assistant', 'Hello', false)
    controller.chip(3, 'Nudge me')
    expect(sent.map((c) => c.type)).toEqual(['show', 'clear', 'clear', 'caption', 'chip'])
    expect(sent[1]).toEqual({ type: 'clear', ids: ['r'] })
    expect(sent[2]).toEqual({ type: 'clear', ids: undefined })
  })
  it('drops a malformed annotation but still draws the rest', () => {
    const { controller, sent, ctx } = setup()
    controller.show([
      { id: 'bad', kind: 'badge', tone: 'guide', at: { x: Number.NaN, y: 0 }, n: 1 },
      { id: 'ok', kind: 'tick', tone: 'success', box: { xmin: 1, ymin: 1, xmax: 5, ymax: 5 }, ok: true },
    ])
    expect(sent).toHaveLength(1)
    expect((sent[0] as { annotations: { id: string }[] }).annotations.map((a) => a.id)).toEqual(['ok'])
    expect(ctx.log).toHaveBeenCalled()
  })
  it('sends nothing when every annotation is malformed', () => {
    const { controller, sent } = setup()
    controller.show([{ id: 'bad', kind: 'badge', tone: 'guide', at: { x: Number.NaN, y: 0 }, n: 1 }])
    expect(sent).toHaveLength(0)
  })
  it('a one-point ghost path starts from the mouse position', () => {
    const { controller, sent } = setup({ x: 100, y: 900 })
    controller.show([{ id: 'g', kind: 'ghostCursor', tone: 'guide', path: [{ x: 500, y: 500 }] }])
    const cmd = sent[0] as { annotations: { path: { x: number; y: number }[] }[] }
    expect(cmd.annotations[0].path).toEqual([{ x: 100, y: 900 }, { x: 500, y: 500 }])
  })
  it('leaves multi-point ghost paths alone', () => {
    const { controller, sent } = setup({ x: 100, y: 900 })
    controller.show([{ id: 'g', kind: 'ghostCursor', tone: 'guide', path: [{ x: 1, y: 1 }, { x: 2, y: 2 }] }])
    const cmd = sent[0] as { annotations: { path: unknown[] }[] }
    expect(cmd.annotations[0].path).toHaveLength(2)
  })
})
