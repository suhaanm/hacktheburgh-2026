// Adapted from farzaa/clicky (MIT) — leanring-buddy/OverlayWindow.swift (BlueCursorView bezier flight, scale pulse, tangent heading)
// Ghost cursor: a translucent pointer that flies a bezier arc to each point of `path` and holds there (SVG + rAF).
// VISUAL ONLY: the overlay window is click-through and nothing here dispatches input; `pressAtEnd` draws a ring
// that looks like a click, it does not click.
import { useEffect, useMemo, useRef, type ReactElement } from 'react'
import type { AnnotationStyle } from '../../design/annotation-style'
import { leanDeg, parseEasing, planFlight, sampleFlight } from '../flight'
import type { Pt, Size } from '../geometry'
import { lifeClass, stacked } from './common'

const POINTER_PATH = 'M0 0 L0 16 L4.2 12.1 L7 17.5 L9.6 16.2 L6.9 10.9 L12.5 10.9 Z'

interface Props {
  path: Pt[]
  style: AnnotationStyle
  viewport: Size
  pressAtEnd: boolean
  exiting: boolean
  // Harness only: render a still of the flight at this many ms instead of animating.
  freezeAtMs?: number | null
  startHint?: Pt
}

export function GhostCursor({ path, style, viewport, pressAtEnd, exiting, freezeAtMs = null, startHint }: Props): ReactElement {
  const g = style.ghostCursor
  const ease = useMemo(() => parseEasing(g.flight.easing), [g.flight.easing])
  const plan = useMemo(() => planFlight(path, g.flight, { viewport, startHint }), [path, g.flight, viewport, startHint])
  const pressMs = pressAtEnd ? g.press.durationMs : 0
  const cursorRef = useRef<SVGGElement>(null)
  const tagRef = useRef<SVGGElement>(null)
  const pressRefs = useRef<(SVGCircleElement | null)[]>([])
  const trailRefs = useRef<(SVGCircleElement | null)[]>([])

  const scale = g.size / 17.5
  const tagText = g.tag
  // Big mode scales every token by 1.6; the promise tag stays readable but must not hide the target.
  const tagFont = style.scale > 1 ? g.tagFontSize * 0.75 : g.tagFontSize
  const tagW = Math.ceil(tagText.length * tagFont * 0.55 + tagFont * 1.4)
  const tagH = Math.ceil(tagFont * 1.9)

  useEffect(() => {
    const apply = (elapsed: number): boolean => {
      const s = sampleFlight(plan, elapsed, ease, pressMs)
      cursorRef.current?.setAttribute('transform', `translate(${s.pos.x.toFixed(1)} ${s.pos.y.toFixed(1)}) rotate(${leanDeg(s.headingDeg).toFixed(1)}) scale(${(scale * s.scale).toFixed(3)})`)
      const flying = s.phase === 'flying'
      const tagX = s.pos.x + g.size * 0.8 + tagW > viewport.width - 8 ? s.pos.x - g.size * 0.6 - tagW : s.pos.x + g.size * 0.8
      const tagY = Math.min(viewport.height - tagH - 8, s.pos.y + g.size * 0.9)
      tagRef.current?.setAttribute('transform', `translate(${tagX.toFixed(1)} ${tagY.toFixed(1)})`)
      // Shown while travelling and briefly after landing, then it gets out of the way of the thing being pointed at.
      const lastHoldStart = plan.totalMs - (plan.segments[plan.segments.length - 1]?.holdMs ?? 0)
      tagRef.current?.setAttribute('opacity', String(Math.max(0, Math.min(1, 1 - (elapsed - lastHoldStart - 700) / 300))))
      for (let i = 0; i < trailRefs.current.length; i++) {
        const el = trailRefs.current[i]
        if (!el) continue
        const past = sampleFlight(plan, Math.max(0, elapsed - (i + 1) * 42), ease, 0)
        el.setAttribute('cx', past.pos.x.toFixed(1))
        el.setAttribute('cy', past.pos.y.toFixed(1))
        el.setAttribute('opacity', flying ? (Math.min(0.85, g.trail.opacity * 1.6) * (1 - i / (g.trail.count + 1))).toFixed(2) : '0')
      }
      for (const ring of pressRefs.current) {
        if (!ring) continue
        if (s.press !== null) {
          ring.setAttribute('cx', s.pos.x.toFixed(1))
          ring.setAttribute('cy', s.pos.y.toFixed(1))
          ring.setAttribute('r', (g.press.radius * (0.35 + 0.65 * s.press)).toFixed(1))
          ring.setAttribute('opacity', (0.9 * (1 - s.press)).toFixed(2))
        } else {
          ring.setAttribute('opacity', '0')
        }
      }
      return s.phase !== 'done'
    }
    if (freezeAtMs !== null) {
      apply(freezeAtMs)
      return
    }
    const start = performance.now()
    let raf = 0
    const frame = (): void => {
      if (apply(performance.now() - start)) raf = requestAnimationFrame(frame)
    }
    frame()
    return () => cancelAnimationFrame(raf)
  }, [plan, ease, pressMs, scale, g.size, tagFont, g.trail.count, g.trail.opacity, g.press.radius, tagW, tagH, viewport.width, viewport.height, freezeAtMs])

  const tone = style.tones.guide
  const first = sampleFlight(plan, 0, ease, 0).pos
  return (
    <g className={exiting ? lifeClass(true) : 'ov-fade-enter'}>
      {Array.from({ length: g.trail.count }, (_, i) => (
        <circle
          key={i}
          ref={(el) => {
            trailRefs.current[i] = el
          }}
          cx={first.x}
          cy={first.y}
          r={g.size * (0.27 - i * 0.032)}
          fill={g.fill}
          stroke={tone.halo}
          strokeWidth={2}
          opacity={0}
        />
      ))}
      {[tone.casing, g.fill].map((color, i) => (
        <circle
          key={i}
          ref={(el) => {
            pressRefs.current[i] = el
          }}
          cx={first.x}
          cy={first.y}
          r={g.press.radius}
          fill="none"
          stroke={color}
          strokeWidth={i === 0 ? style.stroke.core + 2 : style.stroke.core}
          opacity={0}
        />
      ))}
      <g ref={cursorRef} transform={`translate(${first.x} ${first.y}) scale(${scale})`}>
        {stacked(style, 'guide', (p, k) => <path key={k} d={POINTER_PATH} {...p} strokeWidth={(p.strokeWidth as number) / scale} />, { widthScale: 0.55, dashed: false })}
        <path d={POINTER_PATH} fill={g.fill} fillOpacity={0.9} />
      </g>
      <g ref={tagRef} transform={`translate(${first.x + g.size * 0.8} ${first.y + g.size * 0.9})`}>
        <rect width={tagW} height={tagH} rx={tagH / 2} fill={tone.casing} fillOpacity={0.94} stroke={tone.halo} strokeOpacity={0.55} strokeWidth={1.5} />
        <text x={tagW / 2} y={tagH / 2} textAnchor="middle" dominantBaseline="central" fill="#fff" fontFamily={style.bubble.fontFamily} fontSize={tagFont} fontWeight={600}>
          {tagText}
        </text>
      </g>
    </g>
  )
}
