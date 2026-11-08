// The shell's edge cases that code can settle without a screen (docs/knack-ux/edge-cases-a.md lists every case, what happens, and which test or manual step covers it): a profile
// from an earlier build, a damaged or unwritable settings file, a damaged window file, a clock set back, the Mac waking from sleep, and the one rule every overlay window follows
// (on every Space and over full-screen apps, never takes the keyboard unless it is for typing, hidden from screen capture).
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createActivityTracker } from '../src/main/knack/activity'
import { createPillController } from '../src/main/knack/pill-controller'
import { PILL_TIMING, stepPill, IDLE_PILL, type PillSignals } from '../src/main/knack/pill-state'
import { planModels } from '../src/main/knack/model-mode'
import { createWindowStateStore, parseWindowState } from '../src/main/knack/window-state'
import { SettingsStore } from '../src/main/settings'
import { coerceSettings, DEFAULT_SETTINGS } from '../src/shared/settings'
import { stripComments } from './brand-scan'

const tmp: string[] = []
const dir = (): string => {
  const d = fs.mkdtempSync(path.join(os.tmpdir(), 'knack-edge-'))
  tmp.push(d)
  return d
}
afterEach(() => {
  vi.restoreAllMocks()
  for (const d of tmp.splice(0)) {
    try {
      fs.chmodSync(d, 0o700)
    } catch {
      /* gone */
    }
    fs.rmSync(d, { recursive: true, force: true })
  }
})

describe('an update from an earlier build: the saved settings of that build', () => {
  it('keep what is valid, drop what is not, and fill the new keys with the new defaults (nothing is lost, nothing crashes)', () => {
    const old = { persona: 'marcus', helpLevelMode: 'locked', lockedLevel: 3, onboardingDone: true, showDock: true, theme: 'dark', awarenessEnabled: true, someFutureKey: 1, cueEnabled: 'yes', launchAtLogin: false }
    const s = coerceSettings(old)
    expect(s).toMatchObject({ helpLevelMode: 'locked', lockedLevel: 3, onboardingDone: true, theme: 'dark', launchAtLogin: false }) // the worker's own choices survive, even the ones that differ from the new defaults
    expect(s.cueEnabled).toBe(DEFAULT_SETTINGS.cueEnabled) // 'yes' is not a boolean: the default
    expect(s.keepAwakeWhileWorking).toBe(true) // a key that did not exist yet
    expect(s.moveAsideWhileWorking).toBe(true)
    expect(s.persona).toBe('understudy') // an older persona becomes the one identity
    expect('someFutureKey' in s).toBe(false)
  })
  it('a window file from an earlier build (other keys, a wrong version, bad rectangles) is read as far as it is valid', () => {
    const w = parseWindowState({ version: 0, displays: { '1': { x: 10, y: 20, width: 800, height: 600 }, 'x': { x: 1, y: 1, width: 1, height: 1 }, '2': { x: 'a' }, '3': { x: 0, y: 0, width: -5, height: 10 } }, last: '1', junk: true })
    expect(Object.keys(w.displays)).toEqual(['1'])
    expect(w.last).toBe('1')
    expect(parseWindowState(null)).toEqual({ version: 1, displays: {} })
    expect(parseWindowState('x')).toEqual({ version: 1, displays: {} })
  })
})

describe('a damaged settings file', () => {
  it('is read as the defaults (the app starts), and the next change writes a good file', () => {
    const d = dir()
    fs.writeFileSync(path.join(d, 'settings.json'), '{ not json at all')
    const s = new SettingsStore(d)
    expect(s.get()).toMatchObject({ launchAtLogin: true, cueEnabled: true, moveAsideWhileWorking: true })
    s.patch({ lockedLevel: 4 })
    s.flush()
    expect(JSON.parse(fs.readFileSync(path.join(d, 'settings.json'), 'utf8')).lockedLevel).toBe(4)
  })
  it('a file that is valid JSON of the wrong shape (a list, a number, null) is the defaults too', () => {
    for (const body of ['[]', '7', 'null', '"x"']) {
      const d = dir()
      fs.writeFileSync(path.join(d, 'settings.json'), body)
      expect(new SettingsStore(d).get()).toEqual(new SettingsStore(null).get())
    }
  })
  it('a pinned key (the old panel set-up in the Knack app) wins over a damaged or old file and over every change', () => {
    const d = dir()
    fs.writeFileSync(path.join(d, 'settings.json'), JSON.stringify({ onboardingDone: false }))
    const s = new SettingsStore(d, { forced: { onboardingDone: true } })
    expect(s.get().onboardingDone).toBe(true)
    s.patch({ onboardingDone: false })
    expect(s.get().onboardingDone).toBe(true)
  })
})

describe('a home that cannot be written (read-only, or the disk is full)', () => {
  it('losing a settings write is logged and never thrown: the app keeps running on what it holds', () => {
    const d = dir()
    const s = new SettingsStore(d)
    fs.chmodSync(d, 0o500) // nothing can be created in it
    const err = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    s.patch({ lockedLevel: 4 })
    expect(() => s.flush()).not.toThrow()
    expect(s.get().lockedLevel).toBe(4)
    if (process.getuid && process.getuid() !== 0) expect(err).toHaveBeenCalled()
  })
  it('losing a window position write only forgets the position', () => {
    const store = createWindowStateStore({ file: '/nowhere/knack-window.json', readFile: () => { throw new Error('none') }, writeFile: () => { throw new Error('EROFS') }, setTimer: () => 1, clearTimer: () => undefined })
    store.touch(1, { x: 0, y: 0, width: 800, height: 600 })
    expect(() => store.flush()).not.toThrow()
    expect(store.get(1)).toEqual({ x: 0, y: 0, width: 800, height: 600 }) // still held in memory for this session
  })
})

describe('first launch with no key, and a key that was removed', () => {
  const boot = async (hasKey: boolean, switchOn = true) => planModels({ switchOn, hasKey, envOverride: undefined, bootCheck: async () => true })
  it('with no key it starts on example data and says so in one line (nothing is asked, nothing fails)', async () => {
    const d = await boot(false)
    expect(d).toMatchObject({ mode: 'demo', reason: 'no_key' })
    expect(d.notice).toBe('Running with example data')
  })
  it('a key removed since the last start is the same as no key: the next start is on example data, while a running app keeps what it started with', async () => {
    expect((await boot(true)).mode).toBe('live')
    expect((await boot(false)).mode).toBe('demo')
  })
  it('the worker can switch live models off, and it is example data with the same line', async () => {
    expect(await boot(true, false)).toMatchObject({ mode: 'demo', reason: 'switched_off', notice: 'Running with example data' })
  })
})

describe('a clock set back or forward', () => {
  const sig = (over: Partial<PillSignals> = {}): PillSignals => ({ reachable: true, supervisor: 'idle', runs: [], killed: false, pending: 0, ...over })
  it('a done check does not stay for ever when the clock is set back an hour while it shows', () => {
    const w = stepPill(IDLE_PILL, sig({ supervisor: 'running' }), 10_000_000)
    const done = stepPill(w, sig(), 10_001_000)
    expect(done.kind).toBe('done')
    const later = stepPill(done, sig(), 10_001_000 - 60 * 60_000) // the clock now reads an hour earlier
    expect(later.kind).toBe('idle')
  })
  it('an error does not stay for ever either', () => {
    const w = stepPill(IDLE_PILL, sig({ supervisor: 'running' }), 5_000_000)
    const err = stepPill(w, sig({ supervisor: 'failed' }), 5_001_000)
    expect(err.kind).toBe('error')
    expect(stepPill(err, sig(), 5_001_000 - 3 * 60 * 60_000).kind).toBe('idle')
  })
  it('the timer that clears a done check never waits longer than the check itself, whatever the clock says', () => {
    let now = 1_000_000
    const waits: number[] = []
    const c = createPillController({ now: () => now, setTimer: (_fn, ms) => (waits.push(ms), 1), clearTimer: () => undefined })
    c.ingest(sig({ supervisor: 'running' }))
    now += 1000
    c.ingest(sig()) // done
    now -= 60 * 60_000 // set back an hour
    c.ingest(sig({ supervisor: 'running' })) // working again
    c.ingest(sig()) // done again, with since in the "future"
    for (const ms of waits) expect(ms).toBeLessThanOrEqual(PILL_TIMING.errorMs + 5)
  })
  it('a service that is silent while a run works is an error after the limit, even when the clock was set back in between', () => {
    const w = stepPill(IDLE_PILL, sig({ supervisor: 'running' }), 9_000_000)
    const silent1 = stepPill(w, sig({ reachable: false }), 9_001_000) // first look that fails
    const silent2 = stepPill(silent1, sig({ reachable: false }), 9_001_000 - 30 * 60_000) // clock set back
    expect(silent2.kind).toBe('error')
    expect(silent2.text).toBe('Lost contact')
  })
})

describe('the Mac wakes from sleep with a run active', () => {
  it('the silence of the service during the sleep is not an outage: forgiving it restarts the count', () => {
    let now = 2_000_000
    const events: string[] = []
    const t = createActivityTracker({ emit: (e) => void events.push(e.type), now: () => now, setTimer: () => 1, clearTimer: () => undefined })
    const sig = (over: Partial<PillSignals>): PillSignals => ({ reachable: true, supervisor: 'idle', runs: [], killed: false, pending: 0, ...over })
    t.ingest(sig({ supervisor: 'running' }))
    now += 1000
    t.ingest(sig({ reachable: false })) // the first look that fails: the count starts here
    now += 20 * 60_000 // the Mac slept for twenty minutes
    t.forgive() // it woke
    t.ingest(sig({ reachable: false })) // the service is still reconnecting
    expect(events).not.toContain('run_failed') // not the outage it would have read as without forgiving
    now += 5000
    t.ingest(sig({ supervisor: 'running' })) // the service is back and the run goes on
    expect(t.state().kind).toBe('working')
  })
})

// The rule every overlay window of the app follows, read from their sources: the corner column, the permission card, the Ask bar, the background pills, the wake cards and the Cue
// panel appear on every Space and over full-screen apps, and none of them can be captured as a screenshot (the model must never see its own prompts).
describe('every overlay window', () => {
  const src = path.resolve(__dirname, '../src/main')
  const files = ['hud.ts', 'toast.ts', 'knack/ask-bar.ts', 'knack/agent-pills.ts', 'wake/card-window.ts', 'cue/panel-window.ts']
  it.each(files)('%s is on every Space and over full-screen apps, hidden from capture, and out of the task bar', (f) => {
    const code = stripComments(fs.readFileSync(path.join(src, f), 'utf8'))
    expect(code, 'visible on every Space').toMatch(/setVisibleOnAllWorkspaces\(true, \{ visibleOnFullScreen: true/)
    expect(code, 'hidden from capture').toMatch(/setContentProtection\(!capturable\)/)
    expect(code, 'out of the task bar').toMatch(/skipTaskbar: true/)
    expect(code, 'always on top').toMatch(/alwaysOnTop: true/)
  })
  it.each(['hud.ts', 'knack/agent-pills.ts', 'wake/card-window.ts'])('%s never takes the keyboard from the app the worker is in', (f) => {
    expect(stripComments(fs.readFileSync(path.join(src, f), 'utf8'))).toMatch(/focusable: false/)
  })
  it('only the Ask bar (the window for typing) is focusable, and it is a panel so Knack does not come to the front with it', () => {
    const code = stripComments(fs.readFileSync(path.join(src, 'knack/ask-bar.ts'), 'utf8'))
    expect(code).toMatch(/focusable: true/)
    expect(code).toMatch(/type: 'panel'/)
  })
})
