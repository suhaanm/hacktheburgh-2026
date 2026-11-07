import { describe, expect, it } from 'vitest'
import { INITIAL, reduce, type ClickEffect, type ClickEvent, type ClickState } from './click-machine'

function run(events: ClickEvent[], from: ClickState = INITIAL): { state: ClickState; effects: ClickEffect[] } {
  let state = from
  const effects: ClickEffect[] = []
  for (const e of events) {
    const r = reduce(state, e, 7)
    state = r.state
    effects.push(...r.effects)
  }
  return { state, effects }
}
const toSession: ClickEvent[] = [{ t: 'listen_on' }, { t: 'wake' }]
const call = (rungCleared: boolean, targetFound = true): ClickEvent => ({ t: 'tool_call', rungCleared, targetFound })

describe('wake, listening, session', () => {
  it('idle then listening then a session after a wake', () => {
    expect(run([{ t: 'listen_on' }]).state).toEqual({ k: 'listening' })
    expect(run(toSession).state).toEqual({ k: 'session' })
  })
  it('a wake while not listening does nothing, and ending the session returns to listening', () => {
    expect(run([{ t: 'wake' }]).state).toEqual({ k: 'idle' })
    expect(run([...toSession, { t: 'session_ended' }]).state).toEqual({ k: 'listening' })
    expect(run([{ t: 'listen_on' }, { t: 'listen_off' }]).state).toEqual({ k: 'idle' })
  })
  it('a tool call with no session is refused', () => {
    expect(run([call(true)]).effects).toEqual([{ t: 'answer', answer: { ok: false, reason: 'no_session' } }])
    expect(run([{ t: 'listen_on' }, call(true)]).effects).toEqual([{ t: 'answer', answer: { ok: false, reason: 'no_session' } }])
  })
})

describe('the rung record', () => {
  it('while it is missing the answer is first_supervised_test_pending, Knack says it will show instead, and no card appears', () => {
    const r = run([...toSession, call(false)])
    expect(r.state).toEqual({ k: 'rung_missing' })
    expect(r.effects).toEqual([{ t: 'answer', answer: { ok: false, reason: 'first_supervised_test_pending' } }, { t: 'say', line: 'show_instead' }])
    expect(r.effects.some((e) => e.t === 'show_card' || e.t === 'request_run')).toBe(false)
  })
  it('asking again gives the same answer, and the session can still end', () => {
    const r = run([...toSession, call(false), call(false), { t: 'session_ended' }])
    expect(r.effects.filter((e) => e.t === 'answer')).toHaveLength(2)
    expect(r.state).toEqual({ k: 'listening' })
  })
})

describe('the card', () => {
  it('shows only when the rung is cleared and the target was found', () => {
    expect(run([...toSession, call(true)]).state).toEqual({ k: 'card_shown', cardId: 7 })
    expect(run([...toSession, call(true)]).effects).toEqual([{ t: 'show_card', cardId: 7 }])
    const nf = run([...toSession, call(true, false)])
    expect(nf.state).toEqual({ k: 'session' })
    expect(nf.effects).toEqual([{ t: 'answer', answer: { ok: false, reason: 'target_not_found' } }])
  })
  it('a real mouse click on Allow starts the run, once', () => {
    const r = run([...toSession, call(true), { t: 'card_choice', choice: 'allow', via: 'mouse' }])
    expect(r.state).toEqual({ k: 'running', sessionOpen: true })
    expect(r.effects.slice(1)).toEqual([{ t: 'close_card' }, { t: 'answer', answer: { ok: true, started: true } }, { t: 'request_run' }])
    expect(reduce(r.state, { t: 'card_choice', choice: 'allow', via: 'mouse' }).effects).toEqual([{ t: 'ignored', why: 'stale' }])
  })
  it.each(['voice', 'key', 'timer'] as const)('Allow by %s is ignored: no voice, no key, no timer consents', (via) => {
    const r = run([...toSession, call(true), { t: 'card_choice', choice: 'allow', via }])
    expect(r.state).toEqual({ k: 'card_shown', cardId: 7 })
    expect(r.effects.at(-1)).toEqual({ t: 'ignored', why: 'allow_not_by_mouse' })
    expect(r.effects.some((e) => e.t === 'request_run')).toBe(false)
  })
  it('Cancel, by any means (including the timer), cancels and tells the model', () => {
    for (const via of ['mouse', 'key', 'voice', 'timer'] as const) {
      const r = run([...toSession, call(true), { t: 'card_choice', choice: 'cancel', via }])
      expect(r.state).toEqual({ k: 'cancelled' })
      expect(r.effects.slice(1)).toEqual([{ t: 'close_card' }, { t: 'answer', answer: { ok: false, reason: 'worker_cancelled' } }])
    }
  })
  it('after a cancel a new request can be made like in a session, and ending the conversation goes back to listening', () => {
    expect(run([...toSession, call(true), { t: 'card_choice', choice: 'cancel', via: 'mouse' }, call(false)]).state).toEqual({ k: 'rung_missing' })
    expect(run([...toSession, call(true), { t: 'card_choice', choice: 'cancel', via: 'mouse' }, { t: 'session_ended' }]).state).toEqual({ k: 'listening' })
  })
  it('a second request while a card is up or a run is going is busy', () => {
    expect(run([...toSession, call(true), call(true)]).effects.at(-1)).toEqual({ t: 'answer', answer: { ok: false, reason: 'busy' } })
    const r = run([...toSession, call(true), { t: 'card_choice', choice: 'allow', via: 'mouse' }, call(true)])
    expect(r.effects.at(-1)).toEqual({ t: 'answer', answer: { ok: false, reason: 'busy' } })
    expect(r.state).toEqual({ k: 'running', sessionOpen: true })
  })
  it('the conversation ending while the card is up cancels it', () => {
    const r = run([...toSession, call(true), { t: 'session_ended' }])
    expect(r.state).toEqual({ k: 'cancelled' })
    expect(r.effects.slice(1)).toEqual([{ t: 'close_card' }, { t: 'answer', answer: { ok: false, reason: 'session_ended' } }])
  })
  it('a card answer with no card is stale', () => {
    expect(run([...toSession, { t: 'card_choice', choice: 'allow', via: 'mouse' }]).effects).toEqual([{ t: 'ignored', why: 'stale' }])
  })
})

describe('the run', () => {
  it('finishes back in the session (or listening if the conversation ended meanwhile) with a fixed line', () => {
    const start = [...toSession, call(true), { t: 'card_choice', choice: 'allow', via: 'mouse' } as ClickEvent]
    expect(run([...start, { t: 'run_result', ok: true }]).state).toEqual({ k: 'session' })
    expect(run([...start, { t: 'run_result', ok: false }]).effects.at(-1)).toEqual({ t: 'say', line: 'did_not_work' })
    const ended = run([...start, { t: 'session_ended' }])
    expect(ended.state).toEqual({ k: 'running', sessionOpen: false })
    expect(run([{ t: 'run_result', ok: true }], ended.state).state).toEqual({ k: 'listening' })
  })
  it('a result with no run is stale', () => {
    expect(run([...toSession, { t: 'run_result', ok: true }]).effects).toEqual([{ t: 'ignored', why: 'stale' }])
  })
})

describe('kill', () => {
  it('wins from every state; only resume leaves it', () => {
    const states: ClickState[] = [{ k: 'idle' }, { k: 'listening' }, { k: 'session' }, { k: 'rung_missing' }, { k: 'cancelled' }, { k: 'card_shown', cardId: 3 }, { k: 'running', sessionOpen: true }]
    for (const s of states) {
      const r = reduce(s, { t: 'kill' })
      expect(r.state.k).toBe('killed')
      for (const e of [{ t: 'wake' }, { t: 'listen_on' }, { t: 'session_ended' }, { t: 'listen_off' }, { t: 'run_result', ok: true }, { t: 'card_choice', choice: 'allow', via: 'mouse' }] as ClickEvent[]) {
        expect(reduce(r.state, e).state.k).toBe('killed')
        expect(reduce(r.state, e).effects.some((x) => x.t === 'request_run' || x.t === 'show_card')).toBe(false)
      }
    }
  })
  it('stops a run, closes a card and answers a waiting call', () => {
    expect(reduce({ k: 'running', sessionOpen: true }, { t: 'kill' }).effects).toContainEqual({ t: 'stop_run' })
    const c = reduce({ k: 'card_shown', cardId: 3 }, { t: 'kill' })
    expect(c.effects).toContainEqual({ t: 'close_card' })
    expect(c.effects).toContainEqual({ t: 'answer', answer: { ok: false, reason: 'killed' } })
  })
  it('a tool call while killed is refused, and resume returns to listening (or idle if it was idle)', () => {
    const k = reduce({ k: 'session' }, { t: 'kill' }).state
    expect(reduce(k, call(true)).effects).toEqual([{ t: 'answer', answer: { ok: false, reason: 'killed' } }])
    expect(reduce(k, { t: 'resume' }).state).toEqual({ k: 'listening' })
    expect(reduce(reduce({ k: 'idle' }, { t: 'kill' }).state, { t: 'resume' }).state).toEqual({ k: 'idle' })
  })
  it('kill twice is quiet', () => {
    const k = reduce({ k: 'session' }, { t: 'kill' }).state
    expect(reduce(k, { t: 'kill' }).effects).toEqual([])
  })
})
