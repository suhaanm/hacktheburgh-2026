// GET /coach/next?person= -> the coach brain's decision for this moment, and POST /coach/feedback with the worker's response.
//   { meta, data: { action: "silent"|"nudge"|"annotate"|"takeover_offer", message, why, target: {zone, label_hint, role_hint}|null,
//                   level, decision_id, ... } }
// Only `annotate` and `nudge` with a zone become a ring. `takeover_offer` (the agent offers to do the step) is not drawn by the
// desktop: it is an offer for the dashboard and the agent, and the desktop never acts on it.
import type { HelpLevel } from '../../shared/protocol'
import { levelFromEngine } from '../coach-chip'
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
  decisionId: string | null
}

const ACTIONS: readonly CoachAction[] = ['silent', 'nudge', 'annotate', 'takeover_offer']
const ID_RE = /^[A-Za-z0-9_.:-]{1,80}$/
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
    decisionId: typeof body.decision_id === 'string' && ID_RE.test(body.decision_id) ? body.decision_id : null,
  }
}
