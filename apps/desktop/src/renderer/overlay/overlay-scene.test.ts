import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { annotationStyle } from '../design/annotation-style'
import { OverlayScene } from './OverlayScene'
import { EMPTY_OVERLAY_STATE, reduceOverlay, type OverlayState } from './store'

const viewport = { width: 1728, height: 1117 }
const style = annotationStyle({ bigAnnotations: false, highContrast: false })
const ctx = { now: 0, viewport, style }
const render = (state: OverlayState, extra: { coachDot?: boolean } = {}): string => renderToStaticMarkup(createElement(OverlayScene, { state, viewport, style, captionsEnabled: true, typeBubbles: false, ...extra }))

describe('the overlay as it is drawn', () => {
  let withCoach = reduceOverlay(EMPTY_OVERLAY_STATE, { type: 'coach', fade: 'full', level: 1, label: 'Watch me' }, ctx)
  withCoach = reduceOverlay(withCoach, { type: 'chip', level: 1, label: 'Watch me' }, ctx)

  it('draws no persistent coach chip and says nothing like "Watch me" unless the person turned the dot on', () => {
    const html = render(withCoach)
    expect(html).not.toMatch(/Watch me/)
    expect(html).not.toMatch(/coach-dot|coach-chip/)
  })

  it('with the dot on, it is one small dot and still no words', () => {
    const html = render(withCoach, { coachDot: true })
    expect(html).toMatch(/data-testid="coach-dot"/)
    expect(html).not.toMatch(/Watch me/)
    expect(html).toMatch(/width:7px;height:7px/)
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

  it('a step number sits in a small pill set in the mono face', () => {
    const state = reduceOverlay(EMPTY_OVERLAY_STATE, { type: 'show', annotations: [{ id: 'r', kind: 'ring', tone: 'guide', box: { xmin: 400, ymin: 600, xmax: 480, ymax: 640 }, exact: true, step: 3, note: 'Next' }] }, ctx)
    const html = render(state)
    expect(html).toMatch(/aria-label="Step 3"/)
    expect(html).toMatch(/JetBrains Mono/)
  })
})
