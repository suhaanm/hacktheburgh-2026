// Screen-level furniture: the captions band (bottom) and the help-level chip echo (top). Both are pictures
// only; the real controls live in the dock window.
import { useEffect, useState, type ReactElement } from 'react'
import type { CaptionSpeaker } from '../../../shared/protocol'
import type { AnnotationStyle } from '../../design/annotation-style'
import { LEVEL_SUPPORT } from '../../design/levels'
import type { Size } from '../geometry'
import { Measured } from './common'
import type { CaptionState, ChipState } from '../store'

// Long streaming lines keep the most recent words visible.
export function tailText(text: string, max = 110): string {
  if (text.length <= max) return text
  const cut = text.slice(text.length - max)
  const space = cut.indexOf(' ')
  return `… ${space > 0 && space < 40 ? cut.slice(space + 1) : cut}`
}

export function CaptionBand({
  caption,
  topY,
  speakerName,
  style,
  viewport,
  onSize,
}: {
  caption: CaptionState
  // null = the usual bottom position; a number = pinned to the top at this y (when the bottom would cover a mark).
  topY: number | null
  speakerName: string
  style: AnnotationStyle
  viewport: Size
  onSize: (id: string, size: Size) => void
}): ReactElement {
  const c = style.caption
  const exiting = caption.exitingAt !== null
  const text = tailText(caption.text)
  // At most ~60% of the screen. Once the line needs more than one row the band takes its full width, so streaming
  // words never make it jump sideways; the text is clamped to two rows.
  const maxW = Math.min(c.maxWidth, viewport.width * 0.6)
  const wide = text.length > 56 * (c.fontSize > 20 ? 0.6 : 1)
  return (
    <div className="ov-html" style={{ left: 0, width: '100%', ...(topY === null ? { bottom: c.bottomInset } : { top: topY }), display: 'flex', justifyContent: 'center' }}>
      <Measured
        id="caption"
        onSize={onSize}
        className={exiting ? 'ov-exit' : 'ov-fade-enter'}
        style={{
          width: wide ? maxW : 'max-content',
          maxWidth: maxW,
          backdropFilter: style.highContrast ? undefined : 'blur(14px) saturate(1.4)',
          WebkitBackdropFilter: style.highContrast ? undefined : 'blur(14px) saturate(1.4)',
          maxHeight: viewport.height * c.maxHeightFraction,
          overflow: 'hidden',
          background: c.background,
          color: c.color,
          border: c.border,
          borderRadius: c.radius,
          padding: `${c.padding.y}px ${c.padding.x}px`,
          fontFamily: c.fontFamily,
          fontSize: c.fontSize,
          lineHeight: c.lineHeight,
          fontWeight: 600,
          boxShadow: '0 4px 16px rgba(5, 7, 13, 0.28)',
        }}
      >
        <div style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
          {speakerName ? <span style={{ fontSize: c.speakerFontSize, color: c.speakerColor, fontWeight: 700, marginRight: 8, letterSpacing: 0.2 }}>{speakerName}</span> : null}
          <span>{text}</span>
        </div>
      </Measured>
    </div>
  )
}

export function speakerLabel(speaker: CaptionSpeaker, names: Partial<Record<CaptionSpeaker, string>>): string {
  if (names[speaker] !== undefined) return names[speaker] as string
  if (speaker === 'user') return 'You'
  if (speaker === 'assistant') return 'Assistant'
  return ''
}

const BAR_STAGGER_MS = 90
const BARS = [1, 2, 3, 4] as const

// When bar `i` (1 = bottom) flips between its old and new state, in ms after the change starts. Draining empties
// the top bar first; filling (a step back up) fills from the bottom.
function barDelay(i: number, from: number, to: number): number {
  return (to < from ? from - i : i - from - 1) * BAR_STAGGER_MS
}

// The level chip echo. On a level change the bars start at the OLD level and, one frame after mount, switch to the
// new one so the CSS transition shows them draining (top bar first, 90 ms apart); the label cross-fades.
// `progress` (harness only) renders a fixed frame of that animation (0 = before, 1 = after) with no transitions.
export function LevelChipEcho({
  chip,
  style,
  top,
  onSize,
  progress,
}: {
  chip: ChipState
  style: AnnotationStyle
  top: number
  onSize: (id: string, size: Size) => void
  progress?: number
}): ReactElement {
  const l = style.levelChip
  const exiting = chip.exitingAt !== null
  const to = LEVEL_SUPPORT[chip.level]
  const from = chip.from ? LEVEL_SUPPORT[chip.from.level] : to
  const animate = chip.from !== null && !style.reducedMotion && l.changeMs > 0 && progress === undefined
  const [settled, setSettled] = useState(!animate)
  const [showOld, setShowOld] = useState(chip.from !== null && chip.from.label !== chip.label)
  useEffect(() => {
    if (!animate) return
    const frame = requestAnimationFrame(() => setSettled(true))
    const done = setTimeout(() => setShowOld(false), l.changeMs + BAR_STAGGER_MS * 3 + 100)
    return () => {
      cancelAnimationFrame(frame)
      clearTimeout(done)
    }
  }, [animate, l.changeMs])
  const total = l.changeMs + BAR_STAGGER_MS * 3
  const frozen = progress !== undefined ? progress * total : null
  const filledNow = (i: number): boolean => {
    const target = i <= to
    if (frozen !== null) return frozen >= barDelay(i, from, to) + l.changeMs * 0.35 ? target : i <= from
    return settled ? target : i <= from
  }
  // Old label fades out first, then the new one fades in: never two labels at half strength on top of each other.
  const t = frozen !== null ? Math.min(1, Math.max(0, frozen / total)) : settled ? 1 : 0
  const oldOpacity = Math.max(0, 1 - 2 * t)
  const newOpacity = Math.max(0, 2 * t - 1)
  const crossfade = chip.from !== null && chip.from.label !== chip.label && showOld

  return (
    <div key={chip.changedAt} className="ov-html" style={{ left: 0, width: '100%', top, display: 'flex', justifyContent: 'center' }}>
      <Measured
        id="chip"
        onSize={onSize}
        className={exiting ? 'ov-exit' : 'ov-fade-enter'}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: l.fontSize * 0.5,
          background: l.background,
          color: l.color,
          border: l.border,
          borderRadius: l.radius,
          padding: `${l.padding.y}px ${l.padding.x}px`,
          fontFamily: style.bubble.fontFamily,
          fontSize: l.fontSize,
          fontWeight: 700,
          boxShadow: '0 4px 14px rgba(5, 7, 13, 0.3)',
        }}
      >
        <span aria-hidden style={{ display: 'inline-flex', alignItems: 'flex-end', gap: l.fontSize * 0.15, height: l.fontSize }}>
          {BARS.map((i) => (
            <span
              key={i}
              style={{
                width: l.fontSize * 0.2,
                height: l.fontSize * (0.35 + i * 0.16),
                borderRadius: 2,
                background: filledNow(i) ? '#fff' : 'rgba(255,255,255,0.28)',
                transition: frozen !== null || !animate ? 'none' : `background ${l.changeMs * 0.45}ms ease ${barDelay(i, from, to)}ms`,
              }}
            />
          ))}
        </span>
        <span style={{ display: 'inline-grid' }}>
          {crossfade && chip.from ? (
            <span style={{ gridArea: '1 / 1', opacity: oldOpacity, transition: frozen !== null ? 'none' : `opacity ${l.changeMs * 0.4}ms ease` }}>{chip.from.label}</span>
          ) : null}
          <span style={{ gridArea: '1 / 1', opacity: crossfade ? newOpacity : 1, transition: frozen !== null ? 'none' : `opacity ${l.changeMs * 0.4}ms ease ${l.changeMs * 0.45}ms` }}>{chip.label}</span>
        </span>
      </Measured>
    </div>
  )
}
