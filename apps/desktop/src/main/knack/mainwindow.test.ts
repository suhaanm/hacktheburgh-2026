import { describe, expect, it, vi } from 'vitest'
import { KNACK_IPC } from '../../shared/knack'
import { STARTING_URL, createMainWindowController, showsAtStart, type MainWindowEvent, type WindowPort } from './mainwindow'
import { createQuitGuard, sheetFor, type QuitChoice } from './quit-guard'
import { createWindowStateStore } from './window-state'
import type { Rect } from './window-bounds'

/** A window that does what the real one does to its own flags, and records what it was asked. */
function fakeWindow(over: { visible?: boolean; minimised?: boolean; focused?: boolean; bounds?: Rect } = {}) {
  const w = { visible: over.visible ?? true, minimised: over.minimised ?? false, focused: over.focused ?? true, fullScreen: false, destroyed: false, bounds: over.bounds ?? { x: 100, y: 100, width: 1152, height: 735 } }
  const calls: string[] = []
  const handlers = new Map<string, ((e: { preventDefault(): void }) => void)[]>()
  const port: WindowPort = {
    show: () => (calls.push('show'), (w.visible = true), (w.minimised = false)),
    showInactive: () => (calls.push('showInactive'), (w.visible = true), (w.minimised = false)),
    hide: () => (calls.push('hide'), (w.visible = false)),
    focus: () => (calls.push('focus'), (w.focused = true)),
    restore: () => (calls.push('restore'), (w.minimised = false)),
    minimize: () => (calls.push('minimize'), (w.minimised = true), (w.focused = false)),
    isVisible: () => w.visible,
    isMinimized: () => w.minimised,
    isFocused: () => w.focused,
    isFullScreen: () => w.fullScreen,
    isDestroyed: () => w.destroyed,
    getBounds: () => w.bounds,
    destroy: () => (calls.push('destroy'), (w.destroyed = true)),
    loadURL: (u) => void calls.push(`load ${u}`),
    send: (c) => void calls.push(`send ${c}`),
    webContentsId: () => 7,
    on: ((event: string, cb: (e: { preventDefault(): void }) => void) => void handlers.set(event, [...(handlers.get(event) ?? []), cb])) as WindowPort['on'],
  }
  const emit = (event: string): { prevented: boolean } => {
    let prevented = false
    for (const h of handlers.get(event) ?? []) h({ preventDefault: () => (prevented = true) })
    return { prevented }
  }
  return { w, port, calls, emit }
}

const displays = () => [{ id: 1, workArea: { x: 0, y: 25, width: 1440, height: 875 } }]
const rig = (over: Parameters<typeof fakeWindow>[0] = {}) => {
  const f = fakeWindow(over)
  const timers: (() => void)[] = []
  const store = createWindowStateStore({ file: '/x/w.json', readFile: () => { throw new Error('none') }, writeFile: () => undefined, setTimer: (fn) => (timers.push(fn), timers.length), clearTimer: () => undefined })
  const main = createMainWindowController(f.port, { store, displays, hidden: false })
  return { ...f, main, store, timers }
}

describe('closing', () => {
  it('Cmd-W and the red button hide the window and keep everything else: the page stays alive, nothing is destroyed', () => {
    const r = rig()
    const closed = r.emit('close')
    expect(closed.prevented).toBe(true)
    expect(r.calls).toEqual(['hide'])
    expect(r.w.destroyed).toBe(false)
    expect(r.main.state()).toMatchObject({ exists: true, visible: false })
  })
  it('a close during quit really closes', () => {
    const r = rig()
    r.main.setQuitting()
    expect(r.emit('close').prevented).toBe(false)
    expect(r.calls).toEqual([])
  })
})

describe('the Dock icon and Activate', () => {
  it('from closed: shows the window again and takes the keyboard (on Home at the last size and place: the window is the same one)', () => {
    const r = rig({ visible: false, focused: false })
    r.main.show()
    expect(r.calls).toEqual(['show', 'focus'])
    expect(r.main.state()).toMatchObject({ visible: true, focused: true })
  })
  it('from minimised: restores it first', () => {
    const r = rig({ minimised: true, focused: false })
    r.main.show()
    expect(r.calls).toEqual(['restore', 'show', 'focus'])
    expect(r.main.state().minimised).toBe(false)
  })
  it('from behind other windows: brings it to the front, and never makes a second window', () => {
    const r = rig({ focused: false })
    r.main.show()
    expect(r.calls).toEqual(['show', 'focus'])
  })
  it('bringing it back without taking the keyboard (a quiet restore) shows it inactive, and a hidden run never shows it', () => {
    const r = rig({ minimised: true, focused: false })
    r.main.restoreQuietly()
    expect(r.calls).toEqual(['restore', 'showInactive'])
    const f = fakeWindow({ visible: false })
    const hiddenRun = createMainWindowController(f.port, { store: createWindowStateStore({ file: null, setTimer: () => 1, clearTimer: () => undefined }), displays, hidden: true })
    hiddenRun.restoreQuietly()
    expect(f.calls).toEqual([])
  })
  it('minimising moves it to the Dock (it does not hide it), except in full screen', () => {
    const r = rig()
    r.main.minimise()
    expect(r.calls).toEqual(['minimize'])
    expect(r.main.state()).toMatchObject({ minimised: true, visible: false })
    const full = rig()
    full.w.fullScreen = true
    full.main.minimise()
    expect(full.calls).toEqual([])
  })
})

describe('remembering where it is', () => {
  it('saves its bounds under the display it sits on, once, 400 ms after a move', () => {
    const r = rig()
    r.emit('move')
    r.emit('resize')
    expect(r.store.get(1)).toEqual({ x: 100, y: 100, width: 1152, height: 735 })
    expect(r.store.lastDisplay()).toBe(1)
  })
  it('does not save while minimised, hidden or full screen', () => {
    const r = rig({ minimised: true })
    r.emit('move')
    expect(r.store.get(1)).toBeNull()
    const h = rig({ visible: false })
    h.emit('resize')
    expect(h.store.get(1)).toBeNull()
  })
})

describe('the page and the events', () => {
  it('loads its own starting page, then the dashboard, and tells the starting page what is happening', () => {
    const r = rig()
    r.main.loadStarting()
    r.main.pushUiState({ kind: 'starting', text: 'Starting Knack…' })
    r.main.loadDashboard('app://knack/')
    expect(r.calls).toEqual([`load ${STARTING_URL}`, `send ${KNACK_IPC.state}`, 'load app://knack/'])
    expect(r.main.uiState()).toEqual({ kind: 'starting', text: 'Starting Knack…' })
    expect(r.main.owns(7)).toBe(true)
    expect(r.main.owns(8)).toBe(false)
  })
  it('passes focus, hide and minimise to the shell, and stops when unsubscribed', () => {
    const r = rig()
    const seen: MainWindowEvent[] = []
    const off = r.main.subscribe((e) => seen.push(e))
    for (const e of ['focus', 'blur', 'hide', 'minimize', 'restore', 'show']) r.emit(e)
    off()
    r.emit('focus')
    expect(seen).toEqual(['focus', 'blur', 'hide', 'minimize', 'restore', 'show'])
  })
  it('does nothing after it is destroyed', () => {
    const r = rig()
    r.main.dispose()
    r.main.show()
    r.main.minimise()
    expect(r.calls).toEqual(['destroy'])
    expect(r.main.state().exists).toBe(false)
  })
})

describe('quit', () => {
  function guardRig(over: { running?: boolean; due?: boolean; choice?: QuitChoice } = {}) {
    const calls: string[] = []
    const asked: ReturnType<typeof sheetFor>[] = []
    const guard = createQuitGuard({
      running: () => over.running ?? false,
      awayRoutineDueWithin24h: () => over.due ?? false,
      ask: async (s) => (asked.push(s), over.choice ?? 'keep_working'),
      stopAll: async () => void calls.push('stopAll'),
      quit: () => void calls.push('quit'),
      markQuitting: () => void calls.push('markQuitting'),
    })
    const event = { prevented: false, preventDefault() { this.prevented = true } }
    return { guard, calls, asked, event }
  }
  const settle = () => new Promise((r) => setTimeout(r, 0))

  it('with nothing running it quits at once, without a sheet', () => {
    const g = guardRig()
    g.guard.onBeforeQuit(g.event)
    expect(g.event.prevented).toBe(false)
    expect(g.calls).toEqual(['markQuitting'])
    expect(g.asked).toEqual([])
  })
  it('with a job running it stops the quit and asks: "Knack is working. Stop it and quit?" with two buttons', async () => {
    const g = guardRig({ running: true })
    g.guard.onBeforeQuit(g.event)
    await settle()
    expect(g.event.prevented).toBe(true)
    expect(g.asked).toEqual([{ message: 'Knack is working. Stop it and quit?', buttons: ['Stop and quit', 'Keep working'] }])
    expect(g.calls).toEqual([]) // Keep working: nothing was stopped, nothing quit
  })
  it('Stop and quit stops everything first, then quits for real (the second quit goes through)', async () => {
    const g = guardRig({ running: true, choice: 'stop_and_quit' })
    g.guard.onBeforeQuit(g.event)
    await settle()
    expect(g.calls).toEqual(['stopAll', 'quit'])
    const again = { prevented: false, preventDefault() { this.prevented = true } }
    g.guard.onBeforeQuit(again)
    expect(again.prevented).toBe(false)
    expect(g.calls.at(-1)).toBe('markQuitting')
    expect(g.guard.proceeding()).toBe(true)
  })
  it('adds one line when a routine set to run while the worker is away is due within 24 hours', async () => {
    const g = guardRig({ running: true, due: true })
    g.guard.onBeforeQuit(g.event)
    await settle()
    expect(g.asked[0]!.detail).toBe('Routines set to run while you are away will not run until you open Knack.')
    expect(sheetFor(false).detail).toBeUndefined()
  })
  it('asks once while the sheet is up, and a sheet that cannot be shown stops nothing', async () => {
    const g = guardRig({ running: true })
    g.guard.onBeforeQuit(g.event)
    g.guard.onBeforeQuit({ preventDefault: vi.fn() })
    await settle()
    expect(g.asked).toHaveLength(1)
    const broken = createQuitGuard({ running: () => true, awayRoutineDueWithin24h: () => false, ask: async () => { throw new Error('no window') }, stopAll: vi.fn(), quit: vi.fn(), markQuitting: vi.fn() })
    const ev = { prevented: false, preventDefault() { this.prevented = true } }
    broken.onBeforeQuit(ev)
    await settle()
    expect(ev.prevented).toBe(true)
  })
})

describe('launch at login', () => {
  it('shows no window: only the menu bar item and the Dock icon (a normal launch shows it; a hidden check never does)', () => {
    expect(showsAtStart({ hidden: false, openedAtLogin: true })).toBe(false)
    expect(showsAtStart({ hidden: false, openedAtLogin: false })).toBe(true)
    expect(showsAtStart({ hidden: true, openedAtLogin: false })).toBe(false)
  })
  it('and the Dock icon opens it afterwards, from closed', () => {
    const r = rig({ visible: false, focused: false })
    r.main.show()
    expect(r.main.state()).toMatchObject({ visible: true, focused: true })
  })
})
