// Shared SVG/HTML building blocks for annotation renderers. Every stroke is painted as halo -> casing -> core
// (DESIGN's strokeLayers) so marks stay legible on light and dark backdrops; tone is also carried by dash + glyph.
import { useLayoutEffect, useRef, type CSSProperties, type ReactElement, type ReactNode, type SVGProps } from 'react'
import type { AnnotationTone } from '../../../shared/protocol'
import { strokeLayers, type AnnotationStyle, type StrokeLayer, type ToneGlyph } from '../../design/annotation-style'
import type { Size } from '../geometry'

export type Lifecycle = 'enter' | 'exit'

export const lifeClass = (exiting: boolean): string => (exiting ? 'ov-exit' : 'ov-enter')

export function overlayCss(style: AnnotationStyle): string {
  const { transition: t, pulse: p } = style
  return `
.ov-root{position:absolute;left:0;top:0;overflow:hidden;pointer-events:none;user-select:none;-webkit-user-select:none;font-family:${style.bubble.fontFamily}}
.ov-svg{position:absolute;left:0;top:0;pointer-events:none;overflow:visible}
.ov-html{position:absolute;pointer-events:none;box-sizing:border-box}
.ov-mark{transform-box:fill-box;transform-origin:center}
.ov-enter{animation:ov-in ${t.enterMs}ms ${t.easing} both}
.ov-exit{animation:ov-out ${t.exitMs}ms ${t.easing} forwards}
.ov-fade-enter{animation:ov-fade-in ${t.enterMs}ms ${t.easing} both}
.ov-pulse{transform-box:fill-box;transform-origin:center;animation:ov-pulse ${p.periodMs}ms ${p.easing} var(--ov-iter,infinite) both}
@keyframes ov-in{from{opacity:0;transform:scale(${t.enterFromScale})}to{opacity:1;transform:scale(1)}}
@keyframes ov-out{from{opacity:1}to{opacity:0}}
@keyframes ov-fade-in{from{opacity:0}to{opacity:1}}
@keyframes ov-pulse{from{opacity:${p.opacityFrom};transform:scale(${p.scaleFrom})}to{opacity:${p.opacityTo};transform:scale(${p.scaleTo})}}
@keyframes ov-draw{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}
@keyframes ov-press{from{opacity:.85}to{opacity:0}}
`
}

export function iterations(style: AnnotationStyle, tone: AnnotationTone): CSSProperties {
  const n = style.tones[tone].pulseIterations
  return { ['--ov-iter' as string]: String(n) }
}

type StrokeProps = Pick<
  SVGProps<SVGElement>,
  'stroke' | 'strokeWidth' | 'strokeOpacity' | 'fill' | 'strokeLinecap' | 'strokeLinejoin' | 'strokeDasharray'
>

// Renders `draw` once per layer (halo, casing, core). The tone's dash pattern applies to the core only so the
// solid casing shows through the gaps.
export function stacked(
  style: AnnotationStyle,
  tone: AnnotationTone,
  draw: (props: StrokeProps, key: number) => ReactElement,
  opts: { widthScale?: number; dashed?: boolean; layers?: readonly StrokeLayer[] } = {},
): ReactElement[] {
  const dash = opts.dashed === false ? null : style.tones[tone].dash
  return (opts.layers ?? strokeLayers(style, tone, opts.widthScale ?? 1)).map((l, i) =>
    draw(
      {
        stroke: l.color,
        strokeWidth: l.width,
        strokeOpacity: l.opacity,
        fill: 'none',
        strokeLinecap: style.stroke.linecap,
        strokeLinejoin: style.stroke.linejoin,
        strokeDasharray: i === 2 && dash ? dash : undefined,
      },
      i,
    ),
  )
}

// halo/casing/core for a thin line of exactly `coreWidth` px (underlines): the same recipe with slim fringes.
export function slimLayers(style: AnnotationStyle, tone: AnnotationTone, coreWidth: number): StrokeLayer[] {
  const t = style.tones[tone]
  const fringe = Math.max(1.2, 1.2 * style.scale)
  return [
    { color: t.halo, width: coreWidth + fringe * 4, opacity: 0.92 },
    { color: t.casing, width: coreWidth + fringe * 2, opacity: 1 },
    { color: t.core, width: coreWidth, opacity: 1 },
  ]
}

// Soft glow without SVG filters (a full-screen blur per mark would repaint every pulse frame): three wide,
// translucent strokes of the tone colour approximate it. Decorative only; the stack underneath carries legibility.
export function glowStack(style: AnnotationStyle, tone: AnnotationTone, draw: (props: StrokeProps, key: number) => ReactElement): ReactElement[] {
  const core = style.tones[tone].core
  const strength = style.glow.opacity / 0.55
  return [
    [1.0, 0.09],
    [0.62, 0.15],
    [0.3, 0.22],
  ].map(([k, o], i) =>
    draw(
      { stroke: core, strokeWidth: style.stroke.halo + style.glow.blur * k, strokeOpacity: o * strength, fill: 'none', strokeLinecap: 'round', strokeLinejoin: 'round' },
      i,
    ),
  )
}

export function Defs({ style }: { style: AnnotationStyle }): ReactElement {
  return (
    <defs>
      <filter id="ov-feather" x="-25%" y="-40%" width="150%" height="180%">
        <feGaussianBlur stdDeviation={Math.max(0.01, style.spotlight.feather / 2)} />
      </filter>
    </defs>
  )
}

// Layer geometry shared by badge/tick discs: radii of the core, casing and halo circles for a disc of `diameter`.
export function discRadii(style: AnnotationStyle, diameter: number): { core: number; casing: number; halo: number } {
  const casingExtra = (style.stroke.casing - style.stroke.core) / 2
  const haloExtra = (style.stroke.halo - style.stroke.casing) / 2
  const core = diameter / 2
  return { core, casing: core + casingExtra, halo: core + casingExtra + haloExtra }
}

export function Disc({ cx, cy, diameter, tone, style }: { cx: number; cy: number; diameter: number; tone: AnnotationTone; style: AnnotationStyle }): ReactElement {
  const r = discRadii(style, diameter)
  const t = style.tones[tone]
  return (
    <g>
      <circle cx={cx} cy={cy} r={r.halo} fill={t.halo} fillOpacity={0.92} />
      <circle cx={cx} cy={cy} r={r.casing} fill={t.casing} />
      <circle cx={cx} cy={cy} r={r.core} fill={t.core} />
    </g>
  )
}

const GLYPH_PATHS: Record<ToneGlyph, { d: string; filled?: boolean; extra?: string }> = {
  pointer: { d: 'M6 3.5 L6 19.5 L10.2 15.6 L13 21 L15.6 19.7 L12.9 14.4 L18.5 14.4 Z', filled: true },
  check: { d: 'M5.5 12.8 L10 17.3 L18.8 7.2' },
  alert: { d: 'M12 5.5 L12 13.6', extra: 'dot' },
  stop: { d: 'M8.6 3.4 H15.4 L20.6 8.6 V15.4 L15.4 20.6 H8.6 L3.4 15.4 V8.6 Z M7.6 12 H16.4' },
}

// A tone glyph drawn into a `size` box centred at (cx, cy), in `color`. 24-unit grid scaled to size.
export function Glyph({ kind, cx, cy, size, color, weight = 2.6 }: { kind: ToneGlyph; cx: number; cy: number; size: number; color: string; weight?: number }): ReactElement {
  const g = GLYPH_PATHS[kind]
  const s = size / 24
  return (
    <g transform={`translate(${cx - size / 2} ${cy - size / 2}) scale(${s})`}>
      <path d={g.d} fill={g.filled ? color : 'none'} stroke={color} strokeWidth={weight} strokeLinecap="round" strokeLinejoin="round" />
      {g.extra === 'dot' ? <circle cx={12} cy={18.4} r={1.7} fill={color} /> : null}
    </g>
  )
}

// Round tone badge (glyph on the tone colour) for use inside HTML labels.
export function GlyphChip({ tone, style, size }: { tone: AnnotationTone; style: AnnotationStyle; size: number }): ReactElement {
  const t = style.tones[tone]
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden style={{ flex: 'none', display: 'block' }}>
      <circle cx={12} cy={12} r={11.5} fill={t.core} stroke={t.casing} strokeWidth={1.5} />
      <Glyph kind={t.glyph} cx={12} cy={12} size={15} color={t.onCore} weight={2.8} />
    </svg>
  )
}

// Reports the laid-out (untransformed) size of its content so the scene can place it without overlap.
export function Measured({
  id,
  onSize,
  style,
  className,
  children,
}: {
  id: string
  onSize: (id: string, size: Size) => void
  style?: CSSProperties
  className?: string
  children: ReactNode
}): ReactElement {
  const ref = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const report = (): void => onSize(id, { width: el.offsetWidth, height: el.offsetHeight })
    report()
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(report)
    ro.observe(el)
    return () => ro.disconnect()
  }, [id, onSize])
  return (
    <div ref={ref} className={className} style={style}>
      {children}
    </div>
  )
}
