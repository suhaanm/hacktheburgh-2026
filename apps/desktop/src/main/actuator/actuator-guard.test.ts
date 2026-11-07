// The actuator's target guard, with a fake desktop (probe), a fake osascript and a fake clock. Nothing here touches the real desktop.
// It encodes the two weaknesses a supervised check found in another actuator: a click that landed in the wrong app (a scale error and
// no hit test) and keystrokes that went to whatever had focus. Real input must prove where it lands, and fail closed when it cannot.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { setKilled } from '../kill-flag'
import { createActuator, ownerMatchesTarget, parseWindowHit, type DesktopProbe } from './index'
import { aspectMatches, normToPoints, pointsToNorm } from './mapping'

afterEach(() => setKilled(false))

const DISPLAY = { x: 0, y: 0, width: 1728, height: 1117 }
const WIN = { id: 7, pid: 100, owner: 'TextEdit' }
const TEXTEDIT = { app: 'TextEdit', window: WIN } as const

interface Rig {
  actuator: ReturnType<typeof createActuator>
  osascript: ReturnType<typeof vi.fn>
  openApp: ReturnType<typeof vi.fn>
  writeClipboard: ReturnType<typeof vi.fn>
  windowReads: Array<{ x: number; y: number }>
  frontReads: number
  slept: number[]
}

function rig(opts: { front?: { owner: string; layer: number; windowId?: number; pid?: number } | null; hit?: (p: { x: number; y: number }) => { owner: string; layer: number; windowId?: number; pid?: number } | null | Promise<never>; fronts?: Array<string | null>; dryRun?: boolean; display?: typeof DISPLAY; scale?: number } = {}): Rig {
  const osascript = vi.fn(async (_args: string[]) => undefined)
  const openApp = vi.fn(async (_n: string) => undefined)
  const writeClipboard = vi.fn(async (_t: string) => undefined)
  const windowReads: Array<{ x: number; y: number }> = []
  const slept: number[] = []
  const fronts = opts.fronts ?? ['TextEdit']
  const state = { frontReads: 0 }
  const probe: DesktopProbe = {
    frontmostApp: async () => fronts[Math.min(state.frontReads++, fronts.length - 1)],
    frontWindow: async () => (opts.front === undefined ? { owner: 'TextEdit', layer: 0, windowId: 7, pid: 100 } : opts.front),
    topWindowAt: async (p) => {
      windowReads.push(p)
      return opts.hit ? opts.hit(p) : { owner: 'TextEdit', layer: 0, windowId: 7, pid: 100 }
    },
  }
  const actuator = createActuator({
    platform: 'darwin',
    dryRun: opts.dryRun ?? false,
    isTrusted: () => true,
    displayBounds: () => opts.display ?? DISPLAY,
    scaleFactor: () => opts.scale ?? 2,
    probe,
    osascript,
    openAppProcess: openApp,
    readClipboard: async () => 'before',
    writeClipboard,
    openExternal: async () => undefined,
    showItemInFolder: () => undefined,
    sleep: async (ms) => void slept.push(ms),
    focusTimeoutMs: 500,
    focusPollMs: 100,
  })
  return {
    actuator,
    osascript,
    openApp,
    writeClipboard,
    windowReads,
    slept,
    get frontReads() {
      return state.frontReads
    },
  }
}

describe('a click must name its app and land in that app\'s window', () => {
  it('without a target app it is refused, and the desktop is not even probed', async () => {
    const r = rig()
    const out = await r.actuator.clickAt({ x: 500, y: 500 })
    expect(out).toMatchObject({ ok: false, reason: 'blocked' })
    expect(out.detail).toMatch(/no app was named/)
    expect(r.osascript).not.toHaveBeenCalled()
    expect(r.windowReads).toEqual([])
  })

  it('THE INCIDENT: the target app is in front but another app\'s window covers the point: refused, nothing sent to the OS', async () => {
    const r = rig({ hit: () => ({ owner: 'Claude', layer: 0, windowId: 7, pid: 100 }), fronts: ['TextEdit'] })
    const out = await r.actuator.clickAt({ x: 500, y: 500 }, { target: TEXTEDIT })
    expect(out).toMatchObject({ ok: false, reason: 'blocked' })
    expect(out.detail).toMatch(/belongs to Claude, not to TextEdit/)
    expect(r.osascript).not.toHaveBeenCalled()
  })

  it('an unreadable window list is a refusal, not a pass', async () => {
    const r = rig({ hit: () => null })
    expect(await r.actuator.clickAt({ x: 500, y: 500 }, { target: TEXTEDIT })).toMatchObject({ ok: false, reason: 'blocked' })
    const throwing = rig({ hit: () => Promise.reject(new Error('boom')) as never })
    expect(await throwing.actuator.clickAt({ x: 500, y: 500 }, { target: TEXTEDIT })).toMatchObject({ ok: false, reason: 'blocked' })
    expect(r.osascript).not.toHaveBeenCalled()
    expect(throwing.osascript).not.toHaveBeenCalled()
  })

  it('a window of the named app passes (case-insensitive), and the hit test asks about the very point that is clicked', async () => {
    const r = rig({ hit: () => ({ owner: 'textedit', layer: 0, windowId: 7, pid: 100 }) })
    expect(await r.actuator.clickAt({ x: 500, y: 500 }, { target: TEXTEDIT })).toEqual({ ok: true })
    expect(r.windowReads).toEqual([{ x: 864, y: 559 }, { x: 864, y: 559 }]) // the hit test, and a second look right before the click
    expect(r.osascript).toHaveBeenCalledWith(['-e', 'tell application "System Events" to click at {864, 559}'])
  })

  it('a double click and a scroll are guarded the same way', async () => {
    const wrong = rig({ hit: () => ({ owner: 'Safari', layer: 0, windowId: 7, pid: 100 }) })
    expect(await wrong.actuator.clickAt({ x: 10, y: 10 }, { double: true, target: TEXTEDIT })).toMatchObject({ ok: false, reason: 'blocked' })
    expect(await wrong.actuator.scroll({ x: 500, y: 500 }, 5, { target: TEXTEDIT })).toMatchObject({ ok: false, reason: 'blocked' })
    expect(wrong.osascript).not.toHaveBeenCalled()
    const right = rig()
    expect(await right.actuator.scroll({ x: 500, y: 500 }, 5, { target: TEXTEDIT })).toEqual({ ok: true })
    expect(right.windowReads).toHaveLength(2) // the hit test and the second look
  })

  it('the assistant\'s own app and terminals are never a target, whatever the caller says; a menu bar or Dock window is not the target either', async () => {
    for (const app of ['Claude', 'Terminal', 'iTerm2', 'Claude Code']) {
      const r = rig({ hit: () => ({ owner: app, layer: 0 }) })
      expect(await r.actuator.clickAt({ x: 1, y: 1 }, { target: { app } }), app).toMatchObject({ ok: false, reason: 'blocked' })
      expect(r.osascript).not.toHaveBeenCalled()
      expect(r.windowReads, 'refused before the desktop was read').toEqual([])
    }
    const bar = rig({ hit: () => ({ owner: 'Window Server', layer: 25, windowId: 7, pid: 100 }) })
    expect(await bar.actuator.clickAt({ x: 500, y: 1 }, { target: TEXTEDIT })).toMatchObject({ ok: false, reason: 'blocked' })
    const dock = rig({ hit: () => ({ owner: 'Dock', layer: 20, windowId: 7, pid: 100 }) })
    expect(await dock.actuator.clickAt({ x: 500, y: 999 }, { target: TEXTEDIT })).toMatchObject({ ok: false, reason: 'blocked' })
  })

  it('a browser task accepts any browser window and nothing else', async () => {
    const safari = rig({ hit: () => ({ owner: 'Safari', layer: 0, windowId: 7, pid: 100 }) })
    expect(await safari.actuator.clickAt({ x: 500, y: 500 }, { target: { browser: true, window: { id: 7, pid: 100, owner: 'Safari' } } })).toEqual({ ok: true })
    const calc = rig({ hit: () => ({ owner: 'Calculator', layer: 0, windowId: 7, pid: 100 }) })
    expect(await calc.actuator.clickAt({ x: 500, y: 500 }, { target: { browser: true, window: { id: 7, pid: 100, owner: 'Safari' } } })).toMatchObject({ ok: false, reason: 'blocked' })
    expect(ownerMatchesTarget('Google Chrome', { browser: true })).toBe(true)
    expect(ownerMatchesTarget('Claude', { browser: true })).toBe(false)
  })

  it('the kill switch pressed while the desktop was being read stops the click', async () => {
    const r = rig({
      hit: () => {
        setKilled(true)
        return { owner: 'TextEdit', layer: 0, windowId: 7, pid: 100 }
      },
    })
    expect(await r.actuator.clickAt({ x: 500, y: 500 }, { target: TEXTEDIT })).toMatchObject({ ok: false, reason: 'blocked', detail: 'the kill switch is on' })
    expect(r.osascript).not.toHaveBeenCalled()
  })

  it('a dry run never reads or touches the desktop', async () => {
    const r = rig({ dryRun: true })
    expect(await r.actuator.clickAt({ x: 500, y: 500 })).toMatchObject({ ok: true, reason: 'dry-run' })
    expect(await r.actuator.typeText('hello')).toMatchObject({ ok: true, reason: 'dry-run' })
    expect(r.windowReads).toEqual([])
    expect(r.frontReads).toBe(0)
    expect(r.osascript).not.toHaveBeenCalled()
  })
})

describe('typing waits for the focus and verifies it', () => {
  it('without a target app it is refused', async () => {
    const r = rig()
    expect(await r.actuator.typeText('hello')).toMatchObject({ ok: false, reason: 'blocked' })
    expect(await r.actuator.pressKeys('return')).toMatchObject({ ok: false, reason: 'blocked' })
    expect(r.osascript).not.toHaveBeenCalled()
  })

  it('types at once when the target app already has the focus, with no waiting', async () => {
    const r = rig({ fronts: ['TextEdit'] })
    expect(await r.actuator.typeText('hello', { target: TEXTEDIT })).toEqual({ ok: true })
    expect(r.slept).toEqual([])
    expect(r.osascript).toHaveBeenCalledTimes(1)
  })

  it('an unreadable front app is a refusal after the wait, and not a single key is sent', async () => {
    const r = rig({ fronts: [null] })
    const out = await r.actuator.typeText('hello', { target: TEXTEDIT })
    expect(out).toMatchObject({ ok: false, reason: 'blocked' })
    expect(out.detail).toMatch(/could not tell which app has the focus/)
    expect(r.osascript).not.toHaveBeenCalled()
    expect(r.slept.length).toBe(5) // 500 ms in 100 ms steps
  })

  it('another app holding the focus is not fought over: wait, then refuse; the target is not forced to the front', async () => {
    const r = rig({ fronts: ['Safari'] })
    const out = await r.actuator.typeText('hello', { target: TEXTEDIT })
    expect(out).toMatchObject({ ok: false, reason: 'blocked' })
    expect(out.detail).toMatch(/Safari has the focus, not TextEdit/)
    expect(r.openApp).not.toHaveBeenCalled()
    expect(r.osascript).not.toHaveBeenCalled()
  })

  it('the assistant\'s own window (the approval prompt) holding the focus: the target is brought back once, verified, then typed into', async () => {
    const r = rig({ fronts: ['Alongside', 'Alongside', 'TextEdit'] })
    expect(await r.actuator.typeText('hello', { target: TEXTEDIT })).toEqual({ ok: true })
    expect(r.openApp).toHaveBeenCalledTimes(1)
    expect(r.openApp).toHaveBeenCalledWith('TextEdit')
    expect(r.osascript).toHaveBeenCalledTimes(1)
    // and if the target never comes back, nothing is typed
    const stuck = rig({ fronts: ['Electron'] })
    expect(await stuck.actuator.typeText('hello', { target: TEXTEDIT })).toMatchObject({ ok: false, reason: 'blocked' })
    expect(stuck.openApp).toHaveBeenCalledTimes(1)
    expect(stuck.osascript).not.toHaveBeenCalled()
  })

  it('a focus that arrives a moment late is waited for', async () => {
    const r = rig({ fronts: ['Safari', 'Safari', 'TextEdit'] })
    expect(await r.actuator.typeText('hi', { target: TEXTEDIT })).toEqual({ ok: true })
    expect(r.slept).toEqual([100, 100])
  })

  it('a terminal in front is never typed into, even when it is named as the target', async () => {
    const r = rig({ fronts: ['Terminal'] })
    expect(await r.actuator.typeText('rm -rf', { target: { app: 'Terminal' } })).toMatchObject({ ok: false, reason: 'blocked' })
    expect(await r.actuator.pressKeys('return', { target: { app: 'iTerm2' } })).toMatchObject({ ok: false, reason: 'blocked' })
    expect(r.osascript).not.toHaveBeenCalled()
  })

  it('paste verifies the focus BEFORE it touches the clipboard', async () => {
    const wrong = rig({ fronts: ['Safari'] })
    expect(await wrong.actuator.pasteText!('secret-ish', { target: TEXTEDIT })).toMatchObject({ ok: false, reason: 'blocked' })
    expect(wrong.writeClipboard).not.toHaveBeenCalled()
    const right = rig({ fronts: ['TextEdit'] })
    expect(await right.actuator.pasteText!('hello', { target: TEXTEDIT })).toEqual({ ok: true })
    expect(right.writeClipboard.mock.calls.map((c) => c[0])).toEqual(['hello', 'before'])
  })

  it('the typed text is never in the log', async () => {
    const log = vi.fn()
    const a = createActuator({ platform: 'darwin', dryRun: false, isTrusted: () => true, displayBounds: () => DISPLAY, probe: { frontmostApp: async () => 'TextEdit', frontWindow: async () => ({ owner: 'TextEdit', layer: 0, windowId: 7, pid: 100 }), topWindowAt: async () => null }, osascript: async () => undefined, log, openExternal: async () => undefined, showItemInFolder: () => undefined })
    await a.typeText('my private sentence', { target: TEXTEDIT })
    expect(JSON.stringify(log.mock.calls)).not.toContain('my private sentence')
  })
})

describe('scale: points, not pixels, from the display the point was computed on', () => {
  // A point is a fraction of the display (0-1000). Screenshots at 1x, 2x (retina) or a downscaled width all name the same fraction,
  // and the click goes to points on the display's own bounds. A retina display folds its scale factor into the bounds already.
  const displays = [
    { name: '1x 1440x900', d: { x: 0, y: 0, width: 1440, height: 900 }, scale: 1, shots: [1440, 1280] },
    { name: 'retina 1728x1117', d: DISPLAY, scale: 2, shots: [3456, 1920, 1280] },
    { name: '3x 1080x720', d: { x: 0, y: 0, width: 1080, height: 720 }, scale: 3, shots: [3240, 1920] },
    { name: 'primary at an offset', d: { x: 12, y: 40, width: 1512, height: 982 }, scale: 2, shots: [3024, 1920] },
  ]
  for (const { name, d, scale, shots } of displays) {
    it(`${name}: the same place in any screenshot size becomes the same point on the screen`, async () => {
      const fx = 0.37
      const fy = 0.61
      for (const w of shots) {
        const h = Math.round((w * d.height) / d.width)
        const norm = { x: ((fx * w) / w) * 1000, y: ((fy * h) / h) * 1000 } // pixel (fx*w, fy*h) of a w x h screenshot, normalised by that screenshot's own size
        expect(norm.x).toBeCloseTo(370, 6)
        expect(norm.y).toBeCloseTo(610, 6)
        const expected = { x: Math.round(d.x + fx * d.width), y: Math.round(d.y + fy * d.height) }
        expect(normToPoints(norm, d)).toEqual(expected)
        const r = rig({ display: d, scale })
        await r.actuator.clickAt(norm, { target: TEXTEDIT })
        expect(r.windowReads).toEqual([expected, expected]) // the hit test, the second look and the click all use the same point
        expect(r.osascript).toHaveBeenCalledWith(['-e', `tell application "System Events" to click at {${expected.x}, ${expected.y}}`])
      }
      expect(rig({ display: d, scale }).actuator.displayInfo?.()).toEqual({ width: d.width, height: d.height, scaleFactor: scale })
      // the inverse round trip (the Accessibility frame of an element, in points, back to the 0-1000 space)
      const p = { x: d.x + 0.25 * d.width, y: d.y + 0.75 * d.height }
      expect(pointsToNorm(p, d)).toEqual({ x: 250, y: 750 })
    })
  }

  it('a screenshot of the wrong shape does not map onto the display (another display, a crop): refused by shape', () => {
    expect(aspectMatches({ widthPx: 3456, heightPx: 2234 }, DISPLAY)).toBe(true)
    expect(aspectMatches({ widthPx: 1920, heightPx: 1241 }, DISPLAY)).toBe(true)
    expect(aspectMatches({ widthPx: 1920, heightPx: 1080 }, DISPLAY)).toBe(false) // a 16:9 display's capture
    expect(aspectMatches({ widthPx: 1920, heightPx: 600 }, DISPLAY)).toBe(false) // a crop
    expect(aspectMatches({ widthPx: 0, heightPx: 10 }, DISPLAY)).toBe(false)
  })
})

describe('probe helpers', () => {
  it('parses the window server answer (owner and layer only) and rejects anything else', () => {
    expect(parseWindowHit('{"owner":"TextEdit","layer":0}\n')).toEqual({ owner: 'TextEdit', layer: 0 })
    expect(parseWindowHit('{"owner":"TextEdit","layer":0,"id":412,"pid":903}')).toEqual({ owner: 'TextEdit', layer: 0, windowId: 412, pid: 903 })
    expect(parseWindowHit('null')).toBeNull()
    expect(parseWindowHit('')).toBeNull()
    expect(parseWindowHit('{"owner":"","layer":0}')).toBeNull()
    expect(parseWindowHit('{"owner":"X"}')).toBeNull()
  })
})

describe('S-05: the WINDOW the task started in, not just the app (REVIEW-SAFETY)', () => {
  const personal = { owner: 'TextEdit', layer: 0, windowId: 99, pid: 100 } // another document of the same app, on top
  it('a click whose topmost window is another window of the same app is refused', async () => {
    const r = rig({ hit: () => personal })
    expect(await r.actuator.clickAt({ x: 500, y: 500 }, { target: TEXTEDIT })).toMatchObject({ ok: false, reason: 'blocked', detail: expect.stringMatching(/not the one this task started in/) })
    expect(r.osascript).not.toHaveBeenCalled()
  })

  it('the same window number under a different pid is refused too (a recycled number)', async () => {
    const r = rig({ hit: () => ({ owner: 'TextEdit', layer: 0, windowId: 7, pid: 555 }) })
    expect(await r.actuator.clickAt({ x: 500, y: 500 }, { target: TEXTEDIT })).toMatchObject({ ok: false, reason: 'blocked' })
  })

  it('a probe that cannot name the window number never matches', async () => {
    const r = rig({ hit: () => ({ owner: 'TextEdit', layer: 0 }) })
    expect(await r.actuator.clickAt({ x: 500, y: 500 }, { target: TEXTEDIT })).toMatchObject({ ok: false, reason: 'blocked' })
  })

  it('an unpinned target is refused in real mode: no window was pinned, so none is guessed', async () => {
    const r = rig()
    expect(await r.actuator.clickAt({ x: 500, y: 500 }, { target: { app: 'TextEdit' } })).toMatchObject({ ok: false, reason: 'blocked', detail: expect.stringMatching(/no window was pinned/) })
    expect(await r.actuator.typeText('hi', { target: { app: 'TextEdit' } })).toMatchObject({ ok: false, reason: 'blocked' })
  })

  it('typing follows the window: when another window of the app comes to the front mid-text, the next chunk is refused and the count says how far it got', async () => {
    let front = { owner: 'TextEdit', layer: 0, windowId: 7, pid: 100 }
    const r = rig({ front: null })
    // a rig whose front window changes after the second chunk
    let chunks = 0
    const actuator = createActuator({
      platform: 'darwin',
      dryRun: false,
      isTrusted: () => true,
      displayBounds: () => DISPLAY,
      probe: { frontmostApp: async () => 'TextEdit', topWindowAt: async () => front, frontWindow: async () => front },
      osascript: async () => {
        chunks += 1
        if (chunks === 2) front = { owner: 'TextEdit', layer: 0, windowId: 99, pid: 100 }
      },
      killFileExists: () => false,
      sleep: async () => undefined,
    })
    const out = await actuator.typeText('abcdefghijklmnopqrstuvwxyz', { target: TEXTEDIT })
    expect(out).toMatchObject({ ok: false, reason: 'blocked', detail: expect.stringMatching(/typed 12 of 26 characters/) })
    expect(chunks).toBe(2) // two chunks of six went in; the third was refused before it was sent
    void r
  })

  it('pinTarget records the front window of the target app, and refuses when another app is in front or the desktop cannot be read', async () => {
    const r = rig({ front: { owner: 'TextEdit', layer: 0, windowId: 412, pid: 903 } })
    expect(await r.actuator.pinTarget!({ app: 'TextEdit' })).toEqual({ ok: true, target: { app: 'TextEdit', window: { id: 412, pid: 903, owner: 'TextEdit' } } })
    const browser = rig({ front: { owner: 'Google Chrome', layer: 0, windowId: 5, pid: 77 } })
    expect(await browser.actuator.pinTarget!({ browser: true })).toMatchObject({ ok: true, target: { browser: true, window: { id: 5, pid: 77 } } })
    expect(await rig({ front: { owner: 'Calculator', layer: 0, windowId: 5, pid: 77 } }).actuator.pinTarget!({ app: 'TextEdit' })).toMatchObject({ ok: false })
    expect(await rig({ front: null }).actuator.pinTarget!({ app: 'TextEdit' })).toMatchObject({ ok: false })
    expect(await rig({ dryRun: true }).actuator.pinTarget!({ app: 'TextEdit' })).toEqual({ ok: true, target: { app: 'TextEdit' } }) // a dry run reads nothing
  })
})

describe('S-03: a Stop in the middle of an action ends it (REVIEW-SAFETY)', () => {
  const make = (over: Partial<Parameters<typeof createActuator>[0]> = {}) => {
    const typed: string[] = []
    const actuator = createActuator({
      platform: 'darwin',
      dryRun: false,
      isTrusted: () => true,
      displayBounds: () => DISPLAY,
      probe: { frontmostApp: async () => 'TextEdit', topWindowAt: async () => ({ owner: 'TextEdit', layer: 0, windowId: 7, pid: 100 }), frontWindow: async () => ({ owner: 'TextEdit', layer: 0, windowId: 7, pid: 100 }) },
      osascript: async (args) => void typed.push(args[args.length - 1]!),
      killFileExists: () => false,
      sleep: async () => undefined,
      ...over,
    })
    return { actuator, typed }
  }

  it('typing is in chunks of at most six characters', async () => {
    const { actuator, typed } = make()
    await actuator.typeText('x'.repeat(120), { target: TEXTEDIT })
    expect(typed.length).toBe(20)
    expect(Math.max(...typed.map((t) => t.length))).toBeLessThanOrEqual(6)
  })

  it('the caller\'s cancelled() is looked at before every chunk: a Stop during the second chunk types no more than three', async () => {
    let stopped = false
    const typed: string[] = []
    const { actuator } = make({
      osascript: async (args) => {
        typed.push(args[args.length - 1]!)
        if (typed.length >= 2) stopped = true // the person presses Stop during the 2nd chunk
      },
    })
    const out = await actuator.typeText('x'.repeat(120), { target: TEXTEDIT, cancelled: () => stopped })
    expect(typed.length).toBeLessThanOrEqual(3)
    expect(out).toMatchObject({ ok: false, reason: 'blocked', detail: expect.stringMatching(/stopped; typed 12 of 120/) })
  })

  it('the kill flag and the data/KILL file stop the typing between chunks, and a click right before it is sent', async () => {
    let file = false
    const typed: string[] = []
    const { actuator } = make({
      osascript: async (args) => {
        typed.push(args[args.length - 1]!)
        if (typed.length === 2) file = true // a separate process writes data/KILL
      },
      killFileExists: () => file,
    })
    expect(await actuator.typeText('y'.repeat(60), { target: TEXTEDIT })).toMatchObject({ ok: false, detail: expect.stringMatching(/kill switch is on; typed 12/) })
    expect(typed.length).toBe(2)
    const clicker = make({ killFileExists: () => true })
    expect(await clicker.actuator.clickAt({ x: 500, y: 500 }, { target: TEXTEDIT })).toMatchObject({ ok: false, detail: 'the kill switch is on' })
    expect(await make().actuator.clickAt({ x: 500, y: 500 }, { target: TEXTEDIT, cancelled: () => true })).toMatchObject({ ok: false, detail: 'the run was stopped' })
  })

  it('abortInFlightInput reports how many scripts it ended (none when nothing runs)', async () => {
    const { abortInFlightInput } = await import('./index')
    expect(abortInFlightInput()).toBe(0)
  })
})

describe('pasteText never destroys a clipboard that is not text', () => {
  it('refuses when the clipboard holds an image or files, and pastes (concealed, then restored) when it holds text or nothing', async () => {
    const events: string[] = []
    const make = (kind: 'empty' | 'text' | 'other') =>
      createActuator({
        platform: 'darwin',
        dryRun: false,
        isTrusted: () => true,
        displayBounds: () => DISPLAY,
        probe: { frontmostApp: async () => 'TextEdit', topWindowAt: async () => ({ owner: 'TextEdit', layer: 0, windowId: 7, pid: 100 }), frontWindow: async () => ({ owner: 'TextEdit', layer: 0, windowId: 7, pid: 100 }) },
        osascript: async () => void events.push('paste'),
        readClipboard: async () => 'before',
        writeClipboard: async (t) => void events.push(`write ${t}`),
        clipboardKind: async () => kind,
        killFileExists: () => false,
        sleep: async () => undefined,
      })
    expect(await make('other').pasteText!('hello', { target: TEXTEDIT })).toMatchObject({ ok: false, reason: 'blocked', detail: expect.stringMatching(/image or files/) })
    expect(events).toEqual([]) // nothing was written, nothing pressed
    expect(await make('text').pasteText!('hello', { target: TEXTEDIT })).toEqual({ ok: true })
    expect(events).toEqual(['write hello', 'paste', 'write before'])
    events.length = 0
    expect(await make('empty').pasteText!('hi', { target: TEXTEDIT })).toEqual({ ok: true })
  })
})
