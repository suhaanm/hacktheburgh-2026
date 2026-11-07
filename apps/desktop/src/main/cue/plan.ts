// A CueDecision -> what goes on the screen, as plain data (no clocks, no Electron). Two layers draw it:
//   the overlay (click-through): the ring, the silent tick, the ghost cursor, through its existing annotation API;
//   the Cue panel (tappable, never takes focus): the chip, the question card, the offer.
// What appears is decided here by code from the tier (the engine's escalation) and the help level (tokens.ts), never by a model.
import type { Annotation, NormBox, NormPoint } from '../../shared/protocol'
import { CUE_TOKENS, levelTokens, type RingWeight } from './tokens'
import { capChars, pathPhrase, reasonLine, type CueDecision, type CueKind } from './types'

export interface CueOptionView {
  id: string
  label: string
  // The digit on the row's key cap.
  key: string
}

export interface CuePlan {
  kind: CueKind
  ring: { box: NormBox; weight: RingWeight; exact: boolean } | null
  tick: { box: NormBox } | null
  chip: { text: string; stepN: number | null } | null
  ghost: { to: NormPoint } | null
  question: { text: string; options: CueOptionView[] } | null
  offer: { text: string } | null
  whisper: { lineId: string; text: string } | null
  // What the panel sits near and never covers: the target's box, when there is one.
  anchor: NormBox | null
  // The "Why this?" popover: the reason line and the plain phrase. Null when the engine sent neither (then there is nothing to show).
  why: { reason: string | null; phrase: string | null; simulated: boolean } | null
}

export interface PlanOptions {
  // The step's number in the walkthrough, for the level-1 step pill.
  stepN: number | null
  // The worker asked to be shown ("Show me"): the ghost cursor plays at any tier.
  ghostRequested?: boolean
}

export const FALLBACK_QUESTION = 'What are you trying to do?'
export const FALLBACK_OFFER = 'Want a hand?'

export const toNormBox = (b: [number, number, number, number]): NormBox => ({ xmin: b[1], ymin: b[0], xmax: b[3], ymax: b[2] })
export const boxCentre = (b: NormBox): NormPoint => ({ x: (b.xmin + b.xmax) / 2, y: (b.ymin + b.ymax) / 2 })

export function planCue(d: CueDecision, o: PlanOptions): CuePlan | null {
  if (d.kind === 'none') return null
  const asked = d.trigger === 'asked'
  const box = d.target?.box_2d && d.target.confidence >= CUE_TOKENS.minTargetConfidence ? toNormBox(d.target.box_2d) : null
  const base: CuePlan = { kind: d.kind, ring: null, tick: null, chip: null, ghost: null, question: null, offer: null, whisper: null, anchor: box, why: null }

  if (d.kind === 'confirm') return box ? { ...base, tick: { box } } : null

  if (d.kind === 'ask') {
    if (!d.options) return null
    const text = d.say.question ?? (d.say.chip || FALLBACK_QUESTION)
    return { ...base, question: { text, options: d.options.map((opt, i) => ({ id: opt.id, label: opt.label, key: String(i + 1) })) } }
  }

  if (d.kind === 'offer') return { ...base, offer: { text: d.say.chip || FALLBACK_OFFER } }

  // kind === 'cue'
  const tier = d.tier ?? 1
  const lv = levelTokens(d.why.level, asked)
  const chipText = capChars(d.say.chip || d.step?.label || '', CUE_TOKENS.chip.maxChars)
  // A cue must show something: with no ring to draw, the chip stands alone whatever the level says.
  const wantsChip = chipText !== '' && (tier >= lv.chipFromTier || !box)
  const chip = wantsChip ? { text: chipText, stepN: lv.stepPill ? d.step?.n ?? o.stepN ?? null : null } : null
  const ring = box ? { box, weight: (chip ? 'regular' : lv.ringWhenQuiet) as RingWeight, exact: d.target?.source === 'dom' } : null
  const ghost = box && (tier >= CUE_TOKENS.ghostFromTier || o.ghostRequested === true) ? { to: boxCentre(box) } : null
  const whisper = tier === CUE_TOKENS.whisperTier && d.say.whisper && d.say.whisper_id ? { lineId: d.say.whisper_id, text: d.say.whisper } : null
  const reason = reasonLine(d)
  const phrase = pathPhrase(d.why.path_prob)
  const why = reason || phrase ? { reason, phrase, simulated: d.why.origin === 'synthetic' } : null
  if (!ring && !chip) return null
  return { ...base, ring, chip, ghost, whisper, why }
}

export interface CueMarkIds {
  ring: string
  tick: string
  ghost: string
}
export const markIds = (seq: number): CueMarkIds => ({ ring: `${CUE_TOKENS.idPrefix}ring-${seq}`, tick: `${CUE_TOKENS.idPrefix}tick-${seq}`, ghost: `${CUE_TOKENS.idPrefix}ghost-${seq}` })

// `weight` is the one field the overlay's ring does not know yet (CONTRACT-CHANGE sent to the lead): its schema strips it, so until it
// exists a light ring is drawn regular. Nothing else about the marks depends on it.
export type CueRing = Extract<Annotation, { kind: 'ring' }> & { weight?: RingWeight }

/** The overlay marks for a plan: the ring, the confirmation tick, the ghost cursor. The chip and the card are the panel's, not the overlay's. */
export function buildMarks(plan: CuePlan, seq: number, o: { ghost?: boolean } = {}): Annotation[] {
  const ids = markIds(seq)
  const out: Annotation[] = []
  const guard = CUE_TOKENS.timing.untouchedMs + 2_000 // the overlay's own limit if main ever forgets to clear
  if (plan.ring) {
    const ring: CueRing = { id: ids.ring, kind: 'ring', tone: 'guide', box: plan.ring.box, exact: plan.ring.exact, weight: plan.ring.weight, ttlMs: guard }
    out.push(ring)
  }
  if (plan.tick) out.push({ id: ids.tick, kind: 'tick', tone: 'success', box: plan.tick.box, ok: true, ttlMs: CUE_TOKENS.timing.confirmMs })
  if (plan.ghost && o.ghost !== false) out.push({ id: ids.ghost, kind: 'ghostCursor', tone: 'guide', path: [plan.ghost.to], pressAtEnd: true })
  return out
}

/** Every overlay id a plan may have drawn, for clearing (clearing an id that was never shown is harmless). */
export const allMarkIds = (seq: number): string[] => Object.values(markIds(seq))
