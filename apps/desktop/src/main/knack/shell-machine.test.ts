import { describe, expect, it } from 'vitest'
import transitions from '../../../../../docs/knack-ux/shell-transitions.json'
import { CARD_PRIORITY, INITIAL_SHELL, TIMING, WINDOW_RESTORING, outranks, reduce, tokenOf, type CardKind, type Effect, type ShellEvent, type ShellState } from './shell-machine'

const st = (over: Partial<ShellState> & { card?: CardKind; pill?: ShellState['corner']['pill'] } = {}): ShellState => {
  const { card, pill, ...rest } = over
  return { ...INITIAL_SHELL, ...rest, corner: { pill: pill ?? rest.corner?.pill ?? 'none', card: card ?? rest.corner?.card ?? 'none' } }
}
const tokens = (effects: Effect[]): string[] => effects.map(tokenOf)
const row = (id: number) => transitions.transitions.find((t) => t.id === id)!

// One scenario per row of docs/knack-ux/08-window-states.md. Each returns the effects of the row's event, run from the state the row's "when" describes.
const scenarios: Record<number, () => { effects: Effect[]; state: ShellState }[]> = {
  1: () => [reduce(st({ window: 'open', focused: true, moveAside: true }), { type: 'run_started', realScreen: true })],
  2: () => [
    reduce(st({ window: 'absent', focused: false }), { type: 'run_started', realScreen: true }),
    reduce(st({ window: 'minimised', focused: false }), { type: 'run_started', realScreen: true }),
    reduce(st({ window: 'open', focused: false }), { type: 'run_started', realScreen: true }),
    reduce(st({ window: 'open', focused: true, moveAside: false }), { type: 'run_started', realScreen: true }), // the setting is off: the pill still shows
  ],
  3: () => [reduce(st({ window: 'open', focused: true, moveAside: true }), { type: 'run_started', realScreen: false })],
  4: () => [reduce(st({ activity: 'working', pill: 'working' }), { type: 'run_progress', label: 'Filling in calculator B right now please', n: 3, m: 8 })],
  5: () => (['approval', 'safety', 'time'] as const).map((c) => reduce(st({ activity: 'working', pill: 'working', window: 'minimised', focused: false }), { type: 'decision_needed', class: c })),
  6: () => [reduce(st({ window: 'minimised', focused: false, card: 'approval', needsYou: 1 }), { type: 'review_clicked', item: 'q_12' })],
  7: () => [reduce(st({ activity: 'working', pill: 'working' }), { type: 'run_done', needsNothing: true })],
  8: () => [reduce(st({ activity: 'working', pill: 'working', needsYou: 1 }), { type: 'run_failed' })],
  9: () => [reduce(st({ activity: 'working', pill: 'working' }), { type: 'kill' }), reduce(st(), { type: 'kill' }), reduce(st({ card: 'approval' }), { type: 'kill' })],
  10: () => [reduce(st({ activity: 'stopped', card: 'stopped' }), { type: 'resume' })],
  11: () => (['Listening', 'Thinking', 'Speaking'] as const).map((phase) => reduce(st(), { type: 'voice_hold', phase })),
  12: () => [reduce(st(), { type: 'ask_tap' })],
  13: () => [reduce(st({ window: 'absent', focused: false }), { type: 'returned_after_30min', count: 3 })],
  14: () => [reduce(st({ activity: 'working', pill: 'working' }), { type: 'window_close' })],
  15: () => [reduce(st({ activity: 'working', pill: 'working' }), { type: 'window_minimise' })],
  16: () => [reduce(st({ window: 'absent', focused: false }), { type: 'dock_click_or_activate' }), reduce(st({ window: 'minimised', focused: false }), { type: 'dock_click_or_activate' }), reduce(st({ window: 'open', focused: false }), { type: 'dock_click_or_activate' })],
  17: () => [reduce(st({ activity: 'working' }), { type: 'quit', running: true }), reduce(st(), { type: 'quit', running: false })],
  18: () => [reduce(st({ activity: 'working' }), { type: 'quit', running: true, awayRoutineDueWithin24h: true })],
}

describe('the 18 transitions of docs/knack-ux/08-window-states.md', () => {
  it('every row of the table has a scenario, and nothing else does', () => {
    expect(Object.keys(scenarios).map(Number)).toEqual(transitions.transitions.map((t) => t.id))
  })

  // Rows whose effects are written as plain tokens in the spec data: each scenario must produce every one of them.
  for (const id of [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14, 15]) {
    const spec = row(id)
    it(`row ${id} (${spec.event}): ${spec.effects.join(', ')}`, () => {
      const runs = scenarios[id]!()
      expect(runs.length).toBeGreaterThan(0)
      for (const r of runs) {
        const got = tokens(r.effects)
        const expected = id === 2 ? spec.effects : id === 4 ? spec.effects : id === 12 ? ['openAskBar', 'holdCards(except stopped, safety)'] : spec.effects
        for (const e of expected) expect(got, `${id}: ${e}`).toContain(e)
        for (const never of (spec as { never?: string[] }).never ?? []) expect(got).not.toContain(never)
      }
    })
  }

  it('row 1 minimises the window after 400 ms, only when a real-screen run starts with the window focused and the setting on', () => {
    const [r] = scenarios[1]!()
    expect(r!.effects.find((e) => e.type === 'minimizeMainAfter')).toEqual({ type: 'minimizeMainAfter', ms: 400 })
    expect(r!.state).toMatchObject({ activity: 'working', corner: { pill: 'working' } })
    expect(tokens(r!.effects)).toEqual(['minimizeMainAfter400ms', 'showPill(Starting)', 'menubar(working)'])
  })
  it('rows 2 and 3 never move the window', () => {
    for (const r of [...scenarios[2]!(), ...scenarios[3]!()]) {
      expect(tokens(r.effects)).toEqual(['showPill(Starting)', 'menubar(working)'])
      expect(r.state.window === 'open' || r.state.window === 'minimised' || r.state.window === 'absent').toBe(true)
    }
    // A sandbox job (row 3) with the window focused and the setting on: still no move.
    expect(tokens(scenarios[3]!()[0]!.effects)).not.toContain('minimizeMainAfter400ms')
  })
  it('row 4: the label is cut to five words, and the count shows only when n and m are known', () => {
    const r = scenarios[4]!()[0]!
    expect(r.effects).toContainEqual({ type: 'pillLabel', label: 'Filling in calculator B right' })
    expect(r.effects).toContainEqual({ type: 'pillCount', n: 3, m: 8 })
    const unknown = reduce(st({ activity: 'working', pill: 'working' }), { type: 'run_progress', label: 'Reading' })
    expect(tokens(unknown.effects)).toEqual(['pillLabel(<=5 words)'])
    expect(reduce(st(), { type: 'run_progress', label: 'x' }).effects).toEqual([]) // not working: nothing to label
  })
  it('row 5: a decision draws one card by priority, counts, and never restores the window', () => {
    for (const r of scenarios[5]!()) {
      expect(r.effects.some((e) => WINDOW_RESTORING.has(e.type))).toBe(false)
      expect(r.state.corner.card).not.toBe('none')
      expect(r.effects).toContainEqual({ type: 'dockBadge', count: 1 })
      expect(r.state.window).toBe('minimised')
    }
  })
  it('row 6: Review opens or restores the main window on Needs you at that item and closes the card', () => {
    const r = scenarios[6]!()[0]!
    expect(r.effects).toContainEqual({ type: 'openOrRestoreMain', screen: 'needs-you', item: 'q_12' })
    expect(r.state).toMatchObject({ window: 'open', focused: true, corner: { card: 'none' }, needsYou: 1 }) // the badge does not change
  })
  it('row 7: done is a check for 2.5 s, fades in 240 ms, and the window does not pop back', () => {
    const r = scenarios[7]!()[0]!
    expect(r.effects).toContainEqual({ type: 'pillCheck', ms: 2500 })
    expect(r.effects).toContainEqual({ type: 'fade', ms: 240 })
    expect(TIMING.doneMs).toBe(transitions.corner.doneMs)
    expect(TIMING.fadeMs).toBe(transitions.corner.fadeMs)
    expect(r.effects.some((e) => WINDOW_RESTORING.has(e.type))).toBe(false)
    expect(r.state).toMatchObject({ activity: 'idle', corner: { pill: 'done' } })
    expect(reduce(r.state, { type: 'done_timer' }).state.corner.pill).toBe('none')
  })
  it('row 7 with something left to decide: no check, the pill just goes', () => {
    const r = reduce(st({ activity: 'working', pill: 'working' }), { type: 'run_done', needsNothing: false })
    expect(tokens(r.effects)).toEqual(['noWindowRestore', 'menubar(workingOff)'])
  })
  it('row 8: an error holds until acknowledged, then leaves a marker; the window does not pop back', () => {
    const r = scenarios[8]!()[0]!
    expect(r.state).toMatchObject({ activity: 'error', corner: { pill: 'error' } })
    expect(r.effects.some((e) => WINDOW_RESTORING.has(e.type))).toBe(false)
    expect(reduce(r.state, { type: 'done_timer' }).state.corner.pill).toBe('error') // no timer ends an error
    const ack = reduce(r.state, { type: 'error_acknowledged' })
    expect(ack.state).toMatchObject({ activity: 'idle', corner: { pill: 'none' }, errorMarker: true })
  })
  it('row 9: kill stops everything, the Stopped card replaces the pill and any card, the banner shows if the window is open, and nothing restores', () => {
    for (const r of scenarios[9]!()) {
      expect(r.state).toMatchObject({ activity: 'stopped', corner: { pill: 'none', card: 'stopped' } })
      expect(r.effects.some((e) => WINDOW_RESTORING.has(e.type))).toBe(false)
    }
  })
  it('row 10: resume closes the Stopped card and the banner and goes idle', () => {
    const r = scenarios[10]!()[0]!
    expect(r.state).toMatchObject({ activity: 'idle', corner: { pill: 'none', card: 'none' } })
    expect(tokens(r.effects)).toEqual(expect.arrayContaining(['closeStoppedCard', 'bannerOff', 'menubar(idle)']))
  })
  it('row 11: voice uses the same pill with End instead of Stop', () => {
    for (const r of scenarios[11]!()) {
      expect(r.state.corner.pill).toBe('voice')
      expect(tokens(r.effects)[0]).toMatch(/^pill\((Listening|Thinking|Speaking), End\)$/)
    }
  })
  it('row 12: a tap opens the Ask bar, which holds every card except stopped and safety until it closes', () => {
    const open = reduce(st({ activity: 'working', pill: 'working' }), { type: 'ask_tap' })
    expect(open.state.askBarOpen).toBe(true)
    const approval = reduce(open.state, { type: 'decision_needed', class: 'approval' })
    expect(approval.effects.some((e) => e.type === 'cardAbovePill')).toBe(false) // held
    expect(approval.state.held).toContain('approval')
    const safety = reduce(approval.state, { type: 'decision_needed', class: 'safety' })
    expect(safety.effects).toContainEqual(expect.objectContaining({ type: 'cardAbovePill', kind: 'safety' }))
    // The safety card on screen outranks the held approval, which waits behind it; it is drawn once the better card is gone.
    const closed = reduce(safety.state, { type: 'ask_closed' })
    expect(closed.effects.some((e) => e.type === 'cardAbovePill')).toBe(false)
    expect(closed.state.corner.card).toBe('safety')
    expect(reduce(closed.state, { type: 'card_dismissed' }).effects).toContainEqual(expect.objectContaining({ type: 'cardAbovePill', kind: 'approval' }))
    // With no better card up, closing the Ask bar draws the held approval.
    const plain = reduce(reduce(approval.state, { type: 'ask_closed' }).state, { type: 'card_dismissed' })
    expect(reduce(approval.state, { type: 'ask_closed' }).effects).toContainEqual(expect.objectContaining({ type: 'cardAbovePill', kind: 'approval' }))
    void plain
  })
  it('row 13: the worker returns after 30 minutes: the digest is one card, once, with a count', () => {
    const r = scenarios[13]!()[0]!
    expect(r.state.corner.card).toBe('digest')
    expect(r.effects).toContainEqual({ type: 'menubar', state: 'count', count: 3 })
    expect(r.effects).toContainEqual({ type: 'dockBadge', count: 3 })
    expect(TIMING.awayMinutes).toBe(30)
  })
  it('rows 14 and 15: close hides the window and never quits, stops or hides the Dock icon; minimise goes to the Dock and never stops a run', () => {
    const close = scenarios[14]!()[0]!
    expect(close.state).toMatchObject({ window: 'absent', activity: 'working', corner: { pill: 'working' } }) // the run goes on
    expect(close.effects.map((e) => e.type)).toEqual(['hideMain'])
    const mini = scenarios[15]!()[0]!
    expect(mini.state).toMatchObject({ window: 'minimised', activity: 'working' })
    expect(mini.effects.some((e) => e.type === 'stopAll' || e.type === 'quit')).toBe(false)
  })
  it('row 16: the Dock click opens from closed at the last place, restores from minimised, and focuses from behind', () => {
    const [closed, minimised, behind] = scenarios[16]!()
    expect(closed!.effects).toEqual([{ type: 'openMain', screen: 'home', bounds: 'last' }])
    expect(minimised!.effects).toEqual([{ type: 'restoreMain' }])
    expect(behind!.effects).toEqual([{ type: 'focusMain' }])
    for (const r of [closed, minimised, behind]) expect(r!.state).toMatchObject({ window: 'open', focused: true })
    expect(reduce(st({ window: 'open', focused: true }), { type: 'dock_click_or_activate' }).effects).toEqual([]) // already there: no second window, nothing to do
  })
  it('rows 17 and 18: quit asks while something runs (with one more line when a routine is due), and quits at once otherwise', () => {
    const [running, idle] = scenarios[17]!()
    expect(running!.effects).toEqual([{ type: 'quitSheet', routineLine: false }])
    expect(idle!.effects).toEqual([{ type: 'quit' }])
    expect(scenarios[18]!()[0]!.effects).toEqual([{ type: 'quitSheet', routineLine: true }])
    expect(reduce(st({ activity: 'working' }), { type: 'quit_choice', choice: 'stop_and_quit' }).effects).toEqual([{ type: 'stopAndQuit' }])
    expect(reduce(st({ activity: 'working' }), { type: 'quit_choice', choice: 'keep_working' }).effects).toEqual([])
  })
})

describe('the invariants in docs/knack-ux/shell-transitions.json', () => {
  it('lists the eight the plan names', () => {
    expect(transitions.invariants).toHaveLength(8)
  })
  it('the priority order is stopped, safety, approval, time, digest, cue', () => {
    expect(CARD_PRIORITY).toEqual(['stopped', 'safety', 'approval', 'time', 'digest', 'cue'])
    expect(transitions.priority).toEqual(['stopped', 'safety', 'approval_blocking', 'time_sensitive', 'digest', 'cue_no_target'])
    expect(outranks('safety', 'approval')).toBe(true)
    expect(outranks('approval', 'safety')).toBe(false)
    expect(outranks('digest', 'digest')).toBe(false)
    expect(outranks('cue', 'none')).toBe(true)
  })
  it('a card is replaced only by a higher-priority card', () => {
    const withApproval = reduce(st({ activity: 'working', pill: 'working' }), { type: 'decision_needed', class: 'approval' }).state
    const lower = reduce(withApproval, { type: 'decision_needed', class: 'time' })
    expect(lower.state.corner.card).toBe('approval')
    expect(lower.effects.some((e) => e.type === 'cardAbovePill')).toBe(false)
    expect(lower.state.held).toContain('time')
    const higher = reduce(withApproval, { type: 'decision_needed', class: 'safety' })
    expect(higher.state.corner.card).toBe('safety')
    expect(higher.state.held).toContain('approval') // the replaced card waits; it is not lost
    const cue = reduce(withApproval, { type: 'card_arrived', kind: 'cue' })
    expect(cue.state.corner.card).toBe('approval')
  })
  it('a card carries its 600 ms mis-click guard and never takes focus', () => {
    const r = reduce(st(), { type: 'decision_needed', class: 'approval' })
    expect(r.effects).toContainEqual({ type: 'cardAbovePill', kind: 'approval', mistapGuardMs: 600, takesFocus: false })
    expect(transitions.corner.mistapGuardMs).toBe(TIMING.mistapGuardMs)
  })
  it('no card shows while macOS secure input is on, except stopped and safety; the held card appears when it ends', () => {
    const on = reduce(st(), { type: 'secure_input', on: true }).state
    const approval = reduce(on, { type: 'decision_needed', class: 'approval' })
    expect(approval.effects.some((e) => e.type === 'cardAbovePill')).toBe(false)
    expect(reduce(on, { type: 'decision_needed', class: 'safety' }).effects.some((e) => e.type === 'cardAbovePill')).toBe(true)
    expect(reduce(on, { type: 'kill' }).state.corner.card).toBe('stopped')
    const off = reduce(approval.state, { type: 'secure_input', on: false })
    expect(off.effects).toContainEqual(expect.objectContaining({ type: 'cardAbovePill', kind: 'approval' }))
  })
  it('the window is restored or opened only by a Dock click or Activate, Open Knack, Review or a deep link: checked over thousands of random sequences', () => {
    const ALLOWED = new Set<ShellEvent['type']>(['dock_click_or_activate', 'menu_open_knack', 'review_clicked', 'deep_link'])
    const events: ShellEvent[] = [
      { type: 'run_started', realScreen: true }, { type: 'run_started', realScreen: false }, { type: 'run_progress', label: 'Filling in calculator B', n: 1, m: 4 },
      { type: 'decision_needed', class: 'approval' }, { type: 'decision_needed', class: 'safety' }, { type: 'decision_needed', class: 'time' },
      { type: 'card_arrived', kind: 'cue' }, { type: 'card_arrived', kind: 'digest' }, { type: 'card_dismissed' },
      { type: 'run_done', needsNothing: true }, { type: 'run_done', needsNothing: false }, { type: 'run_failed' }, { type: 'error_acknowledged' }, { type: 'done_timer' },
      { type: 'kill' }, { type: 'resume' }, { type: 'voice_hold', phase: 'Listening' }, { type: 'voice_end' }, { type: 'ask_tap' }, { type: 'ask_closed' },
      { type: 'returned_after_30min', count: 2 }, { type: 'window_close' }, { type: 'window_minimise' }, { type: 'dock_click_or_activate' }, { type: 'menu_open_knack' },
      { type: 'review_clicked' }, { type: 'secure_input', on: true }, { type: 'secure_input', on: false }, { type: 'quit', running: true }, { type: 'quit', running: false },
      { type: 'window_state', window: 'minimised', focused: false }, { type: 'settings', moveAside: false },
    ]
    let seed = 12345
    const rand = (n: number): number => {
      seed = (seed * 1664525 + 1013904223) >>> 0
      return seed % n
    }
    for (let run = 0; run < 400; run++) {
      let s = INITIAL_SHELL
      let killed = false
      for (let i = 0; i < 40; i++) {
        const ev = events[rand(events.length)]!
        const before = s
        const r = reduce(s, ev)
        s = r.state
        // restore only by the allowed events
        if (r.effects.some((e) => WINDOW_RESTORING.has(e.type))) expect(ALLOWED.has(ev.type), `${ev.type} restored the window`).toBe(true)
        // close and minimise never quit, stop or hide the Dock icon
        if (ev.type === 'window_close' || ev.type === 'window_minimise') expect(r.effects.some((e) => e.type === 'quit' || e.type === 'stopAll' || e.type === 'stopAndQuit')).toBe(false)
        // a card drawn outranks the one on screen, carries the guard, and respects secure input and the Ask bar
        for (const e of r.effects) {
          if (e.type !== 'cardAbovePill') continue
          expect(e.mistapGuardMs).toBe(600)
          expect(e.takesFocus).toBe(false)
          expect(s.corner.card).toBe(e.kind)
          if (e.kind !== 'stopped' && e.kind !== 'safety') {
            expect(s.secureInput, `${ev.type}: card over secure input`).toBe(false)
            expect(s.askBarOpen, `${ev.type}: card over the Ask bar`).toBe(false)
          }
        }
        // one card, and it is not also held
        expect(s.held).not.toContain(s.corner.card)
        expect(new Set(s.held).size).toBe(s.held.length)
        // a card on screen changes only to a higher-priority one, or to none
        // (closing a card, by Review, Later or Resume, lets the next held one in: that is a close, not a replacement)
        const closes = ev.type === 'card_dismissed' || ev.type === 'review_clicked' || ev.type === 'resume'
        if (!closes && before.corner.card !== 'none' && s.corner.card !== before.corner.card && s.corner.card !== 'none') expect(outranks(s.corner.card, before.corner.card)).toBe(true)
        // kill wins: after a kill, the state is stopped with the Stopped card until Resume
        if (ev.type === 'kill') killed = true
        if (ev.type === 'resume') killed = false
        if (killed) {
          expect(s.activity, `after kill, ${ev.type}`).toBe('stopped')
          expect(s.corner.card === 'stopped').toBe(true)
          expect(s.corner.pill).toBe('none')
        }
      }
    }
  })
})
