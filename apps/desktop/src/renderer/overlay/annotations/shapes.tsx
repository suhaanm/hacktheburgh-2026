// Adapted from farzaa/clicky (MIT) — windows/src/Clicky.Overlay/DrawingOverlayControl.cs (circle and arrow drawing: glow, round caps, head polygon)
// SVG renderers for ring, arrow, badge, spotlight, tick and highlightText marks. Geometry is computed by the scene (so
// labels can avoid the marks); these components only draw.
import type { ReactElement } from 'react'
import type { AnnotationTone } from '../../../shared/protocol'
import type { AnnotationStyle } from '../../design/annotation-style'
import { arrowHeadPoints, arrowShaftPath, type ArrowPlan } from '../arrow'
import type { Pt, Rect, Size } from '../geometry'
import { Disc, Glyph, lifeClass, slimLayers, stacked } from './common'

interface Base {
  style: AnnotationStyle
  exiting: boolean
}

export function RingMark({ rect, tone, style, exiting }: Base & { rect: Rect; tone: AnnotationTone }): ReactElement {
  const t = style.tones[tone]
  const rx = Math.min(style.ring.radius, Math.min(rect.w, rect.h) / 2)
  const core = style.stroke.core
  const key = (style.stroke.casing - style.stroke.core) / 2 // each keyline's width
  // A very subtle second outline a little outside the ring, with viewfinder corner ticks sitting on it.
  const o = style.ring.halo.offset
  const bracket = (grow: number): string => {
    const x0 = rect.x - o - grow
    const y0 = rect.y - o - grow
    const x1 = rect.x + rect.w + o + grow
    const y1 = rect.y + rect.h + o + grow
    const arm = Math.min(style.ring.ticks.arm, (x1 - x0) / 3, (y1 - y0) / 3)
    return [`M ${x0} ${y0 + arm} V ${y0} H ${x0 + arm}`, `M ${x1 - arm} ${y0} H ${x1} V ${y0 + arm}`, `M ${x1} ${y1 - arm} V ${y1} H ${x1 - arm}`, `M ${x0 + arm} ${y1} H ${x0} V ${y1 - arm}`].join(' ')
  }
  // The coloured 2 px line hugs the target; the white keyline and then the ink keyline sit outside it (1 px each), so the whole mark is a
  // 4 px band that reads on a white page (ink edge) and on a dark one (white edge).
  const rings = [
    { grow: core / 2 + key * 1.5, w: key, color: t.keyOuter },
    { grow: core / 2 + key * 0.5, w: key, color: t.keyInner },
    { grow: 0, w: core, color: t.core },
  ]
  const lineProps = { fill: 'none', strokeLinejoin: 'miter' as const }
  return (
    <g className={`ov-mark ${lifeClass(exiting)}`} data-mark="ring">
      <rect x={rect.x - o} y={rect.y - o} width={rect.w + o * 2} height={rect.h + o * 2} rx={rx + o} fill="none" stroke={t.core} strokeWidth={style.ring.halo.width} strokeOpacity={style.ring.halo.opacity} />
      {rings.map((r, i) => (
        <g key={i} stroke={r.color} strokeWidth={r.w} {...lineProps}>
          <path d={bracket(r.grow)} strokeLinecap="square" />
          <rect x={rect.x - r.grow} y={rect.y - r.grow} width={rect.w + r.grow * 2} height={rect.h + r.grow * 2} rx={rx + r.grow} strokeDasharray={r.color === t.core ? (t.dash ?? undefined) : undefined} />
        </g>
      ))}
    </g>
  )
}

export function ArrowMark({ plan, tone, style, exiting }: Base & { plan: ArrowPlan; tone: AnnotationTone }): ReactElement {
  const t = style.tones[tone]
  const shaft = arrowShaftPath(plan)
  const head = arrowHeadPoints(plan)
  return (
    <g className={`ov-mark ${lifeClass(exiting)}`}>
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
  const w = stepPillWidth(style, n)
  const h = style.badge.diameter
  return (
    <g className={`ov-mark ${lifeClass(exiting)}`}>
      <rect x={at.x - w / 2 - 2} y={at.y - h / 2 - 2} width={w + 4} height={h + 4} rx={(h + 4) / 2} fill={t.keyOuter} />
      <rect x={at.x - w / 2 - 1} y={at.y - h / 2 - 1} width={w + 2} height={h + 2} rx={(h + 2) / 2} fill={t.keyInner} />
      <rect x={at.x - w / 2} y={at.y - h / 2} width={w} height={h} rx={h / 2} fill={t.core} />
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

/** Width of the step pill: round for one digit, a little wider for more (mono digits are about 0.6 em). */
export function stepPillWidth(style: AnnotationStyle, n: number): number {
  const digits = String(Math.abs(Math.trunc(n))).length
  return Math.max(style.badge.diameter, Math.round(digits * style.badge.fontSize * 0.62 + style.badge.padX * 2))
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
