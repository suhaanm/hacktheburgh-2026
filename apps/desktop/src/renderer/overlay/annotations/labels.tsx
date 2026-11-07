// The words on the screen: one compact note chip for a ring (its step number and its note), a bubble, and a highlightText note.
// Calm and small: one line in the body face at about 11.5 px, the step number in a small mono pill, a hairline edge that reads on any
// page, no tail, no paragraph. HTML (not SVG text) so the text is measured by the browser; position comes from layout.ts and the real
// size is reported back via <Measured>. The full sentence is not here: it belongs to the decision (the dashboard's "Why this?").
import type { CSSProperties, ReactElement } from 'react'
import type { AnnotationTone } from '../../../shared/protocol'
import type { AnnotationStyle } from '../../design/annotation-style'
import type { Size } from '../geometry'
import type { PlacedLabel } from '../layout'
import { compactNote } from '../note-text'
import { Measured, lifeClass } from './common'

interface Common {
  id: string
  style: AnnotationStyle
  placed: PlacedLabel
  exiting: boolean
  onSize: (id: string, size: Size) => void
}

/** The small numbered pill: mono numerals on the tone colour. */
export function StepPill({ n, tone, style }: { n: number; tone: AnnotationTone; style: AnnotationStyle }): ReactElement {
  const t = style.tones[tone]
  const b = style.badge
  return (
    <span
      aria-label={`Step ${n}`}
      style={{
        flex: 'none',
        boxSizing: 'border-box',
        minWidth: b.diameter,
        height: b.diameter,
        padding: `0 ${b.padX * 0.7}px`,
        borderRadius: b.diameter / 2,
        background: t.core,
        color: t.onCore,
        fontFamily: b.fontFamily,
        fontSize: b.fontSize,
        fontWeight: b.fontWeight,
        fontVariantNumeric: 'tabular-nums',
        lineHeight: `${b.diameter}px`,
        textAlign: 'center',
      }}
    >
      {n}
    </span>
  )
}

function chipStyle(style: AnnotationStyle, scale: number, hasPill: boolean): CSSProperties {
  const b = style.bubble
  return {
    display: 'flex',
    alignItems: 'center',
    gap: b.fontSize * 0.45,
    boxSizing: 'border-box',
    background: b.background,
    color: b.color,
    border: `${b.borderWidth}px solid ${b.borderColor}`,
    borderRadius: b.radius,
    padding: `${b.padding.y}px ${b.padding.x}px ${b.padding.y}px ${hasPill ? b.padding.y + 1 : b.padding.x}px`,
    boxShadow: b.shadow,
    whiteSpace: 'nowrap',
    fontFamily: b.fontFamily,
    fontSize: b.fontSize * scale,
    lineHeight: b.lineHeight,
    fontWeight: b.fontWeight,
    letterSpacing: '0.005em',
  }
}

/** A chip on a ring (or a note on highlighted text): an optional step pill, then the words. */
export function LabelPill({ id, text, tone, step, scale = 1, maxWidth, style, placed, exiting, onSize }: Common & { text: string; tone: AnnotationTone; step?: number; scale?: number; maxWidth: number }): ReactElement {
  const b = style.bubble
  const shown = compactNote(text, b.maxChars)
  return (
    <div className="ov-html" style={{ left: placed.rect.x, top: placed.rect.y, width: 'max-content', maxWidth }}>
      <Measured id={id} onSize={onSize} className={lifeClass(exiting)} style={chipStyle(style, scale, step !== undefined)}>
        {step !== undefined ? <StepPill n={step} tone={tone} style={style} /> : null}
        {shown !== '' ? (
          <span aria-label={text} style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {shown}
          </span>
        ) : null}
      </Measured>
    </div>
  )
}

/** A bubble annotation: the same quiet chip (no tail, no typing effect), anchored to its point. */
export function BubbleView({ id, text, style, placed, exiting, onSize }: Common & { text: string; anchor: { x: number; y: number }; typed?: boolean }): ReactElement {
  const b = style.bubble
  const shown = compactNote(text, b.maxChars)
  return (
    <div className="ov-html" style={{ left: placed.rect.x, top: placed.rect.y, width: 'max-content', maxWidth: b.maxWidth }}>
      <Measured id={id} onSize={onSize} className={lifeClass(exiting)} style={chipStyle(style, 1, false)}>
        <span aria-label={text} style={{ overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {shown}
        </span>
      </Measured>
    </div>
  )
}
