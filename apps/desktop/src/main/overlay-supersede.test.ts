import { describe, expect, it } from 'vitest'
import type { ServiceContext } from './context'
import { createOverlayController } from './overlay-controller'

type Sent = { type: string; ids?: string[]; annotations?: { id: string; kind: string }[] }

function setup() {
  const sent: Sent[] = []
  const ctx = { log: () => undefined, sendOverlay: (c: Sent) => sent.push(c) } as unknown as ServiceContext
  const ov = createOverlayController(ctx, { cursorNorm: () => null })
  return { sent, ov }
}

const ring = (id: string) => ({ id, tone: 'guide' as const, kind: 'ring' as const, box: { xmin: 100, ymin: 100, xmax: 200, ymax: 200 } })
const arrow = (id: string) => ({ id, tone: 'guide' as const, kind: 'arrow' as const, to: { x: 150, y: 150 } })
const flag = (id: string) => ({ id, tone: 'danger' as const, kind: 'highlightText' as const, boxes: [{ xmin: 10, ymin: 10, xmax: 90, ymax: 40 }] })

describe('overlay guidance is temporary and ordered', () => {
  it('a new step ring clears the previous step marks', () => {
    const { sent, ov } = setup()
    ov.show([ring('runner-ring-1'), arrow('runner-arrow-1')])
    ov.show([ring('runner-ring-2')])
    const clears = sent.filter((s) => s.type === 'clear')
    expect(clears).toHaveLength(1)
    expect([...(clears[0]!.ids ?? [])].sort()).toEqual(['runner-arrow-1', 'runner-ring-1'])
  })

  it('an arrow added to the same step does not clear its ring', () => {
    const { sent, ov } = setup()
    ov.show([ring('point-ring')])
    ov.show([arrow('point-arrow')])
    expect(sent.filter((s) => s.type === 'clear')).toHaveLength(0)
  })

  it('point_at replaces lesson marks and the reverse', () => {
    const { sent, ov } = setup()
    ov.show([ring('runner-ring-3')])
    ov.show([ring('point-ring')])
    expect(sent.find((s) => s.type === 'clear')?.ids).toEqual(['runner-ring-3'])
  })

  it('scam flags are never superseded by guidance', () => {
    const { sent, ov } = setup()
    ov.show([flag('flag-1')])
    ov.show([ring('runner-ring-1')])
    ov.show([ring('runner-ring-2')])
    for (const c of sent.filter((s) => s.type === 'clear')) expect(c.ids).not.toContain('flag-1')
  })

  it('re-showing the same id upserts without clearing', () => {
    const { sent, ov } = setup()
    ov.show([ring('runner-ring-1')])
    ov.show([ring('runner-ring-1')])
    expect(sent.filter((s) => s.type === 'clear')).toHaveLength(0)
  })

  it('sends each batch back-to-front regardless of call order', () => {
    const { sent, ov } = setup()
    ov.show([arrow('runner-arrow-1'), ring('runner-ring-1')])
    const batch = sent.find((s) => s.type === 'show')!
    expect(batch.annotations!.map((a) => a.kind)).toEqual(['ring', 'arrow'])
  })

  it('an explicit clear forgets guidance so the next ring does not re-clear it', () => {
    const { sent, ov } = setup()
    ov.show([ring('runner-ring-1')])
    ov.clear()
    ov.show([ring('runner-ring-2')])
    expect(sent.filter((s) => s.type === 'clear')).toHaveLength(1)
  })

  it('a verification tick survives the next step ring arriving straight after it', () => {
    const { sent, ov } = setup()
    ov.show([ring('runner-ring-1')])
    ov.show([{ id: 'runner-tick-1', tone: 'success' as const, kind: 'tick' as const, box: { xmin: 100, ymin: 100, xmax: 200, ymax: 200 }, ok: true }])
    ov.show([ring('runner-ring-2')])
    const cleared = sent.filter((s) => s.type === 'clear').flatMap((c) => c.ids ?? [])
    expect(cleared).toContain('runner-ring-1')
    expect(cleared).not.toContain('runner-tick-1')
  })
})
