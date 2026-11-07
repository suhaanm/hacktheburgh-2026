import { describe, expect, it } from 'vitest'
import { CALM_SIGNALS, createFlowTracker, toQuery, toStateBody } from './signals'
import { parseNext, toSubject } from './types'

describe('signals', () => {
  it('the query carries flags and numbers only', () => {
    const q = new URLSearchParams(toQuery({ ...CALM_SIGNALS, typingBurst: true, quietS: 0.44, dnd: true, taskMarkerS: 12 }, Date.UTC(2026, 10, 9, 10, 0, 0)))
    expect(q.get('typing_burst')).toBe('1')
    expect(q.get('quiet_s')).toBe('0.4')
    expect(q.get('dnd')).toBe('1')
    expect(q.get('task_marker_s')).toBe('12')
    expect(q.get('t')).toBe(String(Math.floor(Date.UTC(2026, 10, 9, 10, 0, 0) / 1000)))
    for (const [, v] of q) expect(v).toMatch(/^[0-9.]+$/)
  })

  it('the state body has the engine schema keys only', () => {
    const body = toStateBody(CALM_SIGNALS, 0)
    const allowed = new Set(['typing_burst', 'quiet_s', 'deep_work', 'task_in_progress', 'task_marker_s', 'away', 'away_s', 'locked', 'dnd', 'screen_sharing', 'on_call', 'in_meeting', 'voice_session', 'dashboard_focused', 'local_hour', 't'])
    for (const k of Object.keys(body)) expect(allowed.has(k)).toBe(true)
  })

  it('flow tracker: a burst needs several inputs close together and ends after two seconds of quiet', () => {
    let t = 0
    const f = createFlowTracker({ now: () => t })
    expect(f.snapshot().typingBurst).toBe(false)
    for (const at of [0, 400, 800, 1200]) {
      t = at
      f.onInput(at)
    }
    expect(f.snapshot().typingBurst).toBe(true)
    t = 3_500
    expect(f.snapshot().typingBurst).toBe(false)
    expect(f.snapshot().quietS).toBeCloseTo(2.3, 1)
  })

  it('flow tracker: deep work needs 25 minutes with no gap of two minutes, and a gap ends it', () => {
    let t = 0
    const f = createFlowTracker({ now: () => t })
    for (let s = 0; s <= 26 * 60; s += 30) {
      t = s * 1000
      f.onInput(t)
    }
    expect(f.snapshot().deepWork).toBe(true)
    t += 3 * 60_000
    expect(f.snapshot().deepWork).toBe(false)
  })
})

describe('parsing', () => {
  const item = { id: 'i_abc', type: 'approval_blocking', channel: 'toast', text_id: 'approval_blocking', title: 'An approval is waiting', body: 'Approval queue: 1 approval waiting.', source: 'Approval queue', count: 1, actions: [{ id: 'open_queue', label: 'Open the queue' }], priority: 2, new: true, preempt: false, reminder: false, display_s: 20, expires_in_s: 100, reason_code: 'shown_break' }

  it('a good answer parses and malformed ones mean nothing to show', () => {
    const ok = parseNext({ meta: {}, data: { item, active: null, badges: { needs_you: 2, waiting: 1, marker: 'needs_you', stopped: false }, digest_ready: true, poll_after_s: 2 } })
    expect(ok.item?.id).toBe('i_abc')
    expect(ok.badges.needs_you).toBe(2)
    expect(ok.digestReady).toBe(true)
    for (const bad of [null, 'x', 42, {}, { data: null }, { data: { item: { id: 'no spaces allowed', type: 'x' } } }]) {
      const r = parseNext(bad)
      expect(r.item).toBeNull()
    }
  })

  it('unknown fields are dropped, strings capped, enums validated', () => {
    const r = parseNext({ data: { item: { ...item, evil: 'x', title: 'x'.repeat(500) }, badges: { needs_you: 1, waiting: 0, marker: 'wat', stopped: false } } })
    expect(r.item).toBeNull() // a title past the cap is not an item we trust
    const r2 = parseNext({ data: { item: { ...item, channel: 'sms' }, badges: {} } })
    expect(r2.item).toBeNull()
    const r3 = parseNext({ data: { item, badges: { needs_you: 1, waiting: 0, marker: 'wat', stopped: false } } })
    expect(r3.badges.marker).toBe('none')
    expect(Object.keys(r3.item ?? {})).not.toContain('evil')
  })

  it('subjects are made safe for the engine', () => {
    expect(toSubject('Run 7 / A?')).toBe('run_7___a_')
    expect(toSubject('-x')).toBe('x-x')
    expect(toSubject('a'.repeat(100))).toHaveLength(64)
    expect(toSubject('E_ABC123')).toBe('e_abc123')
  })
})
