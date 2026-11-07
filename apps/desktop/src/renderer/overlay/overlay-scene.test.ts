import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { annotationStyle } from '../design/annotation-style'
import { OverlayScene } from './OverlayScene'
import { advance, CHIP_VISIBLE_MS, EMPTY_OVERLAY_STATE, reduceOverlay, type OverlayState } from './store'

const viewport = { width: 1728, height: 1117 }
const style = annotationStyle({ bigAnnotations: false, highContrast: false })
const ctx = { now: 0, viewport, style }
const render = (state: OverlayState, extra: { coachDot?: boolean } = {}): string => renderToStaticMarkup(createElement(OverlayScene, { state, viewport, style, captionsEnabled: true, typeBubbles: false, ...extra }))

describe('the overlay as it is drawn', () => {
  let withCoach = reduceOverlay(EMPTY_OVERLAY_STATE, { type: 'coach', fade: 'full', level: 1, label: 'Watch me' }, ctx)
  withCoach = reduceOverlay(withCoach, { type: 'chip', level: 1, label: 'Watch me' }, ctx)

  it('draws no persistent coach chip: the coach state alone puts nothing on the screen, with or without the dot', () => {
    const coachOnly = reduceOverlay(EMPTY_OVERLAY_STATE, { type: 'coach', fade: 'full', level: 1, label: 'Watch me' }, ctx)
    const html = render(coachOnly)
    expect(html).not.toMatch(/Watch me/)
    expect(html).not.toMatch(/coach-dot|coach-chip/)
    const dot = render(coachOnly, { coachDot: true })
    expect(dot).toMatch(/data-testid="coach-dot"/)
    expect(dot).not.toMatch(/Watch me/)
    expect(dot).toMatch(/width:7px;height:7px/)
  })

  it('a level change shows as a small toast that leaves after two seconds', () => {
    expect(CHIP_VISIBLE_MS).toBe(2000)
    expect(withCoach.chip).not.toBeNull()
    expect(render(withCoach)).toMatch(/Watch me/) // the toast is up
    const gone = advance(withCoach, { now: CHIP_VISIBLE_MS + 1, viewport, style })
    const later = advance(gone, { now: CHIP_VISIBLE_MS + 1 + style.transition.exitMs + 1, viewport, style })
    expect(later.chip).toBeNull()
    expect(render(later)).not.toMatch(/Watch me/)
  })

  it('a ring with a note is a ring, corner ticks and one short chip: no bubble, no arrow, no glow, nothing animating in a loop', () => {
    const state = reduceOverlay(EMPTY_OVERLAY_STATE, { type: 'show', annotations: [{ id: 'r', kind: 'ring', tone: 'guide', box: { xmin: 400, ymin: 600, xmax: 480, ymax: 640 }, exact: true, note: 'Check cliff edges before you reconcile the results.' }] }, ctx)
    const html = render(state)
    expect(html).toContain('Check cliff edges')
    expect(html).not.toContain('reconcile the results')
    expect(html).toMatch(/data-mark="ring"/)
    expect(html).not.toMatch(/<polygon|ov-pulse|infinite|filter=/)
    const family = (/font-family:([^;"]+)/.exec(html.replace(/&#x27;/g, "'"))?.[1] ?? '')
    expect(family).toMatch(/Source Sans 3/)
  })

  it('a light ring (help level L3) is thinner and quieter: no offset halo outline, shorter ticks, a 1.25 px line', () => {
    const show = (weight?: 'regular' | 'light') => render(reduceOverlay(EMPTY_OVERLAY_STATE, { type: 'show', annotations: [{ id: 'r', kind: 'ring', tone: 'guide', box: { xmin: 400, ymin: 600, xmax: 480, ymax: 640 }, exact: true, ...(weight ? { weight } : {}) }] }, ctx))
    const regular = show()
    const light = show('light')
    expect(regular).toMatch(/data-weight="regular"/)
    expect(light).toMatch(/data-weight="light"/)
    expect(light).toMatch(/stroke-width="1.25"/)
    expect(regular).not.toMatch(/stroke-width="1.25"/)
    expect((light.match(/<rect /g) ?? []).length).toBeLessThan((regular.match(/<rect /g) ?? []).length) // the halo outline is gone
  })

  it('a step number sits in a small pill set in the mono face', () => {
    const state = reduceOverlay(EMPTY_OVERLAY_STATE, { type: 'show', annotations: [{ id: 'r', kind: 'ring', tone: 'guide', box: { xmin: 400, ymin: 600, xmax: 480, ymax: 640 }, exact: true, step: 3, note: 'Next' }] }, ctx)
    const html = render(state)
    expect(html).toMatch(/aria-label="Step 3"/)
    expect(html).toMatch(/JetBrains Mono/)
  })
})
