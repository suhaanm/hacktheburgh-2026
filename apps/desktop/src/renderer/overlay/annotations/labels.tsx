// Adapted from farzaa/clicky (MIT) — leanring-buddy/OverlayWindow.swift (pointing bubble: scale-bounce entrance, character-by-character typing)
// HTML labels: ring label pill, highlightText note, and the speech bubble. HTML (not SVG text) so words wrap properly at
// large sizes; position comes from layout.ts and the real size is reported back via <Measured>.
import { useEffect, useState, type CSSProperties, type ReactElement } from 'react'
import type { AnnotationTone } from '../../../shared/protocol'
import type { AnnotationStyle } from '../../design/annotation-style'
import type { Size } from '../geometry'
import type { PlacedLabel } from '../layout'
import { GlyphChip, Measured, lifeClass } from './common'

interface Common {
  id: string
  style: AnnotationStyle
  placed: PlacedLabel
  exiting: boolean
  onSize: (id: string, size: Size) => void
}

export function LabelPill({ id, text, tone, scale, maxWidth, style, placed, exiting, onSize, compact = false }: Common & { text: string; tone: AnnotationTone; scale: number; maxWidth: number; compact?: boolean }): ReactElement {
  const b = style.bubble
  const fs = b.fontSize * scale
  const bw = compact ? Math.max(1, style.scale) : b.borderWidth
  const pad = compact ? `${fs * 0.3}px ${fs * 0.65}px` : `${b.padding.y * 0.7}px ${b.padding.x * 0.8}px`
  return (
    <div className="ov-html" style={{ left: placed.rect.x, top: placed.rect.y, width: 'max-content', maxWidth }}>
      <Measured
        id={id}
        onSize={onSize}
        className={lifeClass(exiting)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: fs * (compact ? 0.4 : 0.45),
          background: b.background,
          color: b.color,
          border: `${bw}px solid ${b.borderColor}`,
          borderRadius: compact ? fs : b.radius,
          padding: pad,
          boxShadow: compact ? '0 2px 8px rgba(5, 7, 13, 0.3)' : b.shadow,
          whiteSpace: compact ? 'nowrap' : undefined,
          fontFamily: b.fontFamily,
          fontSize: fs,
          lineHeight: b.lineHeight,
          fontWeight: 700,
        }}
      >
        <GlyphChip tone={tone} style={style} size={Math.round(fs * (compact ? 1.1 : 1.25))} />
        <span>{text}</span>
      </Measured>
    </div>
  )
}

function useTyped(text: string, enabled: boolean): number {
  const [n, setN] = useState(enabled ? 0 : text.length)
  useEffect(() => {
    if (!enabled || text.length === 0) {
      setN(text.length)
      return
    }
    setN(0)
    const per = Math.min(40, Math.max(12, 700 / text.length))
    let i = 0
    const timer = setInterval(() => {
      i += 1
      setN(i)
      if (i >= text.length) clearInterval(timer)
    }, per)
    return () => clearInterval(timer)
  }, [text, enabled])
  return Math.min(n, text.length)
}

export function BubbleView({ id, text, anchor, style, placed, exiting, onSize, typed: typeIn = true }: Common & { text: string; anchor: { x: number; y: number }; typed?: boolean }): ReactElement {
  const b = style.bubble
  const typed = useTyped(text, typeIn && !style.reducedMotion)
  const rect = placed.rect
  const bw = b.borderWidth
  const side = placed.side
  const s = b.tail * 1.45
  const half = s / 2
  // Tail is a rotated square whose two outer borders form the pointer; same fill as the bubble hides the seam.
  const along = side === 'below' || side === 'above' ? Math.min(rect.w - b.radius - half, Math.max(b.radius + half, placed.attach.x - rect.x)) : Math.min(rect.h - b.radius - half, Math.max(b.radius + half, placed.attach.y - rect.y))
  const tail: CSSProperties = { position: 'absolute', width: s, height: s, background: b.background, transform: 'rotate(45deg)', boxSizing: 'border-box', borderStyle: 'solid', borderColor: b.borderColor, borderWidth: 0 }
  if (side === 'below') Object.assign(tail, { left: along - half, top: -half - bw / 2, borderTopWidth: bw, borderLeftWidth: bw })
  if (side === 'above') Object.assign(tail, { left: along - half, bottom: -half - bw / 2, borderBottomWidth: bw, borderRightWidth: bw })
  if (side === 'right') Object.assign(tail, { top: along - half, left: -half - bw / 2, borderBottomWidth: bw, borderLeftWidth: bw })
  if (side === 'left') Object.assign(tail, { top: along - half, right: -half - bw / 2, borderTopWidth: bw, borderRightWidth: bw })
  void anchor
  return (
    <div className="ov-html" style={{ left: rect.x, top: rect.y, width: 'max-content', maxWidth: b.maxWidth }}>
      <Measured
        id={id}
        onSize={onSize}
        className={lifeClass(exiting)}
        style={{
          position: 'relative',
          background: b.background,
          color: b.color,
          border: `${bw}px solid ${b.borderColor}`,
          borderRadius: b.radius,
          padding: `${b.padding.y}px ${b.padding.x}px`,
          boxShadow: b.shadow,
          fontFamily: b.fontFamily,
          fontSize: b.fontSize,
          lineHeight: b.lineHeight,
          fontWeight: 600,
        }}
      >
        <span aria-label={text}>
          {text.slice(0, typed)}
          <span style={{ visibility: 'hidden' }}>{text.slice(typed)}</span>
        </span>
        <span style={tail} />
      </Measured>
    </div>
  )
}
