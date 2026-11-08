import { describe, expect, it } from 'vitest'
import { PILLS_INSET, PILLS_PAD, PILLS_WIDTH, pillIdOf, pillsBounds, pillsWindowHeight } from './agent-pills-ipc'
import { PILL_LIMITS, createAgentRunsSource, createPillsModel, openPathsOfTasks, pillRunsOf, pillRunsOfTasks, plainLine, titleOf, type AgentPillRun, type PillsView } from './agent-pills-model'
import { RUN_MAX_AGE_MS } from './pill-state'

function rig() {
  let now = 1_000_000
  const timers: { fn: () => void; at: number; id: number }[] = []
  let nextId = 1
  const views: PillsView[] = []
  const m = createPillsModel({
    now: () => now,
    setTimer: (fn, ms) => {
      const id = nextId++
      timers.push({ fn, at: now + ms, id })
      return id
    },
    clearTimer: (h) => {
      const i = timers.findIndex((t) => t.id === h)
      if (i >= 0) timers.splice(i, 1)
    },
    onChange: (v) => views.push(v),
  })
  /** Moves the clock and runs what is due, in order. */
  const advance = (ms: number): void => {
    const to = now + ms
    for (;;) {
      const due = timers.filter((t) => t.at <= to).sort((a, b) => a.at - b.at)[0]
      if (!due) break
      timers.splice(timers.indexOf(due), 1)
      now = Math.max(now, due.at)
      due.fn()
    }
    now = to
  }
  return { m, views, advance, texts: () => m.view().items.map((i) => `${i.phase}:${i.text}`) }
}
const work = (id: string, over: Partial<AgentPillRun> = {}): AgentPillRun => ({ id, title: `Task ${id}`, route: 'answer', state: 'working', stoppable: true, ...over })

describe('the words on a pill', () => {
  it('turn a run kind into at most four readable words, letters and digits only', () => {
    expect(titleOf('data.profile')).toBe('Data profile')
    expect(titleOf('benefits.check_eligibility-now.please.thanks')).toBe('Benefits check eligibility now')
    expect(titleOf('')).toBe('Task')
    expect(titleOf('<script>alert(1)</script>')).toBe('Script alert 1 script')
  })
  it('keep a line to one plain line, cut at the limit', () => {
    expect(plainLine('  a\n b   c ')).toBe('a b c')
    expect(plainLine('x'.repeat(200))).toHaveLength(PILL_LIMITS.maxChars)
    expect(plainLine(7)).toBe('')
  })
})

describe('the service run list as pills', () => {
  const now = 10 * RUN_MAX_AGE_MS
  it('maps the states, and a run that "is running" on a record too old to be real is a ghost: stopped, never shown', () => {
    const rows = pillRunsOf(
      [
        { id: 'r_a', state: 'running', startedAt: now - 1000, kind: 'data.profile' },
        { id: 'r_b', state: 'planning', startedAt: now - 3 * RUN_MAX_AGE_MS, kind: 'data.profile' },
        { id: 'r_c', state: 'done', kind: 'x' },
        { id: 'r_d', state: 'timeout', kind: 'x' },
        { id: 'r_e', state: 'killed', kind: 'x' },
      ],
      now,
    )
    expect(rows.map((r) => r.state)).toEqual(['working', 'stopped', 'done', 'failed', 'stopped'])
    expect(rows[0]).toMatchObject({ title: 'Data profile', route: 'run' })
  })
})

describe('the task events as pills (task API contract v1)', () => {
  const row = (over: Record<string, unknown>) => ({ task_id: 'tk_8f3a1c2e', title: 'Fill in the form', route: 'browser', state: 'running', latest: null, result: null, reason: null, started: '2026-11-08T00:10:00Z', ...over })
  it('one pill per task that is planning, running or waiting for consent; the label is the step line, else the title, cut to four words', () => {
    const out = pillRunsOfTasks([row({ latest: 'Opening the page' }), row({ task_id: 'tk_aaaa1111', state: 'planning' }), row({ task_id: 'tk_bbbb2222', state: 'waiting_consent' }), row({ task_id: 'tk_cccc3333', title: 'Fill in the quarterly benefits form for Marcus' })])
    expect(out.map((r) => [r.state, r.title])).toEqual([['working', 'Opening the page'], ['working', 'Fill in the form'], ['waiting', 'Fill in the form'], ['working', 'Fill in the quarterly…']])
    expect(out[0]).toMatchObject({ route: 'browser', stoppable: true, animated: true, startedAt: Date.parse('2026-11-08T00:10:00Z') })
  })
  it('animates only a running task: planning and waiting for consent hold still', () => {
    const out = pillRunsOfTasks([row({ state: 'running' }), row({ task_id: 'tk_aaaa1111', state: 'planning' }), row({ task_id: 'tk_bbbb2222', state: 'waiting_consent' })])
    expect(out.map((r) => r.animated)).toEqual([true, false, false])
  })
  it('lists only the paths the service recorded (a folder or a file, absolute) for the worker to reveal in Finder', () => {
    const paths = openPathsOfTasks([
      row({ state: 'done', open: { kind: 'folder', path: '/Users/w/Documents/Results' } }),
      row({ task_id: 'tk_aaaa1111', state: 'done', open: { kind: 'file', path: '/Users/w/Documents/a.csv' } }),
      row({ task_id: 'tk_bbbb2222', state: 'done', open: { kind: 'script', path: '/bin/sh' } }),
      row({ task_id: 'tk_cccc3333', state: 'done', open: { kind: 'file', path: 'relative/a.csv' } }),
      row({ task_id: 'tk_dddd4444', state: 'done', open: { kind: 'file', path: '/x\0y' } }),
      row({ task_id: 'tk_eeee5555', state: 'done', open: null }),
      null,
    ])
    expect(paths).toEqual(['/Users/w/Documents/Results', '/Users/w/Documents/a.csv'])
  })
  it('carries the end line of a finished task (the result, or the reason) and nothing else', () => {
    const out = pillRunsOfTasks([row({ state: 'done', result: 'Saved the file in Documents' }), row({ task_id: 'tk_aaaa1111', state: 'failed', reason: 'The page did not load' }), row({ task_id: 'tk_bbbb2222', state: 'stopped' })])
    expect(out.map((r) => [r.state, r.endText])).toEqual([['done', 'Saved the file in Documents'], ['failed', 'The page did not load'], ['stopped', undefined]])
  })
  it('skips anything that is not a well-formed row, and gives an unknown route the plain icon', () => {
    const out = pillRunsOfTasks([null, 'x', { state: 'running' }, row({ task_id: '../../etc' }), row({ task_id: 'tk_ok12345', route: 'who knows' }), row({ task_id: 'tk_zz123456', state: 'surprise' })])
    expect(out).toHaveLength(1)
    expect(out[0]).toMatchObject({ id: 'tk_ok12345', route: 'answer' })
  })
  it('never draws more than one plain line of the worker words', () => {
    const [r] = pillRunsOfTasks([row({ title: 'a'.repeat(300) })])
    expect(r!.title.length).toBeLessThanOrEqual(PILL_LIMITS.maxChars)
  })
})

describe('when a pill comes and goes', () => {
  it('appears while the work goes on, shows how it ended, fades after five seconds and leaves nothing behind', () => {
    const r = rig()
    r.m.update([work('tk_1')])
    expect(r.texts()).toEqual(['working:Task tk_1'])
    r.m.update([work('tk_1', { state: 'done', endText: 'Saved the file' })])
    expect(r.texts()).toEqual(['done:Saved the file'])
    expect(r.m.view().items[0]!.stoppable).toBe(false)
    r.advance(PILL_LIMITS.doneMs - 1)
    expect(r.m.view().items[0]!.leaving).toBe(false)
    r.advance(1)
    expect(r.m.view().items[0]!.leaving).toBe(true)
    r.advance(PILL_LIMITS.fadeMs)
    expect(r.m.view().items).toEqual([])
  })
  it('a stop shows a dash for three seconds; a failure (a red dot) stays until the worker has clicked it, then fades', () => {
    const r = rig()
    r.m.update([work('tk_1'), work('tk_2')])
    r.m.update([work('tk_1', { state: 'failed', endText: 'The page did not load' }), work('tk_2', { state: 'stopped' })])
    expect(r.texts()).toEqual(['failed:The page did not load', 'stopped:Stopped'])
    r.advance(PILL_LIMITS.stoppedMs + PILL_LIMITS.fadeMs)
    expect(r.texts()).toEqual(['failed:The page did not load'])
    r.advance(60 * 60_000) // an hour later it is still there
    expect(r.texts()).toEqual(['failed:The page did not load'])
    r.m.dismiss('tk_nope') // an unknown pill changes nothing
    r.m.dismiss('tk_1')
    expect(r.m.view().items[0]!.leaving).toBe(true)
    r.advance(PILL_LIMITS.fadeMs)
    expect(r.m.view().items).toEqual([])
  })
  it('a click can only dismiss a failure, never a pill that is still working', () => {
    const r = rig()
    r.m.update([work('tk_1')])
    r.m.dismiss('tk_1')
    expect(r.texts()).toEqual(['working:Task tk_1'])
  })
  it('only a running task moves its icon: planning and waiting hold still, and an ended pill never moves', () => {
    const r = rig()
    r.m.update([work('tk_1', { animated: true }), work('tk_2', { animated: false }), work('tk_3', { state: 'waiting', animated: true })])
    expect(r.m.view().items.map((i) => i.animated)).toEqual([true, false, false])
    r.m.update([work('tk_1', { state: 'done' }), work('tk_2'), work('tk_3', { state: 'waiting' })])
    expect(r.m.view().items[0]!.animated).toBe(false)
  })
  it('says a plain word when the service sent no end line', () => {
    const r = rig()
    r.m.update([work('tk_1'), work('tk_2')])
    r.m.update([work('tk_1', { state: 'done' }), work('tk_2', { state: 'failed' })])
    expect(r.texts()).toEqual(['done:Done', 'failed:Did not finish'])
  })
  it('work that was going on and is no longer listed has ended: a done pill, not a stuck one', () => {
    const r = rig()
    r.m.update([work('tk_1')])
    r.m.update([])
    expect(r.texts()).toEqual(['done:Done'])
    r.advance(PILL_LIMITS.doneMs + PILL_LIMITS.fadeMs)
    expect(r.m.view().items).toEqual([])
  })
  it('only work seen going on earns a finished pill: a finished entry on its own (an old snapshot) shows nothing', () => {
    const r = rig()
    r.m.update([work('tk_old', { state: 'done', endText: 'Yesterday' }), work('tk_old2', { state: 'failed' })])
    expect(r.m.view().items).toEqual([])
    expect(r.views).toEqual([])
  })
  it('a task that waits for an OK is a still pill with its own phase, and goes back to working when it goes on', () => {
    const r = rig()
    r.m.update([work('tk_1', { state: 'waiting' })])
    expect(r.texts()).toEqual(['waiting:Task tk_1'])
    r.m.update([work('tk_1', { title: 'Next step' })])
    expect(r.texts()).toEqual(['working:Next step'])
  })
  it('shows at most four and counts the rest, oldest first so the column does not jump', () => {
    const r = rig()
    const runs = ['tk_1', 'tk_2', 'tk_3', 'tk_4', 'tk_5', 'tk_6'].map((id, i) => work(id, { startedAt: 1000 + i }))
    r.m.update(runs)
    expect(r.m.view().items.map((i) => i.id)).toEqual(['tk_1', 'tk_2', 'tk_3', 'tk_4'])
    expect(r.m.view().more).toBe(2)
    r.m.update(runs.slice(1)) // the first one ended
    expect(r.m.view().items.map((i) => i.id)).toContain('tk_1') // as a done pill
    expect(r.m.view().more).toBe(2)
  })
  it('a stopped run just goes, and a resumed one comes back as working', () => {
    const r = rig()
    r.m.update([work('r_1', { route: 'run' })])
    r.m.update([work('r_1', { route: 'run', state: 'done' })])
    r.m.update([work('r_1', { route: 'run' })])
    expect(r.texts()).toEqual(['working:Task r_1'])
    r.advance(PILL_LIMITS.doneMs + PILL_LIMITS.fadeMs) // the old fade must not take the working pill away
    expect(r.texts()).toEqual(['working:Task r_1'])
  })
  it('emits only when the view changed', () => {
    const r = rig()
    r.m.update([work('tk_1')])
    const n = r.views.length
    r.m.update([work('tk_1')])
    expect(r.views.length).toBe(n)
  })
})

describe('the one source of work', () => {
  it('hands the listener what was pushed last at once, then every change, and stops when unsubscribed', () => {
    const s = createAgentRunsSource()
    s.push([work('tk_1')])
    const seen: number[] = []
    const off = s.onAgentRuns((runs) => seen.push(runs.length))
    s.push([work('tk_1'), work('tk_2')])
    off()
    s.push([])
    expect(seen).toEqual([1, 2])
  })
})

describe('where the column goes', () => {
  const wa = { x: 0, y: 25, width: 1440, height: 875 }
  it('is 16 px in from the right and 16 px below the top of the work area, which starts below the menu bar', () => {
    const b = pillsBounds(wa, 100)
    expect(b.x + b.width - PILLS_PAD).toBe(wa.x + wa.width - PILLS_INSET)
    expect(b.y + PILLS_PAD).toBe(wa.y + PILLS_INSET)
    expect(b.y).toBeGreaterThanOrEqual(wa.y) // never over the menu bar
    expect(b.width).toBe(PILLS_WIDTH)
  })
  it('follows a second display at an offset', () => {
    const second = { x: 1440, y: 0, width: 1920, height: 1080 }
    expect(pillsBounds(second, 60).x + PILLS_WIDTH - PILLS_PAD).toBe(second.x + second.width - PILLS_INSET)
  })
  it('takes only the ids the service makes and the heights the page may ask for', () => {
    expect(pillIdOf('tk_8f3a1c2e')).toBe('tk_8f3a1c2e')
    expect(pillIdOf('r_ab12cd34')).toBe('r_ab12cd34')
    for (const bad of ['', 'tk_', '../x', 'task_1', 'tk_8f3a1c2e/../..', 7, null, undefined]) expect(pillIdOf(bad)).toBeNull()
    expect(pillsWindowHeight(120.2)).toBe(121)
    for (const bad of [0, -3, 9999, NaN, '10', null]) expect(pillsWindowHeight(bad)).toBeNull()
  })
})
