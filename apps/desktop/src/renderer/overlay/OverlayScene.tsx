// The whole overlay picture as a pure function of (state, viewport, style). Used by the real overlay window and by
// the headless render harness, so what the harness screenshots is what the user sees.
import { useCallback, useMemo, useState, type ReactElement } from 'react'
import type { CaptionSpeaker } from '../../shared/protocol'
import type { AnnotationStyle } from '../design/annotation-style'
import { ArrowMark, BadgeMark, HighlightMarks, RingMark, SpotlightMark, TickMark } from './annotations/shapes'
import { BubbleView, LabelPill } from './annotations/labels'
import { CaptionBand, LevelChipEcho, speakerLabel } from './annotations/chrome'
import { Defs, overlayCss } from './annotations/common'
import { GhostCursor } from './annotations/GhostCursor'
import { normToPx, type Size } from './geometry'
import { CHIP_TOP, LABEL_SCALE, chipRect, chooseCaptionRect, labelKey, planScene, shortLabel } from './scene-plan'
import type { OverlayState } from './store'

export interface SceneProps {
  state: OverlayState
  viewport: Size
  style: AnnotationStyle
  captionsEnabled: boolean
  speakerNames?: Partial<Record<CaptionSpeaker, string>>
  // Harness only: freeze ghost-cursor animations at this many ms.
  freezeGhostMs?: number | null
  // Harness stills render bubbles fully typed.
  typeBubbles?: boolean
  // Harness only: freeze the level-chip echo at this point of its change animation (0 = before, 1 = after).
  chipProgress?: number
}

const RANK: Record<string, number> = { spotlight: 0, highlightText: 1, ring: 2, arrow: 3, tick: 4, badge: 5, ghostCursor: 6, bubble: 7 }

export function OverlayScene({ state, viewport, style, captionsEnabled, speakerNames = {}, freezeGhostMs = null, typeBubbles = true, chipProgress }: SceneProps): ReactElement {
  const [sizes, setSizes] = useState<Record<string, Size>>({})
  const onSize = useCallback((id: string, size: Size) => {
    setSizes((prev) => {
      const old = prev[id]
      if (old && Math.abs(old.width - size.width) < 0.5 && Math.abs(old.height - size.height) < 0.5) return prev
      return { ...prev, [id]: size }
    })
  }, [])

  const showCaption = captionsEnabled && state.caption !== null
  const captionSize = sizes.caption ?? { width: Math.min(style.caption.maxWidth, viewport.width * 0.6) * 0.7, height: style.caption.fontSize * style.caption.lineHeight + style.caption.padding.y * 2 }
  const chip = useMemo(() => (state.chip ? chipRect(sizes.chip ?? { width: 260 * style.scale, height: style.levelChip.fontSize * 2 }, viewport, CHIP_TOP) : undefined), [state.chip, sizes.chip, viewport, style])
  // Two passes: first the marks (without captions), then the caption goes where it covers none of them.
  const marks = useMemo(() => planScene(state.annotations, viewport, style, sizes, { chip }).marks, [state.annotations, viewport, style, sizes, chip])
  const captionPlace = useMemo(() => (showCaption ? chooseCaptionRect(marks, captionSize, viewport, style, chip) : null), [showCaption, marks, captionSize, viewport, style, chip])
  const chrome = useMemo(() => ({ caption: captionPlace?.rect, chip }), [captionPlace, chip])
  const plan = useMemo(() => planScene(state.annotations, viewport, style, sizes, chrome), [state.annotations, viewport, style, sizes, chrome])
  const css = useMemo(() => overlayCss(style), [style])
  const entries = useMemo(() => [...state.annotations].sort((a, b) => (RANK[a.annotation.kind] ?? 9) - (RANK[b.annotation.kind] ?? 9)), [state.annotations])

  return (
    <div className="ov-root" style={{ width: viewport.width, height: viewport.height }}>
      <style>{css}</style>
      <svg className="ov-svg" width={viewport.width} height={viewport.height} viewBox={`0 0 ${viewport.width} ${viewport.height}`}>
        <Defs style={style} />
        {entries.map((e) => {
          const a = e.annotation
          const exiting = e.exitingAt !== null
          switch (a.kind) {
            case 'spotlight': {
              const rect = plan.spotlights.get(a.id)
              return rect ? <SpotlightMark key={a.id} id={a.id} rect={rect} tone={a.tone} style={style} viewport={viewport} exiting={exiting} /> : null
            }
            case 'highlightText': {
              const rects = plan.highlights.get(a.id)
              return rects ? <HighlightMarks key={a.id} rects={rects} tone={a.tone} style={style} exiting={exiting} /> : null
            }
            case 'ring': {
              const ring = plan.rings.get(a.id)
              if (!ring) return null
              return (
                <g key={a.id}>
                  <RingMark rect={ring.rect} tone={a.tone} style={style} exiting={exiting} />
                  {ring.step && a.step !== undefined ? <BadgeMark at={ring.step} n={a.step} tone={a.tone} style={style} exiting={exiting} /> : null}
                </g>
              )
            }
            case 'arrow': {
              const arrow = plan.arrows.get(a.id)
              return arrow ? <ArrowMark key={a.id} plan={arrow} tone={a.tone} style={style} exiting={exiting} /> : null
            }
            case 'tick': {
              const tick = plan.ticks.get(a.id)
              return tick ? <TickMark key={a.id} box={tick.box} center={tick.center} ok={a.ok} tone={a.ok ? style.tick.okTone : style.tick.notOkTone} style={style} exiting={exiting} /> : null
            }
            case 'badge': {
              const at = plan.badges.get(a.id)
              return at ? <BadgeMark key={a.id} at={at} n={a.n} tone={a.tone} style={style} exiting={exiting} /> : null
            }
            case 'ghostCursor': {
              const path = plan.ghosts.get(a.id)
              return path ? <GhostCursor key={a.id} path={path} style={style} viewport={viewport} pressAtEnd={a.pressAtEnd === true} exiting={exiting} freezeAtMs={freezeGhostMs} /> : null
            }
            default:
              return null
          }
        })}
      </svg>
      {entries.map((e) => {
        const a = e.annotation
        const exiting = e.exitingAt !== null
        if (a.kind === 'ring' && a.label) {
          const key = labelKey(a.id, 'label')
          const placed = plan.labels.get(key)
          return placed ? <LabelPill key={key} id={key} compact text={shortLabel(a.label)} tone={a.tone} scale={LABEL_SCALE} maxWidth={style.bubble.maxWidth} style={style} placed={placed} exiting={exiting} onSize={onSize} /> : null
        }
        if (a.kind === 'highlightText' && a.note) {
          const key = labelKey(a.id, 'note')
          const placed = plan.labels.get(key)
          return placed ? <LabelPill key={key} id={key} text={a.note} tone={a.tone} scale={0.85} maxWidth={style.highlightText.noteMaxWidth} style={style} placed={placed} exiting={exiting} onSize={onSize} /> : null
        }
        if (a.kind === 'bubble') {
          const key = labelKey(a.id, 'bubble')
          const placed = plan.labels.get(key)
          return placed ? <BubbleView key={key} id={key} typed={typeBubbles} text={a.text} anchor={normToPx(a.at, viewport)} style={style} placed={placed} exiting={exiting} onSize={onSize} /> : null
        }
        return null
      })}
      {showCaption && state.caption ? <CaptionBand caption={state.caption} topY={captionPlace?.atTop ? captionPlace.rect.y : null} speakerName={speakerLabel(state.caption.speaker, speakerNames)} style={style} viewport={viewport} onSize={onSize} /> : null}
      {state.chip ? <LevelChipEcho chip={state.chip} style={style} top={CHIP_TOP} onSize={onSize} progress={chipProgress} /> : null}
    </div>
  )
}
