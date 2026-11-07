import { describe, expect, it } from 'vitest'
import type { PillKind } from './pill-state'
import { PILL_MARGIN, PILL_SIZE, interactiveParts, pillBounds, pillVisibility, workDisplay } from './pill-visibility'
import { INITIAL_MEMO, decideWindow, type ShellWindowState } from './shell-rules'

const up: ShellWindowState = { exists: true, visible: true, minimised: false, fullScreen: false }
const minimised: ShellWindowState = { ...up, minimised: true }
const hidden: ShellWindowState = { ...up, visible: false }
const on = { minimiseWhileWorking: true }
const off = { minimiseWhileWorking: false }
const pill = (from: PillKind, to: PillKind) => ({ type: 'pill' as const, from, to })

describe('minimising when a run starts', () => {
  it('minimises (not hides) the window when a new run starts and the setting is on', () => {
    for (const from of ['idle', 'done', 'error', 'killed'] as const) {
      expect(decideWindow(pill(from, 'working'), up, on, INITIAL_MEMO), from).toEqual({ action: 'minimise', memo: { minimisedByUs: true } })
    }
  })
  it('does nothing with the setting off', () => {
    expect(decideWindow(pill('idle', 'working'), up, off, INITIAL_MEMO).action).toBe('none')
  })
  it('does nothing when the window is already minimised, hidden to the menu bar, in full screen, or not there', () => {
    for (const w of [minimised, hidden, { ...up, fullScreen: true }, { ...up, exists: false }]) expect(decideWindow(pill('idle', 'working'), w, on, INITIAL_MEMO).action).toBe('none')
  })
  it('does not minimise again when the run carries on after the worker approved something', () => {
    expect(decideWindow(pill('needs-you', 'working'), up, on, INITIAL_MEMO).action).toBe('none')
  })
})

describe('coming back', () => {
  it('restores on needs-you from minimised and from the menu bar, and leaves a window that is already up alone', () => {
    expect(decideWindow(pill('working', 'needs-you'), minimised, on, { minimisedByUs: true })).toEqual({ action: 'restore', memo: { minimisedByUs: false } })
    expect(decideWindow(pill('working', 'needs-you'), hidden, off, INITIAL_MEMO).action).toBe('restore') // even with minimising switched off: the worker is needed
    expect(decideWindow(pill('working', 'needs-you'), up, on, INITIAL_MEMO).action).toBe('none')
  })
  it('restores when the worker clicks the pill or the Dock icon', () => {
    for (const type of ['pill-click', 'dock-click'] as const) expect(decideWindow({ type }, minimised, on, { minimisedByUs: true }), type).toEqual({ action: 'restore', memo: { minimisedByUs: false } })
    expect(decideWindow({ type: 'dock-click' }, hidden, on, INITIAL_MEMO).action).toBe('restore')
  })
  it('does not restore when a run ends with nothing to approve, fails, or is stopped', () => {
    for (const to of ['done', 'error', 'killed', 'idle'] as const) expect(decideWindow(pill('working', to), minimised, on, { minimisedByUs: true }).action, to).toBe('none')
  })
  it('forgets that a minimise was ours once the worker brings the window back', () => {
    expect(decideWindow({ type: 'window-shown' }, up, on, { minimisedByUs: true }).memo.minimisedByUs).toBe(false)
  })
  it('does nothing for a pill event that is not a change', () => {
    expect(decideWindow(pill('working', 'working'), up, on, INITIAL_MEMO).action).toBe('none')
  })
})

describe('whether the pill may be on screen', () => {
  const base = { kind: 'working' as PillKind, suppressed: null, presenting: false, knackInFront: false, disabled: false }
  it('shows while something is happening and nothing says to stay away', () => {
    expect(pillVisibility(base)).toEqual({ show: true, reason: null })
  })
  it('is off when idle or when the shell is disabled', () => {
    expect(pillVisibility({ ...base, kind: 'idle' }).reason).toBe('idle')
    expect(pillVisibility({ ...base, disabled: true }).reason).toBe('disabled')
  })
  it('never shows over a secure input or a denylisted app, in any state, the Stopped one included', () => {
    for (const kind of ['working', 'needs-you', 'done', 'error', 'killed'] as const) {
      expect(pillVisibility({ ...base, kind, suppressed: 'secure_input' }), kind).toEqual({ show: false, reason: 'suppressed' })
      expect(pillVisibility({ ...base, kind, suppressed: 'app_denied' }).show, kind).toBe(false)
    }
  })
  it('hides while presenting, and while Knack itself is the app in front', () => {
    expect(pillVisibility({ ...base, presenting: true }).reason).toBe('presenting')
    expect(pillVisibility({ ...base, knackInFront: true }).reason).toBe('knack_in_front')
  })
})

describe('where the pill sits', () => {
  it('is 280 by 44, bottom-right of the work area with a 16 px margin', () => {
    expect(PILL_SIZE).toEqual({ width: 280, height: 44 })
    expect(pillBounds({ x: 0, y: 25, width: 1440, height: 875 })).toEqual({ x: 1440 - 280 - PILL_MARGIN, y: 25 + 875 - 44 - PILL_MARGIN, width: 280, height: 44 })
  })
  it('sits on the second display when the work (the pointer) is there', () => {
    const d1 = { id: 1, workArea: { x: 0, y: 25, width: 1440, height: 875 } }
    const d2 = { id: 2, workArea: { x: 1440, y: 0, width: 1920, height: 1055 } }
    expect(workDisplay([d1, d2], { x: 2000, y: 400 }, d1).id).toBe(2)
    expect(workDisplay([d1, d2], { x: 100, y: 400 }, d2).id).toBe(1)
    expect(pillBounds(d2.workArea).x).toBe(1440 + 1920 - 280 - 16)
  })
  it('takes the pointer only on the Stop button and the label, never on the rest of the pill', () => {
    expect(interactiveParts('working')).toEqual({ stop: true, open: true })
    expect(interactiveParts('needs-you')).toEqual({ stop: false, open: true })
    expect(interactiveParts('idle')).toEqual({ stop: false, open: false })
  })
})
