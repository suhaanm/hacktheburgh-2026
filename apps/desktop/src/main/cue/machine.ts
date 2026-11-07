// The Cue state machine: what is on the screen, and what to do when something happens. A pure reducer in the style of the overlay's store:
// time is passed in, nothing here touches Electron, a timer or the network; it returns the next state and a list of effects for the
// controller to carry out. That is what makes the rules (one cue at a time, 20 seconds, 12 seconds, never a stale ring) testable.
//
// The rules, from docs/REQ7_PLAN.md section 4 and the CUE-UX brief:
//   - At most one cue is visible. A new cue replaces the old one in one step (the overlay clears and shows together: a 150 ms cross-fade).
//   - A cue goes on progress, on dismiss, after 20 s untouched (12 s for the question, 14 s for the offer), or when its target is gone.
//   - A box that no longer matches the screen is hidden at once and re-grounded for a moment; if it is not found the cue is dropped.
//   - Every cue that was shown ends with exactly one feedback event; the episode ends with `resolved` or `abandoned`.
import type { Annotation, NormBox } from '../../shared/protocol'
import { buildFeedback, type CueFeedbackEvent, type FeedbackHow } from './feedback'
import { admit, type Policy } from './guards'
import type { CueView } from './ipc'
import { allMarkIds, buildMarks, planCue, toNormBox, type CuePlan } from './plan'
import { CUE_TOKENS } from './tokens'
import { buildView } from './view'
import { isProgress, sameCue, type CueDecision } from './types'
import { OTHER_OPTION_ID } from './voice'

export interface Visible {
  seq: number
  decision: CueDecision
  plan: CuePlan
  shownAt: number
  touchedAt: number
  // The ghost-cursor demonstration was requested by the worker ("Show me").
  ghostRequested: boolean
  popover: boolean
  // A chip that is the collapsed answer of the question card, waiting for the engine's cue for the chosen step.
  pending: boolean
  // The ring was hidden because the screen changed; when it happened (null: not hidden).
  hiddenAt: number | null
  stepN: number | null
}

export interface Episode {
  id: string
  startedAt: number
  questions: number
  shown: number
  stepsDone: number
  progressed: boolean
  last: CueDecision
}

export interface MachineState {
  seq: number
  visible: Visible | null
  episode: Episode | null
  // When each cue, question or offer was shown (confirmations excluded), for the caps.
  recent: number[]
  // Cues the worker has already seen end: never drawn again, whatever the engine repeats.
  ended: string[]
  // "I know this": episode/step pairs Cue stays quiet about.
  known: string[]
  // No new unprompted cue before this time (the decision's own cooldown after a dismissal or a timeout).
  cooldownUntil: number
}

export const INITIAL_MACHINE: MachineState = { seq: 0, visible: null, episode: null, recent: [], ended: [], known: [], cooldownUntil: 0 }

export type MachineEvent =
  | { type: 'decision'; decision: CueDecision }
  | { type: 'answer'; id: string }
  | { type: 'dismiss'; how: 'esc' | 'click' }
  | { type: 'why'; open: boolean }
  | { type: 'show_me' }
  | { type: 'know_this' }
  | { type: 'offer'; yes: boolean }
  | { type: 'touch' }
  | { type: 'progress'; stepId: string | null }
  | { type: 'stale' }
  | { type: 'retarget'; box: [number, number, number, number] }
  | { type: 'tick' }
  | { type: 'stop'; how: 'killed' | 'off' | 'quiet' }

export type Effect =
  // One atomic change of the overlay: clearing the old marks and showing the new ones together is the cross-fade.
  | { type: 'overlay'; clear: string[]; show: Annotation[] }
  // The panel: a view (or null to hide it), and what it keeps clear of.
  // `keep`: the chip is the card collapsing (its answer): it stays where the card was instead of moving next to the old target.
  | { type: 'panel'; view: CueView; anchor: NormBox | null; kind: 'chip' | 'card'; keep: boolean }
  | { type: 'keys'; on: boolean; options: number }
  | { type: 'feedback'; event: CueFeedbackEvent }
  | { type: 'speak'; lineId: string; asked: boolean }
  | { type: 'listen'; options: Array<{ id: string; label: string }> }
  | { type: 'converse' }
  | { type: 'reground'; box: NormBox }
  // The engine should be asked again straight away (the worker said yes to an offer).
  | { type: 'poll'; asked: boolean }

export interface Env {
  now: number
  policy: Policy
  chord?: string
}

export interface Result {
  state: MachineState
  effects: Effect[]
}

const T = CUE_TOKENS.timing
const ENDED_MAX = 64

// The engine sends no decision id: a cue is its episode, kind, step, options and tier. A higher tier is a new key (escalation), the same tier again is not.
export const cueKey = (d: CueDecision): string => d.decision_id ?? `${d.episode_id}/${d.kind}/${d.step?.id ?? ''}/${(d.options ?? []).map((o) => o.id).join(',')}/${d.tier ?? 0}`
const knownKey = (d: CueDecision): string => `${d.episode_id}/${d.step?.id ?? ''}`

/** How long this cue may sit untouched. */
function lifeMs(v: Visible): number {
  if (v.pending) return T.answerWaitMs
  const own = v.decision.kind === 'ask' ? T.questionIgnoreMs : v.decision.kind === 'offer' ? T.offerIgnoreMs : v.decision.kind === 'confirm' ? T.confirmMs : T.untouchedMs
  // The engine's own display limit can only shorten it.
  return v.decision.expires_in_s !== null ? Math.min(own, v.decision.expires_in_s * 1000) : own
}

/** When the controller next needs a `tick`, or null when nothing is waiting on the clock. */
export function nextDeadline(s: MachineState): number | null {
  const v = s.visible
  if (!v) return null
  if (v.hiddenAt !== null) return v.hiddenAt + T.regroundMs
  return (v.decision.kind === 'confirm' ? v.shownAt : v.touchedAt) + lifeMs(v)
}

const feedback = (e: Parameters<typeof buildFeedback>[0]): Effect => ({ type: 'feedback', event: buildFeedback(e) })
const panelKind = (v: Visible): 'chip' | 'card' => (v.plan.question || v.plan.offer ? 'card' : 'chip')

function panelEffect(v: Visible, env: Env, from?: 'question'): Effect {
  return { type: 'panel', view: buildView({ seq: v.seq, plan: v.plan, popover: v.popover, ghost: v.ghostRequested || v.plan.ghost !== null, pending: v.pending, from, chord: env.chord ?? 'Alt+' }), anchor: v.plan.anchor, kind: panelKind(v), keep: v.pending }
}

const keysFor = (v: Visible | null): Effect => ({ type: 'keys', on: v !== null && (v.plan.question !== null || v.plan.offer !== null), options: v?.plan.question?.options.length ?? 0 })

// Ends the visible cue: the marks and the panel go, the keys are released, the feedback is sent. `ended` remembers it so it is not redrawn.
function end(s: MachineState, env: Env, o: { event?: 'accepted' | 'dismissed' | 'answered' | 'abandoned' | 'know_this'; how?: FeedbackHow; optionId?: string; cooldown?: boolean; keepPanel?: boolean }): Result {
  const v = s.visible
  if (!v) return { state: s, effects: [] }
  const effects: Effect[] = [{ type: 'overlay', clear: allMarkIds(v.seq), show: [] }]
  if (!o.keepPanel) effects.push({ type: 'panel', view: null, anchor: null, kind: 'chip', keep: false })
  effects.push({ type: 'keys', on: false, options: 0 })
  // A pending chip (the collapsed answer) was already reported as answered; it ends without a second label.
  if (o.event && !v.pending) effects.push(feedback({ event: o.event, decision: v.decision, how: o.how, optionId: o.optionId, elapsedMs: env.now - v.shownAt }))
  const key = cueKey(v.decision)
  const ended = s.ended.includes(key) ? s.ended : [...s.ended, key].slice(-ENDED_MAX)
  const cooldownUntil = o.cooldown ? Math.max(s.cooldownUntil, env.now + Math.min(300, v.decision.cooldown_s) * 1000) : s.cooldownUntil
  return { state: { ...s, visible: null, ended, cooldownUntil }, effects }
}

function closeEpisode(s: MachineState, env: Env, effects: Effect[]): MachineState {
  const e = s.episode
  if (!e) return s
  if (e.shown > 0) {
    const how: FeedbackHow = e.progressed ? 'progress' : 'episode_end'
    effects.push(feedback({ event: e.progressed ? 'resolved' : 'abandoned', scope: 'episode', decision: e.last, how, elapsedMs: env.now - e.startedAt }))
  }
  return { ...s, episode: null }
}

function show(s: MachineState, env: Env, d: CueDecision, plan: CuePlan, effects: Effect[]): MachineState {
  const seq = s.seq + 1
  const episode0 = s.episode && s.episode.id === d.episode_id ? s.episode : null
  const episode: Episode = episode0 ?? { id: d.episode_id, startedAt: env.now, questions: 0, shown: 0, stepsDone: 0, progressed: false, last: d }
  const stepN = d.step?.n ?? episode.stepsDone + 1
  const visible: Visible = { seq, decision: d, plan, shownAt: env.now, touchedAt: env.now, ghostRequested: false, popover: false, pending: false, hiddenAt: null, stepN }
  // Marks and panel for the plan; the chip's pill uses the walkthrough count when the engine did not number the step.
  const planned = planCue(d, { stepN }) ?? plan
  const v: Visible = { ...visible, plan: planned }
  const old = s.visible
  effects.push({ type: 'overlay', clear: old ? allMarkIds(old.seq) : [], show: buildMarks(planned, seq) })
  effects.push(panelEffect(v, env))
  effects.push(keysFor(v))
  if (planned.whisper) effects.push({ type: 'speak', lineId: planned.whisper.lineId, asked: d.trigger === 'asked' })
  if (planned.question) effects.push({ type: 'listen', options: planned.question.options.map((o) => ({ id: o.id, label: o.label })) })
  effects.push(feedback({ event: 'shown', decision: d, elapsedMs: 0 }))
  const countsAgainstCaps = d.kind !== 'confirm'
  return {
    ...s,
    seq,
    visible: v,
    episode: { ...episode, last: d, shown: episode.shown + 1, questions: episode.questions + (d.kind === 'ask' ? 1 : 0) },
    recent: countsAgainstCaps ? [...s.recent.filter((t) => env.now - t < CUE_TOKENS.caps.windowMs), env.now] : s.recent,
  }
}

function onDecision(s: MachineState, env: Env, d: CueDecision): Result {
  const effects: Effect[] = []
  let state = s

  if (d.kind === 'none') {
    // Any quiet answer takes the cue down (the engine keeps returning a cue that should stay, with the reason "persisting"). Its reason
    // codes say why: progress or recovered is the worker getting past the step; the rest is the system ending it.
    const reasons = d.why.reasons
    const progress = isProgress(d)
    if (progress && state.episode && (d.episode_id === '' || d.episode_id === state.episode.id)) state = { ...state, episode: { ...state.episode, progressed: true } }
    const v = state.visible
    // The silent confirmation tick is its own: it goes after confirmMs whatever the next poll says.
    if (v && v.decision.kind !== 'confirm') {
      const has = (...ids: string[]): boolean => ids.some((id) => reasons.includes(id))
      const how: FeedbackHow = progress ? (env.now - v.shownAt > T.acceptWindowMs ? 'late' : 'progress') : has('timeout', 'waiting_escalation') ? 'timeout' : has('quiet') ? 'quiet' : has('denied', 'no_consent', 'unsure_away') ? 'off' : 'superseded'
      const r = end(state, env, { event: progress ? 'accepted' : 'abandoned', how })
      state = r.state
      effects.push(...r.effects)
    }
    if (progress) state = closeEpisode(state, env, effects)
    return { state, effects }
  }

  const key = cueKey(d)
  if (state.ended.includes(key)) return { state, effects }
  if (state.known.includes(knownKey(d)) && d.trigger !== 'asked') return { state, effects }

  const continuing = state.visible !== null && sameCue(state.visible.decision, d)
  const adm = admit(d, { now: env.now, policy: env.policy, recent: state.recent, episodeQuestions: state.episode && state.episode.id === d.episode_id ? state.episode.questions : 0, continuing })
  if (!adm.ok) {
    // Switched off, killed, quiet or suppressed: whatever is up goes too. A cap or a rule only keeps the new cue from showing.
    if (state.visible && (adm.reason === 'killed' || adm.reason === 'off' || adm.reason === 'quiet' || adm.reason === 'suppressed')) {
      const r = end(state, env, { event: 'abandoned', how: adm.reason === 'quiet' ? 'quiet' : 'off' })
      return { state: r.state, effects: r.effects }
    }
    return { state, effects }
  }
  if (d.trigger !== 'asked' && d.kind !== 'confirm' && !continuing && env.now < state.cooldownUntil) return { state, effects }

  const stepN = d.step?.n ?? (state.episode && state.episode.id === d.episode_id ? state.episode.stepsDone + 1 : 1)
  const plan = planCue(d, { stepN, ghostRequested: continuing ? state.visible?.ghostRequested : false })
  if (!plan) return { state, effects }

  if (continuing && state.visible) {
    // The same cue growing (a higher tier): updated in place, same marks, no new entrance. The ghost and a whisper are added when they arrive.
    const v = state.visible
    // A new tier (`new`) means the engine just escalated: the clock for it starts now.
    const next: Visible = { ...v, decision: d, plan, hiddenAt: v.hiddenAt, touchedAt: d.new ? env.now : v.touchedAt }
    const changed = JSON.stringify(plan) !== JSON.stringify(v.plan)
    if (!changed) return { state: { ...state, visible: { ...v, decision: d, touchedAt: next.touchedAt } }, effects }
    if (v.hiddenAt === null) effects.push({ type: 'overlay', clear: [], show: buildMarks(plan, v.seq, { ghost: !v.plan.ghost || false }) })
    effects.push(panelEffect(next, env))
    if (plan.whisper && !v.plan.whisper) effects.push({ type: 'speak', lineId: plan.whisper.lineId, asked: d.trigger === 'asked' })
    return { state: { ...state, visible: next, episode: state.episode ? { ...state.episode, last: d } : state.episode }, effects }
  }

  // A different cue. If the step moved on inside the same episode, the old cue's step was done: that is progress, not a rejection.
  if (state.visible) {
    const v = state.visible
    const moved = v.decision.episode_id === d.episode_id && (v.decision.step?.id ?? null) !== (d.step?.id ?? null) && v.decision.kind === 'cue' && !v.pending
    const how: FeedbackHow = moved ? (env.now - v.shownAt > T.acceptWindowMs ? 'late' : 'progress') : 'superseded'
    if (!v.pending) effects.push(feedback({ event: moved ? 'accepted' : 'abandoned', decision: v.decision, how, elapsedMs: env.now - v.shownAt }))
    if (moved && state.episode) state = { ...state, episode: { ...state.episode, stepsDone: state.episode.stepsDone + 1, progressed: true } }
    const key0 = cueKey(v.decision)
    state = { ...state, ended: state.ended.includes(key0) ? state.ended : [...state.ended, key0].slice(-ENDED_MAX) }
  }
  if (state.episode && state.episode.id !== d.episode_id) state = closeEpisode(state, env, effects)

  // `show` clears the old marks in the same overlay effect as it shows the new ones.
  const shownState = show({ ...state, visible: state.visible }, env, d, plan, effects)
  return { state: shownState, effects }
}

export function reduce(s: MachineState, ev: MachineEvent, env: Env): Result {
  const v = s.visible
  switch (ev.type) {
    case 'decision':
      return onDecision(s, env, ev.decision)

    case 'touch':
      return v ? { state: { ...s, visible: { ...v, touchedAt: env.now } }, effects: [] } : { state: s, effects: [] }

    case 'why': {
      if (!v || !v.plan.chip) return { state: s, effects: [] }
      const next = { ...v, popover: ev.open, touchedAt: env.now }
      return { state: { ...s, visible: next }, effects: [panelEffect(next, env)] }
    }

    case 'show_me': {
      if (!v || !v.plan.anchor || v.ghostRequested) return { state: s, effects: [] }
      const plan = planCue(v.decision, { stepN: v.stepN, ghostRequested: true })
      if (!plan) return { state: s, effects: [] }
      const next: Visible = { ...v, plan, ghostRequested: true, popover: false, touchedAt: env.now }
      // Asking to be shown is the worker asking for more help: reported as accepted with how=show_me (the cue is still up, so this is not its last event).
      const effects: Effect[] = [{ type: 'overlay', clear: [], show: buildMarks(plan, v.seq) }, panelEffect(next, env), feedback({ event: 'accepted', decision: v.decision, how: 'show_me', elapsedMs: env.now - v.shownAt })]
      return { state: { ...s, visible: next }, effects }
    }

    case 'answer': {
      if (!v || !v.plan.question) return { state: s, effects: [] }
      const options = v.plan.question.options
      const chosen = options.find((o) => o.id === ev.id)
      if (!chosen && ev.id !== OTHER_OPTION_ID) return { state: s, effects: [] }
      const effects: Effect[] = [feedback({ event: 'answered', decision: v.decision, optionId: ev.id, elapsedMs: env.now - v.shownAt })]
      const episode = s.episode ? { ...s.episode, questions: Math.max(s.episode.questions, 1) } : s.episode
      if (!chosen) {
        // "Something else": the question is answered, nothing is guessed. The conversation (Live, opt-in) is the controller's to start.
        const r = end({ ...s, episode }, env, {})
        return { state: r.state, effects: [...effects, ...r.effects, { type: 'converse' }] }
      }
      // The card collapses into the chip for the chosen step; the engine's cue for that step replaces it when it comes.
      const plan: CuePlan = { kind: 'cue', ring: null, tick: null, chip: { text: chosen.label, stepN: null }, ghost: null, question: null, offer: null, whisper: null, anchor: v.plan.anchor, why: null }
      const next: Visible = { ...v, plan, pending: true, popover: false, shownAt: env.now, touchedAt: env.now }
      effects.push(panelEffect(next, env, 'question'), { type: 'keys', on: false, options: 0 })
      return { state: { ...s, episode, visible: next, ended: s.ended.includes(cueKey(v.decision)) ? s.ended : [...s.ended, cueKey(v.decision)] }, effects: [...effects, { type: 'poll', asked: false }] }
    }

    case 'dismiss': {
      if (!v) return { state: s, effects: [] }
      const r = end(s, env, { event: 'dismissed', how: ev.how, cooldown: true })
      return { state: r.state, effects: r.effects }
    }

    case 'offer': {
      if (!v || !v.plan.offer) return { state: s, effects: [] }
      if (ev.yes) {
        const r = end(s, env, { event: 'accepted', how: 'accepted_offer' })
        return { state: r.state, effects: [...r.effects, { type: 'poll', asked: true }] }
      }
      const r = end(s, env, { event: 'dismissed', how: 'declined', cooldown: true })
      return { state: r.state, effects: r.effects }
    }

    case 'know_this': {
      if (!v) return { state: s, effects: [] }
      const r = end(s, env, { event: 'know_this', cooldown: true })
      const known = s.known.includes(knownKey(v.decision)) ? s.known : [...s.known, knownKey(v.decision)].slice(-ENDED_MAX)
      return { state: { ...r.state, known }, effects: r.effects }
    }

    case 'progress': {
      let state = s
      if (state.episode) state = { ...state, episode: { ...state.episode, progressed: true, stepsDone: state.episode.stepsDone + 1 } }
      if (!v) return { state, effects: [] }
      // Progress on some other step is not the cue being followed.
      if (ev.stepId !== null && v.decision.step && ev.stepId !== v.decision.step.id && !v.pending) return { state, effects: [] }
      const r = end(state, env, { event: 'accepted', how: env.now - v.shownAt > T.acceptWindowMs ? 'late' : 'progress' })
      return { state: r.state, effects: r.effects }
    }

    case 'stale': {
      if (!v || !v.plan.ring || v.hiddenAt !== null) return { state: s, effects: [] }
      // Never leave a stale ring: the marks go now, and the engine gets a moment to find the target again.
      const next: Visible = { ...v, hiddenAt: env.now }
      return { state: { ...s, visible: next }, effects: [{ type: 'overlay', clear: allMarkIds(v.seq), show: [] }, { type: 'panel', view: null, anchor: null, kind: 'chip', keep: false }, { type: 'reground', box: v.plan.ring.box }] }
    }

    case 'retarget': {
      // The ring's element moved (the page scrolled) or came back after being lost: the ring and the panel go with it. A cue with no ring has nothing to move.
      if (!v || !v.plan.ring) return { state: s, effects: [] }
      const box = toNormBox(ev.box)
      const wasHidden = v.hiddenAt !== null
      const plan: CuePlan = { ...v.plan, ring: { ...v.plan.ring, box }, anchor: box, ghost: v.plan.ghost ? { to: { x: (box.xmin + box.xmax) / 2, y: (box.ymin + box.ymax) / 2 } } : null }
      const next: Visible = { ...v, plan, hiddenAt: null, touchedAt: wasHidden ? env.now : v.touchedAt }
      // Moving a ring that is on screen updates it in place (same id: no new entrance); the ghost is only drawn again when everything was cleared.
      return { state: { ...s, visible: next }, effects: [{ type: 'overlay', clear: [], show: buildMarks(plan, v.seq, { ghost: wasHidden && (v.ghostRequested || plan.ghost !== null) }) }, panelEffect(next, env)] }
    }

    case 'tick': {
      if (!v) return { state: s, effects: [] }
      if (v.hiddenAt !== null && env.now >= v.hiddenAt + T.regroundMs) {
        const r = end(s, env, { event: 'abandoned', how: 'stale' })
        return { state: r.state, effects: r.effects }
      }
      const due = (v.decision.kind === 'confirm' ? v.shownAt : v.touchedAt) + lifeMs(v)
      if (v.hiddenAt === null && env.now >= due) {
        if (v.decision.kind === 'confirm') {
          // The silent tick is the overlay's own (it expires by itself); there is nothing to report.
          const r = end(s, env, {})
          return { state: r.state, effects: r.effects }
        }
        // Ignored: a question or an offer is dismissed (ignoring is an answer); a cue nobody touched is abandoned.
        const ignored = v.decision.kind === 'ask' || v.decision.kind === 'offer'
        const r = end(s, env, { event: ignored ? 'dismissed' : 'abandoned', how: 'timeout', cooldown: true })
        return { state: r.state, effects: r.effects }
      }
      return { state: s, effects: [] }
    }

    case 'stop': {
      if (!v) return { state: s, effects: [] }
      const r = end(s, env, ev.how === 'killed' ? {} : { event: 'abandoned', how: ev.how === 'quiet' ? 'quiet' : 'off' })
      return { state: r.state, effects: r.effects }
    }
  }
}
