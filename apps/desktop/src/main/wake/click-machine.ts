// "Click when I say so", as a pure state machine. The model proposes (the Live tool `do_it_for_me`); this decides, in code, and fails closed at
// every step. It never clicks: it emits EFFECTS that the shell performs (show a card, ask the agent service to run, stop it).
//
//   idle ──listen_on──▶ listening ──wake──▶ session ──tool_call──▶ rung_missing   (no rung record: say "I will show you instead", keep guiding)
//                                              │                └─▶ card_shown ──allow by MOUSE──▶ running ──run_result──▶ session
//                                              │                                └─cancel / timeout / session ended──▶ cancelled
//   any state ──kill──▶ killed ──resume──▶ listening (or idle)       only resume leaves killed
//
// Hard rules, each one tested:
//   * No tool call does anything without a Live session (no_session).
//   * While the persisted rung record is absent the answer is always `first_supervised_test_pending`; no card is shown.
//   * The card's Allow counts ONLY if it arrived as a real mouse click. The same choice by voice, key or timer is ignored (and a timer means Cancel).
//   * One request at a time (busy). Kill wins from any state, stops a run, closes the card and answers a waiting call.
//   * Never unattended, never a purchase, never a real account: those limits live in the agent service's guards, not here; this machine only
//     decides whether the request may reach them at all.
export type ClickState =
  | { k: 'idle' }
  | { k: 'listening' }
  | { k: 'session' }
  | { k: 'rung_missing' }
  | { k: 'card_shown'; cardId: number }
  | { k: 'running'; sessionOpen: boolean }
  | { k: 'cancelled' }
  | { k: 'killed'; resumeTo: 'idle' | 'listening' }

export type RefusalReason = 'first_supervised_test_pending' | 'no_session' | 'busy' | 'killed' | 'target_not_found' | 'worker_cancelled' | 'session_ended'

export type ToolAnswer = { ok: true; started: true } | { ok: false; reason: RefusalReason }

export type ClickEvent =
  | { t: 'listen_on' }
  | { t: 'listen_off' }
  | { t: 'wake' }
  | { t: 'session_ended' }
  | { t: 'tool_call'; rungCleared: boolean; targetFound: boolean }
  | { t: 'card_choice'; choice: 'allow' | 'cancel'; via: 'mouse' | 'key' | 'voice' | 'timer' }
  | { t: 'run_result'; ok: boolean }
  | { t: 'kill' }
  | { t: 'resume' }

export type ClickEffect =
  | { t: 'answer'; answer: ToolAnswer }
  | { t: 'say'; line: 'show_instead' | 'done' | 'did_not_work' | 'stopped' }
  | { t: 'show_card'; cardId: number }
  | { t: 'close_card' }
  | { t: 'request_run' }
  | { t: 'stop_run' }
  | { t: 'ignored'; why: 'allow_not_by_mouse' | 'stale' }

export interface Step {
  state: ClickState
  effects: ClickEffect[]
}

export const INITIAL: ClickState = { k: 'idle' }

const inSession = (s: ClickState): boolean => s.k === 'session' || s.k === 'rung_missing' || s.k === 'cancelled' || s.k === 'card_shown' || s.k === 'running'

export function reduce(s: ClickState, e: ClickEvent, nextCardId = 1): Step {
  // Kill wins from everywhere.
  if (e.t === 'kill') {
    if (s.k === 'killed') return { state: s, effects: [] }
    const effects: ClickEffect[] = []
    if (s.k === 'card_shown') effects.push({ t: 'close_card' }, { t: 'answer', answer: { ok: false, reason: 'killed' } })
    if (s.k === 'running') effects.push({ t: 'stop_run' })
    effects.push({ t: 'say', line: 'stopped' })
    const resumeTo = s.k === 'idle' ? 'idle' : 'listening'
    return { state: { k: 'killed', resumeTo }, effects }
  }
  if (s.k === 'killed') {
    if (e.t === 'resume') return { state: { k: s.resumeTo }, effects: [] }
    if (e.t === 'tool_call') return { state: s, effects: [{ t: 'answer', answer: { ok: false, reason: 'killed' } }] }
    return { state: s, effects: [] } // wake, listen_on and the rest wait for resume
  }
  switch (e.t) {
    case 'resume':
      return { state: s, effects: [] }
    case 'listen_on':
      return s.k === 'idle' ? { state: { k: 'listening' }, effects: [] } : { state: s, effects: [] }
    case 'listen_off':
      if (s.k === 'listening') return { state: { k: 'idle' }, effects: [] }
      return { state: s, effects: [] }
    case 'wake':
      // A wake while listening opens a session; during a session or a run it is ignored (the helper is dormant then anyway).
      return s.k === 'listening' ? { state: { k: 'session' }, effects: [] } : { state: s, effects: [] }
    case 'session_ended': {
      if (s.k === 'card_shown') return { state: { k: 'cancelled' }, effects: [{ t: 'close_card' }, { t: 'answer', answer: { ok: false, reason: 'session_ended' } }] }
      if (s.k === 'running') return { state: { k: 'running', sessionOpen: false }, effects: [] } // the run is not tied to the conversation; kill and the supervisor stop it
      if (inSession(s)) return { state: { k: 'listening' }, effects: [] }
      return { state: s, effects: [] }
    }
    case 'tool_call': {
      if (!inSession(s)) return { state: s, effects: [{ t: 'answer', answer: { ok: false, reason: 'no_session' } }] }
      if (s.k === 'card_shown' || s.k === 'running') return { state: s, effects: [{ t: 'answer', answer: { ok: false, reason: 'busy' } }] }
      if (!e.rungCleared) {
        return { state: { k: 'rung_missing' }, effects: [{ t: 'answer', answer: { ok: false, reason: 'first_supervised_test_pending' } }, { t: 'say', line: 'show_instead' }] }
      }
      if (!e.targetFound) return { state: { k: 'session' }, effects: [{ t: 'answer', answer: { ok: false, reason: 'target_not_found' } }] }
      return { state: { k: 'card_shown', cardId: nextCardId }, effects: [{ t: 'show_card', cardId: nextCardId }] }
    }
    case 'card_choice': {
      if (s.k !== 'card_shown') return { state: s, effects: [{ t: 'ignored', why: 'stale' }] }
      if (e.choice === 'allow') {
        if (e.via !== 'mouse') return { state: s, effects: [{ t: 'ignored', why: 'allow_not_by_mouse' }] } // no voice, no key, no timer
        return { state: { k: 'running', sessionOpen: true }, effects: [{ t: 'close_card' }, { t: 'answer', answer: { ok: true, started: true } }, { t: 'request_run' }] }
      }
      return { state: { k: 'cancelled' }, effects: [{ t: 'close_card' }, { t: 'answer', answer: { ok: false, reason: 'worker_cancelled' } }] }
    }
    case 'run_result':
      if (s.k !== 'running') return { state: s, effects: [{ t: 'ignored', why: 'stale' }] }
      return { state: s.sessionOpen ? { k: 'session' } : { k: 'listening' }, effects: [{ t: 'say', line: e.ok ? 'done' : 'did_not_work' }] }
  }
}
