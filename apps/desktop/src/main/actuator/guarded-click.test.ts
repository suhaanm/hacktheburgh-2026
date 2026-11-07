// S-18: the hit test and the click in ONE process. Against fakes only: the real script (GUARDED_CLICK_JXA) has never been executed and no real
// click is allowed before the owner approves the supervised ladder. What is checked here: the script's shape (it compares the pinned
// window BEFORE it posts anything, takes every value as argv, reads no title), the request and answer plumbing, and what the actuator does
// with each answer. The path is OFF unless a guardedClick is injected or UNDERSTUDY_JXA_CLICK=1.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { setKilled } from '../kill-flag'
import { createActuator, GUARDED_CLICK_JXA, guardedClickArgs, guardedClickReason, jxaClickFromEnv, parseGuardedClick, type DesktopProbe, type GuardedClickOutcome, type GuardedClickRequest } from './index'

afterEach(() => {
  setKilled(false)
  delete process.env.UNDERSTUDY_JXA_CLICK
})

const DISPLAY = { x: 0, y: 0, width: 1728, height: 1117 }
const WIN = { id: 7, pid: 100, owner: 'TextEdit' }
const TEXTEDIT = { app: 'TextEdit', window: WIN } as const

function rig(opts: { guarded?: (r: GuardedClickRequest) => Promise<GuardedClickOutcome>; jxaClick?: boolean; dryRun?: boolean; hit?: { owner: string; layer: number; windowId?: number; pid?: number } | null } = {}) {
  const osascript = vi.fn(async (_a: string[]) => undefined)
  const guarded = opts.guarded ? vi.fn(opts.guarded) : undefined
  const reads: Array<{ x: number; y: number }> = []
  const probe: DesktopProbe = {
    frontmostApp: async () => 'TextEdit',
    frontWindow: async () => ({ owner: 'TextEdit', layer: 0, windowId: 7, pid: 100 }),
    topWindowAt: async (p) => (reads.push(p), opts.hit === undefined ? { owner: 'TextEdit', layer: 0, windowId: 7, pid: 100 } : opts.hit),
  }
  const actuator = createActuator({ platform: 'darwin', dryRun: opts.dryRun ?? false, isTrusted: () => true, displayBounds: () => DISPLAY, scaleFactor: () => 2, probe, osascript, guardedClick: guarded, jxaClick: opts.jxaClick, ownPid: 4242, killFileExists: () => false })
  return { actuator, osascript, guarded, reads }
}

describe('the script', () => {
  it('reads the window list, compares the pinned window, and only then posts: nothing is posted before the comparison', () => {
    const j = GUARDED_CLICK_JXA
    expect(j).toContain('CGWindowListCopyWindowInfo')
    const compare = j.indexOf('window_changed')
    const firstPost = j.indexOf('CGEventPost')
    expect(compare).toBeGreaterThan(0)
    expect(firstPost).toBeGreaterThan(compare)
    expect(j.indexOf('no_window')).toBeLessThan(firstPost)
    // every post is after a return on a mismatch: there is exactly one place a window is accepted
    expect(j).toMatch(/Number\(hit\.kCGWindowNumber\) !== pinId \|\| Number\(hit\.kCGWindowOwnerPID\) !== pinPid\) return/)
  })

  it('takes every value as argv, reads no title or text, and does not use System Events', () => {
    const j = GUARDED_CLICK_JXA
    expect(j).not.toMatch(/System Events|kCGWindowName|title|\$\{|eval|doShellScript/i)
    for (let i = 0; i < 8; i++) expect(j).toContain(`argv[${i}]`)
    expect(j).not.toContain('argv[8]')
  })

  it('skips the click-through furniture exactly as the hit test does', () => {
    const j = GUARDED_CLICK_JXA
    expect(j).toContain("name === 'Dock'")
    expect(j).toContain("name === 'Window Server'")
    expect(j).toContain('kCGWindowAlpha === 0')
  })

  it('the arguments are the point, the double flag, the pin, our pid and the display, as rounded integers after `--`', () => {
    const args = guardedClickArgs({ x: 412.6, y: 300.2, double: true, pin: WIN, ownPid: 4242, display: { width: 1728, height: 1117 } })
    expect(args.slice(0, 3)).toEqual(['-l', 'JavaScript', '-e'])
    expect(args[3]).toBe(GUARDED_CLICK_JXA)
    expect(args.slice(4)).toEqual(['--', '413', '300', '1', '7', '100', '4242', '1728', '1117'])
    expect(guardedClickArgs({ x: 1, y: 2, double: false, pin: WIN, ownPid: 1, display: { width: 3, height: 4 } }).slice(7, 8)).toEqual(['0'])
  })
})

describe('the answer', () => {
  it('parses clicked, the known refusals, and treats anything else as unreadable (never as a click)', () => {
    expect(parseGuardedClick('{"clicked":true}\n')).toEqual({ clicked: true })
    expect(parseGuardedClick('{"clicked":false,"why":"window_changed"}')).toEqual({ clicked: false, why: 'window_changed' })
    expect(parseGuardedClick('{"clicked":false,"why":"no_window"}')).toEqual({ clicked: false, why: 'no_window' })
    expect(parseGuardedClick('{"clicked":false,"why":"event_failed"}')).toEqual({ clicked: false, why: 'event_failed' })
    for (const bad of ['', 'null', 'true', '{"clicked":"true"}', '{"clicked":1}', '{"clicked":false,"why":"anything else"}', 'not json', '{"why":"window_changed"}']) expect(parseGuardedClick(bad), bad).toMatchObject({ clicked: false })
    expect(parseGuardedClick('{"clicked":false,"why":"anything else"}')).toEqual({ clicked: false, why: 'unreadable' })
    for (const w of ['no_window', 'window_changed', 'event_failed', 'unreadable'] as const) expect(guardedClickReason(w).length).toBeGreaterThan(10)
  })
})

describe('the actuator with the in-process click', () => {
  const A = { x: 250, y: 500 }

  it('one script does the last look and the click: the request carries the pin, our pid and the display; osascript is not used; the point is read once (the first guard only)', async () => {
    const r = rig({ guarded: async () => ({ clicked: true }) })
    const res = await r.actuator.clickAt(A, { target: TEXTEDIT })
    expect(res).toEqual({ ok: true })
    expect(r.guarded).toHaveBeenCalledTimes(1)
    expect(r.guarded!.mock.calls[0]![0]).toEqual({ x: 432, y: 559, double: false, pin: { id: 7, pid: 100 }, ownPid: 4242, display: { width: 1728, height: 1117 } })
    expect(r.osascript).not.toHaveBeenCalled()
    expect(r.reads).toHaveLength(1) // the old path reads the point twice; the second look is now inside the click's own process
  })

  it('a double click is one request with double true', async () => {
    const r = rig({ guarded: async () => ({ clicked: true }) })
    await r.actuator.clickAt(A, { target: TEXTEDIT, double: true })
    expect(r.guarded!.mock.calls[0]![0].double).toBe(true)
  })

  it.each([
    ['window_changed', 'not the one this task started in'],
    ['no_window', 'could not tell which window'],
    ['event_failed', 'could not be created'],
    ['unreadable', 'nothing was clicked'],
  ] as const)('%s is a refusal (blocked), never a failure and never a click', async (why, text) => {
    const r = rig({ guarded: async () => ({ clicked: false, why }) })
    const res = await r.actuator.clickAt(A, { target: TEXTEDIT })
    expect(res).toMatchObject({ ok: false, reason: 'blocked' })
    expect(res.detail).toContain(text)
    expect(r.osascript).not.toHaveBeenCalled()
  })

  it('an exception in the script is a failure, not a click, and nothing falls back to the two-script click', async () => {
    const r = rig({
      guarded: async () => {
        throw new Error('osascript died')
      },
    })
    const res = await r.actuator.clickAt(A, { target: TEXTEDIT })
    expect(res).toMatchObject({ ok: false, reason: 'failed' })
    expect(r.osascript).not.toHaveBeenCalled()
  })

  it('every earlier guard still runs first: no window pinned, the wrong app, a changed window at the first look, the kill switch and a Stop', async () => {
    const guard = async () => ({ clicked: true as const })
    const noPin = rig({ guarded: guard })
    expect(await noPin.actuator.clickAt(A, { target: { app: 'TextEdit' } })).toMatchObject({ ok: false, reason: 'blocked' })
    const wrongApp = rig({ guarded: guard, hit: { owner: 'Safari', layer: 0, windowId: 7, pid: 100 } })
    expect(await wrongApp.actuator.clickAt(A, { target: TEXTEDIT })).toMatchObject({ ok: false, reason: 'blocked' })
    const moved = rig({ guarded: guard, hit: { owner: 'TextEdit', layer: 0, windowId: 8, pid: 100 } })
    expect(await moved.actuator.clickAt(A, { target: TEXTEDIT })).toMatchObject({ ok: false, reason: 'blocked' })
    const stopped = rig({ guarded: guard })
    expect(await stopped.actuator.clickAt(A, { target: TEXTEDIT, cancelled: () => true })).toMatchObject({ ok: false, reason: 'blocked' })
    setKilled(true)
    const killed = rig({ guarded: guard })
    expect(await killed.actuator.clickAt(A, { target: TEXTEDIT })).toMatchObject({ ok: false, reason: 'blocked' })
    for (const r of [noPin, wrongApp, moved, stopped, killed]) {
      expect(r.guarded).not.toHaveBeenCalled()
      expect(r.osascript).not.toHaveBeenCalled()
    }
  })

  it('a dry run performs nothing, on either path', async () => {
    const r = rig({ guarded: async () => ({ clicked: true }), dryRun: true })
    expect(await r.actuator.clickAt(A, { target: TEXTEDIT })).toMatchObject({ ok: true, reason: 'dry-run' })
    expect(r.guarded).not.toHaveBeenCalled()
    expect(r.osascript).not.toHaveBeenCalled()
  })
})

describe('it is off by default', () => {
  it('without an injected click or the flag, the two-script click is used and the second hit test still runs', async () => {
    const r = rig()
    expect(await r.actuator.clickAt({ x: 250, y: 500 }, { target: TEXTEDIT })).toEqual({ ok: true })
    expect(r.osascript).toHaveBeenCalledTimes(1)
    expect(r.osascript.mock.calls[0]![0].join(' ')).toContain('click at')
    expect(r.reads).toHaveLength(2)
  })

  it('UNDERSTUDY_JXA_CLICK is on only for exactly "1"', () => {
    expect(jxaClickFromEnv()).toBe(false)
    process.env.UNDERSTUDY_JXA_CLICK = 'true'
    expect(jxaClickFromEnv()).toBe(false)
    process.env.UNDERSTUDY_JXA_CLICK = '1'
    expect(jxaClickFromEnv()).toBe(true)
  })
})
