// Pure reducer for OverlayCommand -> what is currently on screen. Time is passed in (no clocks here), so the
// lifecycle (enter, ttl, exit, caption linger, stale guards) is unit-testable and identical in the harness.
import type { Annotation, CaptionSpeaker, HelpLevel, OverlayCommand } from '../../shared/protocol'
import type { AnnotationStyle } from '../design/annotation-style'
import { planFlight } from './flight'
import { normToPx, type Size } from './geometry'

export interface ActiveAnnotation {
  annotation: Annotation
  shownAt: number
  expiresAt: number | null
  exitingAt: number | null
}

export interface CaptionState {
  speaker: CaptionSpeaker
  text: string
  final: boolean
  updatedAt: number
  expiresAt: number
  exitingAt: number | null
}

export interface ChipState {
  level: HelpLevel
  label: string
  // What the chip said before this change (null the first time), so the echo can drain/fill from there.
  from: { level: HelpLevel; label: string } | null
  changedAt: number
  expiresAt: number
  exitingAt: number | null
}

export interface OverlayState {
  annotations: ActiveAnnotation[]
  caption: CaptionState | null
  chip: ChipState | null
  // Survives the chip fading out, so a later level change still animates from the previous level.
  lastChip: { level: HelpLevel; label: string } | null
}

export const EMPTY_OVERLAY_STATE: OverlayState = { annotations: [], caption: null, chip: null, lastChip: null }

export interface ReduceContext {
  now: number
  viewport: Size
  style: AnnotationStyle
}

// Nothing may sit on the user's real screen forever if main forgets to clear it.
export const STALE_GUARD_MS = 120_000
const TICK_TTL_MS = 3_500
const BUBBLE_TTL_MS = 12_000
const GHOST_AFTERGLOW_MS = 2_200
const CHIP_VISIBLE_MS = 6_000
const CAPTION_STREAMING_GUARD_MS = 20_000

export function captionLingerMs(text: string): number {
  return Math.min(9_000, Math.max(3_000, 2_500 + text.length * 55))
}

export function defaultTtlMs(annotation: Annotation, ctx: ReduceContext): number {
  if (annotation.ttlMs !== undefined) return annotation.ttlMs
  switch (annotation.kind) {
    case 'tick':
      return TICK_TTL_MS
    case 'bubble':
      return BUBBLE_TTL_MS
    case 'ghostCursor': {
      const pts = annotation.path.map((p) => normToPx(p, ctx.viewport))
      const plan = planFlight(pts, ctx.style.ghostCursor.flight, { viewport: ctx.viewport })
      return plan.totalMs + GHOST_AFTERGLOW_MS
    }
    default:
      return STALE_GUARD_MS
  }
}

export function reduceOverlay(state: OverlayState, cmd: OverlayCommand, ctx: ReduceContext): OverlayState {
  switch (cmd.type) {
    case 'show': {
      let annotations = state.annotations
      for (const annotation of cmd.annotations) {
        const existing = annotations.find((a) => a.annotation.id === annotation.id)
        const entry: ActiveAnnotation = {
          annotation,
          // Same id and kind = an update in place: no replayed entrance animation.
          shownAt: existing && existing.annotation.kind === annotation.kind && existing.exitingAt === null ? existing.shownAt : ctx.now,
          expiresAt: ctx.now + defaultTtlMs(annotation, ctx),
          exitingAt: null,
        }
        annotations = existing ? annotations.map((a) => (a === existing ? entry : a)) : [...annotations, entry]
      }
      return { ...state, annotations }
    }
    case 'clear': {
      const ids = cmd.ids ? new Set(cmd.ids) : null
      return {
        ...state,
        annotations: state.annotations.map((a) => (a.exitingAt === null && (!ids || ids.has(a.annotation.id)) ? { ...a, exitingAt: ctx.now } : a)),
      }
    }
    case 'caption': {
      if (cmd.text.trim() === '') return { ...state, caption: state.caption ? { ...state.caption, exitingAt: state.caption.exitingAt ?? ctx.now } : null }
      return {
        ...state,
        caption: {
          speaker: cmd.speaker,
          text: cmd.text,
          final: cmd.final,
          updatedAt: ctx.now,
          expiresAt: ctx.now + (cmd.final ? captionLingerMs(cmd.text) : CAPTION_STREAMING_GUARD_MS),
          exitingAt: null,
        },
      }
    }
    case 'chip': {
      const from = state.lastChip && state.lastChip.level !== cmd.level ? state.lastChip : null
      return {
        ...state,
        chip: { level: cmd.level, label: cmd.label, from, changedAt: ctx.now, expiresAt: ctx.now + CHIP_VISIBLE_MS, exitingAt: null },
        lastChip: { level: cmd.level, label: cmd.label },
      }
    }
  }
}

// Moves expired entries to "exiting" and drops finished exits. Returns the same object when nothing changed.
export function advance(state: OverlayState, ctx: ReduceContext): OverlayState {
  const exitMs = ctx.style.transition.exitMs
  let changed = false
  const annotations: ActiveAnnotation[] = []
  for (const a of state.annotations) {
    if (a.exitingAt !== null && ctx.now - a.exitingAt >= exitMs) {
      changed = true
      continue
    }
    if (a.exitingAt === null && a.expiresAt !== null && ctx.now >= a.expiresAt) {
      changed = true
      annotations.push({ ...a, exitingAt: ctx.now })
      continue
    }
    annotations.push(a)
  }
  const step = <T extends { expiresAt: number; exitingAt: number | null }>(v: T | null): T | null => {
    if (!v) return v
    if (v.exitingAt !== null) {
      if (ctx.now - v.exitingAt >= exitMs) {
        changed = true
        return null
      }
      return v
    }
    if (ctx.now >= v.expiresAt) {
      changed = true
      return { ...v, exitingAt: ctx.now }
    }
    return v
  }
  const caption = step(state.caption)
  const chip = step(state.chip)
  return changed ? { ...state, annotations, caption, chip } : state
}

// Earliest time `advance` has something to do; null when the scene is idle.
export function nextDeadline(state: OverlayState, exitMs: number): number | null {
  const times: number[] = []
  for (const a of state.annotations) times.push(a.exitingAt !== null ? a.exitingAt + exitMs : a.expiresAt ?? Infinity)
  for (const v of [state.caption, state.chip]) if (v) times.push(v.exitingAt !== null ? v.exitingAt + exitMs : v.expiresAt)
  const min = Math.min(...times)
  return Number.isFinite(min) ? min : null
}
