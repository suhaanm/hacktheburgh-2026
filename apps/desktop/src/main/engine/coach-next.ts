// GET /coach/next?person= -> the coach brain's decision for this moment, and POST /coach/feedback with the worker's response.
//   { meta, data: { action: "silent"|"nudge"|"annotate"|"takeover_offer", message, why, target: {zone, label_hint, role_hint}|null,
//                   level, decision_id, ... } }
// Only `annotate` and `nudge` with a zone become a ring. `takeover_offer` (the agent offers to do the step) is not drawn by the
// desktop: it is an offer for the dashboard and the agent, and the desktop never acts on it.
import type { ChipFade, HelpLevel } from '../../shared/protocol'
import { chipFromEngine, levelFromEngine } from '../coach-chip'
import { toTarget, type DomTarget } from '../dom-ground/protocol'

export type CoachAction = 'silent' | 'nudge' | 'annotate' | 'takeover_offer'
export type FeedbackOutcome = 'followed' | 'dismissed' | 'repeated' | 'undone'

export interface CoachDecision {
  action: CoachAction
  message: string
  why: string
  // The element to point at, by capture zone; null when the decision has none.
  target: Extract<DomTarget, { zone: string }> | null
  level: HelpLevel | null
  // How much of the chip the engine says to show at this level (study mode included).
  chip: ChipFade | null
  decisionId: string | null
  // The engine's reason codes (silent: on_track, gate_cooldown, already_prompted, no_active_task ...). They tell the desktop WHY it is
  // quiet, which is how it knows a prompt it drew was acted on (the engine stops saying already_prompted) or is moot (the case ended).
  reasons: string[]
  // The step the worker is on, and the step ids the coach says were missed (as the engine names them).
  step: string | null
  missed: string[]
  // The hazard model's chance of no progress in the next minute (body.p_stuck: finite, 0..1), else null. ONE poll serves two readers: the
  // coach brain acts on the decision, and the awareness layer's stuck trigger reads this number (see pStuckForTrigger).
  pStuck: number | null
}

// POST /coach/feedback -> { decision_id, outcome, recorded, note?, ... }. `recorded: false` with the note "already recorded" means the
// engine had already labelled the decision with this outcome itself (it labels a step done within 30 s of a prompt as followed).
export interface FeedbackResult {
  ok: boolean
  recorded: boolean | null
  note: string | null
}

const ACTIONS: readonly CoachAction[] = ['silent', 'nudge', 'annotate', 'takeover_offer']
const ID_RE = /^[A-Za-z0-9_.:-]{1,80}$/
const CODE_RE = /^[a-z0-9_]{1,40}$/
const STEP_RE = /^[A-Za-z0-9_.-]{1,60}$/
const codes = (v: unknown, re: RegExp): string[] => (Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string' && re.test(x)).slice(0, 24) : [])
const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)

export function parseCoachNext(raw: unknown): CoachDecision | null {
  if (!isObj(raw)) return null
  const body = isObj(raw.data) ? raw.data : raw
  // An action this app does not know is treated as silence, never as something to act on.
  const action = typeof body.action === 'string' && (ACTIONS as readonly string[]).includes(body.action) ? (body.action as CoachAction) : 'silent'
  const t = isObj(body.target) ? toTarget({ zone: body.target.zone, label_hint: body.target.label_hint, role_hint: body.target.role_hint }) : null
  return {
    action,
    message: typeof body.message === 'string' ? body.message.replace(/\s+/g, ' ').trim().slice(0, 200) : '',
    why: typeof body.why === 'string' ? body.why.slice(0, 200) : '',
    target: t && 'zone' in t ? t : null,
    level: levelFromEngine(body.level),
    chip: chipFromEngine(body.chip),
    decisionId: typeof body.decision_id === 'string' && ID_RE.test(body.decision_id) ? body.decision_id : null,
    reasons: codes(body.reason_codes, CODE_RE),
    step: typeof body.step === 'string' && STEP_RE.test(body.step) ? body.step : null,
    missed: codes(body.missed, STEP_RE),
    pStuck: typeof body.p_stuck === 'number' && Number.isFinite(body.p_stuck) && body.p_stuck >= 0 && body.p_stuck <= 1 ? body.p_stuck : null,
  }
}

// Reasons under which the engine has no episode to score: p_stuck is then absent or meaningless, so the trigger gets no reading.
const NO_EPISODE = new Set(['no_events', 'no_pack', 'no_active_task', 'study_mode', 'study_post_test', 'study_off'])

/** The stuck probability the awareness trigger may use: null when the engine has no episode to score (or gave no number). */
export function pStuckForTrigger(d: Pick<CoachDecision, 'pStuck' | 'reasons'>): number | null {
  return d.pStuck !== null && !d.reasons.some((r) => NO_EPISODE.has(r)) ? d.pStuck : null
}
