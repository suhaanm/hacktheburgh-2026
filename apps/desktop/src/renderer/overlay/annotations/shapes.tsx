// Adapted from farzaa/clicky (MIT) — windows/src/Clicky.Overlay/DrawingOverlayControl.cs (circle and arrow drawing: glow, round caps, head polygon)
// SVG renderers for ring, arrow, badge, spotlight, tick and highlightText marks. Geometry is computed by the scene (so
// labels can avoid the marks); these components only draw.
import type { ReactElement } from 'react'
import type { AnnotationTone } from '../../../shared/protocol'
import type { AnnotationStyle } from '../../design/annotation-style'
import { arrowHeadPoints, arrowShaftPath, type ArrowPlan } from '../arrow'
import type { Pt, Rect, Size } from '../geometry'
import { Disc, Glyph, glowStack, iterations, lifeClass, slimLayers, stacked } from './common'

interface Base {
  style: AnnotationStyle
  exiting: boolean
}

export function RingMark({ rect, tone, style, exiting }: Base & { rect: Rect; tone: AnnotationTone }): ReactElement {
  const t = style.tones[tone]
  const rx = Math.min(style.ring.radius, Math.min(rect.w, rect.h) / 2)
  return (
    <g className={`ov-mark ${lifeClass(exiting)}`}>
      {glowStack(style, tone, (p, k) => (
        <rect key={`g${k}`} x={rect.x} y={rect.y} width={rect.w} height={rect.h} rx={rx} {...p} />
      ))}
      {stacked(style, tone, (p, k) => (
        <rect key={k} x={rect.x} y={rect.y} width={rect.w} height={rect.h} rx={rx} {...p} />
      ))}
      {style.pulse.enabled ? (
        <rect className="ov-pulse" style={iterations(style, tone)} x={rect.x} y={rect.y} width={rect.w} height={rect.h} rx={rx} fill="none" stroke={t.core} strokeWidth={style.stroke.core} />
      ) : null}
    </g>
  )
}

export function ArrowMark({ plan, tone, style, exiting }: Base & { plan: ArrowPlan; tone: AnnotationTone }): ReactElement {
  const t = style.tones[tone]
  const shaft = arrowShaftPath(plan)
  const head = arrowHeadPoints(plan)
  return (
    <g className={`ov-mark ${lifeClass(exiting)}`}>
      {glowStack(style, tone, (p, k) => (
        <g key={`g${k}`}>
          <path d={shaft} {...p} />
          <polygon points={head} {...p} />
        </g>
      ))}
      {stacked(style, tone, (p, k) => (
        <g key={k}>
          <path d={shaft} {...p} />
          <polygon points={head} {...p} strokeDasharray={undefined} />
        </g>
      ))}
      <polygon points={head} fill={t.core} />
    </g>
  )
}

export function BadgeMark({ at, n, tone, style, exiting }: Base & { at: Pt; n: number; tone: AnnotationTone }): ReactElement {
  const t = style.tones[tone]
  return (
    <g className={`ov-mark ${lifeClass(exiting)}`}>
      <Disc cx={at.x} cy={at.y} diameter={style.badge.diameter} tone={tone} style={style} />
      <text
        x={at.x}
        y={at.y}
        textAnchor="middle"
        dominantBaseline="central"
        fill={t.onCore}
        fontFamily={style.badge.fontFamily}
        fontSize={style.badge.fontSize}
        fontWeight={style.badge.fontWeight}
        style={{ fontVariantNumeric: 'tabular-nums' }}
      >
        {n}
      </text>
    </g>
  )
}

// A dim layer over the whole display with a soft-edged cut-out around the target. Pure picture: it never blocks input.
export function SpotlightMark({ rect, tone, style, viewport, exiting, id }: Base & { rect: Rect; tone: AnnotationTone; viewport: Size; id: string }): ReactElement {
  const s = style.spotlight
  const maskId = `ov-spot-${id.replace(/[^a-zA-Z0-9_-]/g, '_')}`
  const hasFeather = s.feather > 0
  return (
    <g className={lifeClass(exiting) === 'ov-exit' ? 'ov-exit' : 'ov-fade-enter'}>
      <mask id={maskId} maskUnits="userSpaceOnUse" x={0} y={0} width={viewport.width} height={viewport.height}>
        <rect x={0} y={0} width={viewport.width} height={viewport.height} fill="#fff" />
        <rect x={rect.x} y={rect.y} width={rect.w} height={rect.h} rx={s.radius} fill="#000" filter={hasFeather ? 'url(#ov-feather)' : undefined} />
      </mask>
      <rect x={0} y={0} width={viewport.width} height={viewport.height} fill={s.dimColor} fillOpacity={s.dimOpacity} mask={`url(#${maskId})`} />
      {stacked(style, tone, (p, k) => (
        <rect key={k} x={rect.x} y={rect.y} width={rect.w} height={rect.h} rx={s.radius} {...p} />
      ), { widthScale: 0.45, dashed: false })}
    </g>
  )
}

export function TickMark({ box, center, ok, tone, style, exiting }: Base & { box: Rect; center: Pt; ok: boolean; tone: AnnotationTone }): ReactElement {
  const t = style.tones[tone]
  const d = style.tick.size
  const rx = Math.min(style.ring.radius, Math.min(box.w, box.h) / 2)
  const draw = style.tick.drawMs
  const checkPath = `M ${center.x - d * 0.24} ${center.y + d * 0.02} L ${center.x - d * 0.06} ${center.y + d * 0.2} L ${center.x + d * 0.26} ${center.y - d * 0.2}`
  return (
    <g className={`ov-mark ${lifeClass(exiting)}`}>
      {stacked(style, tone, (p, k) => (
        <rect key={k} x={box.x} y={box.y} width={box.w} height={box.h} rx={rx} {...p} />
      ), { widthScale: 0.7 })}
      <Disc cx={center.x} cy={center.y} diameter={d} tone={tone} style={style} />
      {ok ? (
        <path
          d={checkPath}
          fill="none"
          stroke={t.onCore}
          strokeWidth={d * 0.13}
          strokeLinecap="round"
          strokeLinejoin="round"
          pathLength={1}
          className="ov-check"
          style={draw > 0 ? { strokeDasharray: 1, animation: `ov-draw ${draw}ms ease-out 120ms both` } : undefined}
        />
      ) : (
        <Glyph kind={t.glyph} cx={center.x} cy={center.y} size={d * 0.62} color={t.onCore} weight={3} />
      )}
    </g>
  )
}

export function HighlightMarks({ rects, tone, style, exiting }: Base & { rects: Rect[]; tone: AnnotationTone }): ReactElement {
  const h = style.highlightText
  const t = style.tones[tone]
  const layers = slimLayers(style, tone, h.underlineWidth * 0.7)
  return (
    <g className={lifeClass(exiting) === 'ov-exit' ? 'ov-exit' : 'ov-fade-enter'}>
      {rects.map((r, i) => {
        const box = { x: r.x - h.pad, y: r.y - h.pad, w: r.w + h.pad * 2, h: r.h + h.pad * 2 }
        const y = box.y + box.h + 1
        return (
          <g key={i}>
            <rect x={box.x} y={box.y} width={box.w} height={box.h} rx={h.radius} fill={t.wash} />
            {stacked(style, tone, (p, k) => (
              <line key={k} x1={box.x + 2} y1={y} x2={box.x + box.w - 2} y2={y} {...p} />
            ), { layers })}
          </g>
        )
      })}
    </g>
  )
}
