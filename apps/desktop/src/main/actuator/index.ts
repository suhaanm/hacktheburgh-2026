// The actuator: every real action Alongside can take on the learner's computer goes through this ONE object.
//   Tier 1 (no Accessibility needed): openUrl, openApp, revealPath, openSettingsPane.
//   Tier 2 (needs macOS Accessibility, checked with isTrustedAccessibilityClient(false), which never prompts):
//   clickAt, typeText, pressKeys, scroll, via osascript.
// It is a primitive layer: WHETHER to act (settings, approvals, denylist, scam context, Stop) is decided by the callers
// (do_it_for_me in ./flow.ts, AGENCY's policy engine). Everything is validated against allowlists here as defence in depth;
// nothing the model or the screen produced is interpolated into script source.
// ALONGSIDE_ACTUATOR_DRYRUN=1 validates, logs every call and performs nothing (returns {ok:true, reason:'dry-run'}).
//
// THE TARGET GUARD (real mode only; a dry run never touches the desktop). A supervised check of another actuator clicked into the
// wrong app (a scale error and no hit test), so every action that touches the keyboard or the pointer proves where it will land:
//   - it must NAME the app the task is about (`target`): without one it is refused, never guessed;
//   - a click or scroll first asks the window server which window is topmost at that very point and refuses unless it belongs
//     to the target app (a window of another app over the target, a terminal, the assistant's own app, the menu bar: refused);
//   - typing, keys and paste first wait for the target app to be frontmost and VERIFY it (one attempt to bring it back, then
//     refused), because keystrokes go to whatever has focus;
//   - an unreadable answer is a refusal. Nothing here fails open.
// Pixels never reach this layer: callers pass a point normalised to the display (0-1000), converted to points with the display's
// own bounds (retina is already folded in), and the act_for_me loop refuses a screenshot whose shape does not match the display.
// electron is imported lazily so unit tests need no Electron.
import { execFile } from 'node:child_process'
import { existsSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import type { NormPoint } from '../../shared/protocol'
import { isKilled } from '../kill-flag'
import { isBrowser, isNeverActApp, isOwnApp, readFrontApp } from '../agency/scope'
import { isValidNormPoint, normToPoints, type DisplayBounds } from './mapping'
import { checkAppName, checkKeyCombo, checkScrollDelta, checkSettingsPane, checkTypedText, checkUrl, type SettingsPane } from './validate'

export type { SettingsPane } from './validate'

export interface ActResult {
  ok: boolean
  // accessibility: macOS Accessibility not granted. blocked: refused by an allowlist/validation. dry-run: ok, but nothing was done.
  // failed: the OS call failed (app not found, script error, unsupported platform).
  reason?: 'accessibility' | 'blocked' | 'dry-run' | 'failed'
  detail?: string
}

// The app an action is about. `{ browser: true }` = any browser (a web task).
export type ActTarget = { app: string } | { browser: true }
export interface ActOpts {
  target?: ActTarget
}

// The topmost window at a point, as the window server sees it (owner only; never titles or contents).
export interface WindowHit {
  owner: string
  layer: number
}
export interface DesktopProbe {
  // The app that has the keyboard focus, or null when it cannot be read.
  frontmostApp(): Promise<string | null>
  // The topmost window that would receive a click at this global point (our own click-through overlay is skipped), or null when unreadable.
  topWindowAt(p: { x: number; y: number }): Promise<WindowHit | null>
}

export interface Actuator {
  status(): { accessibility: boolean; dryRun: boolean }
  // The primary display as the actuator maps it: size in points and its scale factor. Null when unknown.
  displayInfo?(): { width: number; height: number; scaleFactor: number } | null
  // True when a click/type/key action could run right now (Accessibility granted, or dry run).
  canClick(): boolean
  openUrl(url: string): Promise<ActResult>
  openApp(name: string): Promise<ActResult>
  revealPath(path: string): Promise<ActResult>
  openSettingsPane(pane: SettingsPane): Promise<ActResult>
  // One left click, or a double click when `double` is set (two clicks in one script: the OS decides if it counts as double).
  clickAt(p: NormPoint, opts?: { double?: boolean } & ActOpts): Promise<ActResult>
  // Types plain text (max 300 chars, no control characters) into whatever has focus (verified to be the target app first).
  typeText(text: string, opts?: ActOpts): Promise<ActResult>
  // Allowlist only: return, tab, escape, space, arrows, cmd+l/t/w/v/c/a/f.
  pressKeys(combo: string, opts?: ActOpts): Promise<ActResult>
  // Fallback for typeText: puts the text on the clipboard, presses Cmd+V, then restores the previous clipboard text.
  pasteText?(text: string, opts?: ActOpts): Promise<ActResult>
  // Scrolls the window under `p`; dy > 0 reads further down, dy < 0 back up (lines, 1-50).
  scroll(p: NormPoint, dy: number, opts?: ActOpts): Promise<ActResult>
}

export interface ActuatorDeps {
  log?: (scope: string, ...args: unknown[]) => void
  dryRun?: boolean
  platform?: NodeJS.Platform
  isTrusted?: () => boolean
  displayBounds?: () => DisplayBounds
  // The primary display's scale factor (screen.getPrimaryDisplay().scaleFactor); only reported through displayInfo().
  scaleFactor?: () => number
  // How the desktop is probed for the target guard; the default asks lsappinfo and the window server through osascript.
  probe?: DesktopProbe
  // The pid of this process and the display size, so the default probe can skip our own click-through overlay.
  ownPid?: number
  // How long typing waits for the target app to take the focus, and how often it looks.
  focusTimeoutMs?: number
  focusPollMs?: number
  sleep?: (ms: number) => Promise<void>
  // Runs /usr/bin/osascript with exactly these arguments; rejects on failure.
  osascript?: (args: string[]) => Promise<void>
  // Runs `open -a <name>`; rejects on failure.
  openAppProcess?: (name: string) => Promise<void>
  // Clipboard text access for pasteText (pbpaste / pbcopy); tests inject fakes.
  readClipboard?: () => Promise<string>
  writeClipboard?: (text: string) => Promise<void>
  openExternal?: (url: string) => Promise<void>
  showItemInFolder?: (path: string) => void
  exists?: (path: string) => boolean
  homedir?: string
}

// Understudy: SIMULATED BY DEFAULT. Real clicks, keystrokes, scrolls (and app/URL opens through the actuator) run only when
// UNDERSTUDY_REAL_ACTUATOR=1 is set AND ALONGSIDE_ACTUATOR_DRYRUN is not '1'. Spike S2 (owner present) has not passed; do not set it.
export const dryRunFromEnv = (): boolean => process.env.ALONGSIDE_ACTUATOR_DRYRUN === '1' || process.env.UNDERSTUDY_REAL_ACTUATOR !== '1'

export function clickScript(x: number, y: number, double = false): string[] {
  const line = `click at {${Math.round(x)}, ${Math.round(y)}}`
  return double ? ['-e', 'tell application "System Events"', '-e', line, '-e', line, '-e', 'end tell'] : ['-e', `tell application "System Events" to ${line}`]
}

// Typed text is passed as an osascript ARGUMENT (after `--`), read inside the script as `item 1 of argv`: it is data, so
// quotes, backslashes, newlines and AppleScript-looking text cannot change what the script does.
export function typeScript(text: string): string[] {
  return ['-e', 'on run argv', '-e', 'tell application "System Events" to keystroke (item 1 of argv)', '-e', 'end run', '--', text]
}

// JXA (no System Events verb scrolls): move the pointer, then post one scroll-wheel event. Numbers arrive as argv.
const SCROLL_JXA = `ObjC.import('CoreGraphics');
function run(argv) {
  var x = Number(argv[0]), y = Number(argv[1]), lines = Number(argv[2]);
  $.CGWarpMouseCursorPosition({ x: x, y: y });
  var ev = $.CGEventCreateScrollWheelEvent(null, $.kCGScrollEventUnitLine, 1, lines);
  $.CGEventPost($.kCGHIDEventTap, ev);
}`
export function scrollScript(x: number, y: number, lines: number): string[] {
  // CGEvent: positive = wheel up. Our dy > 0 means "read further down", so the sign is flipped.
  return ['-l', 'JavaScript', '-e', SCROLL_JXA, '--', String(Math.round(x)), String(Math.round(y)), String(-lines)]
}

const runOsascript = (args: string[]): Promise<void> =>
  new Promise((resolve, reject) => {
    execFile('/usr/bin/osascript', args, { timeout: 8000 }, (err, _stdout, stderr) => (err ? reject(new Error(stderr.trim() || err.message)) : resolve()))
  })

const runOpenApp = (name: string): Promise<void> =>
  new Promise((resolve, reject) => {
    // Argument array, no shell. The name was validated and cannot start with "-".
    execFile('/usr/bin/open', ['-a', name], { timeout: 8000 }, (err, _stdout, stderr) => (err ? reject(new Error(stderr.trim() || err.message)) : resolve()))
  })

// Demo only (ALONGSIDE_BROWSER_APP): open web addresses in one named browser instead of the system default.
const runOpenUrlIn = (app: string, url: string): Promise<void> =>
  new Promise((resolve, reject) => {
    execFile('/usr/bin/open', ['-a', app, url], { timeout: 8000 }, (err, _stdout, stderr) => (err ? reject(new Error(stderr.trim() || err.message)) : resolve()))
  })

const runClipboardRead = (): Promise<string> =>
  new Promise((resolve) => {
    execFile('/usr/bin/pbpaste', [], { timeout: 3000, maxBuffer: 1 << 20 }, (err, stdout) => resolve(err ? '' : String(stdout)))
  })

// The text goes in on stdin: it is data, never part of a command line.
const runClipboardWrite = (text: string): Promise<void> =>
  new Promise((resolve, reject) => {
    const child = execFile('/usr/bin/pbcopy', [], { timeout: 3000 }, (err) => (err ? reject(new Error(err.message)) : resolve()))
    child.stdin?.end(text)
  })

// JXA: the topmost window under a global point, front to back from the window server's list. Full-display windows of this process
// (the click-through overlay) and of the Dock and the window server (transparent layers) are skipped. Prints one JSON line (owner,
// layer) or null. Owner names only: no titles.
const WINDOW_AT_JXA = `ObjC.import('CoreGraphics');
function run(argv) {
  var x = Number(argv[0]), y = Number(argv[1]), ownPid = Number(argv[2]), dw = Number(argv[3]), dh = Number(argv[4]);
  var list = ObjC.deepUnwrap(ObjC.castRefToObject($.CGWindowListCopyWindowInfo($.kCGWindowListOptionOnScreenOnly | $.kCGWindowListExcludeDesktopElements, $.kCGNullWindowID)));
  for (var i = 0; i < list.length; i++) {
    var w = list[i], b = w.kCGWindowBounds;
    if (!b || w.kCGWindowAlpha === 0) continue;
    if (x < b.X || x >= b.X + b.Width || y < b.Y || y >= b.Y + b.Height) continue;
    // Click-through furniture that covers the whole display: our own overlay, and the Dock's and the window server's full-screen layers.
    var name = String(w.kCGWindowOwnerName);
    if ((w.kCGWindowOwnerPID === ownPid || name === 'Dock' || name === 'Window Server') && b.Width >= dw - 2 && b.Height >= dh - 2) continue;
    return JSON.stringify({ owner: String(w.kCGWindowOwnerName), layer: Number(w.kCGWindowLayer) });
  }
  return 'null';
}`

export function parseWindowHit(out: string): WindowHit | null {
  try {
    const j = JSON.parse(out.trim()) as { owner?: unknown; layer?: unknown } | null
    return j && typeof j.owner === 'string' && j.owner.trim() && typeof j.layer === 'number' ? { owner: j.owner.trim().slice(0, 80), layer: j.layer } : null
  } catch {
    return null
  }
}

/** May an action aimed at `target` land in a window owned by `owner`? The assistant's own app and terminals never count. */
export function ownerMatchesTarget(owner: string, target: ActTarget): boolean {
  if (isNeverActApp(owner)) return false
  return 'browser' in target ? isBrowser(owner) : owner.trim().toLowerCase() === target.app.trim().toLowerCase()
}

function defaultProbe(ownPid: number, display: () => { width: number; height: number }): DesktopProbe {
  return {
    frontmostApp: () => readFrontApp().catch(() => null),
    topWindowAt: (p) =>
      new Promise((resolve) => {
        const d = display()
        execFile('/usr/bin/osascript', ['-l', 'JavaScript', '-e', WINDOW_AT_JXA, '--', String(Math.round(p.x)), String(Math.round(p.y)), String(ownPid), String(d.width), String(d.height)], { timeout: 2000, killSignal: 'SIGKILL' }, (err, stdout) => resolve(err ? null : parseWindowHit(String(stdout))))
      }),
  }
}

let electronApi: Promise<typeof import('electron')> | null = null
const electron = (): Promise<typeof import('electron')> => (electronApi ??= import('electron'))

const message = (err: unknown): string => (err instanceof Error ? err.message : String(err))

export function createActuator(deps: ActuatorDeps = {}): Actuator {
  const log = deps.log ?? (() => undefined)
  const dryRun = deps.dryRun ?? dryRunFromEnv()
  const platform = deps.platform ?? process.platform
  const osascript = deps.osascript ?? runOsascript
  const openAppProcess = deps.openAppProcess ?? runOpenApp
  const readClipboard = deps.readClipboard ?? runClipboardRead
  const writeClipboard = deps.writeClipboard ?? runClipboardWrite
  const exists = deps.exists ?? existsSync
  const home = deps.homedir ?? os.homedir()
  const sleep = deps.sleep ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)))
  const focusTimeout = deps.focusTimeoutMs ?? 1500
  const focusPoll = deps.focusPollMs ?? 100
  let scale = deps.scaleFactor
  let trusted = deps.isTrusted
  let bounds = deps.displayBounds
  let openExternal = deps.openExternal
  let showItemInFolder = deps.showItemInFolder
  if (!trusted || !bounds || !scale || !openExternal || !showItemInFolder) {
    void electron()
      .then(({ systemPreferences, screen, shell }) => {
        trusted ??= () => platform === 'darwin' && systemPreferences.isTrustedAccessibilityClient(false)
        bounds ??= () => screen.getPrimaryDisplay().bounds
        scale ??= () => screen.getPrimaryDisplay().scaleFactor
        openExternal ??= (url) => shell.openExternal(url)
        showItemInFolder ??= (p) => shell.showItemInFolder(p)
      })
      .catch(() => undefined)
  }

  const blocked = (detail: string): ActResult => ({ ok: false, reason: 'blocked', detail })
  const probe = deps.probe ?? defaultProbe(deps.ownPid ?? process.pid, () => ({ width: bounds?.().width ?? 0, height: bounds?.().height ?? 0 }))

  // ---- the target guard ----
  const refuseNeverActTarget = (target: ActTarget): string | null => ('app' in target && isNeverActApp(target.app) ? `I never act in ${target.app}` : null)
  // Where will a click or scroll at this point really land? Only the target app's own window passes.
  const guardPoint = async (target: ActTarget | undefined, at: { x: number; y: number }): Promise<string | null> => {
    if (!target) return 'no app was named for this action, so I will not guess where it lands'
    const never = refuseNeverActTarget(target)
    if (never) return never
    let hit: WindowHit | null = null
    try {
      hit = await probe.topWindowAt(at)
    } catch {
      hit = null
    }
    if (!hit) return 'I could not tell which window is under that point'
    if (!ownerMatchesTarget(hit.owner, target)) return `the window under that point belongs to ${hit.owner}, not to ${'browser' in target ? 'a browser' : target.app}`
    return null
  }
  // Keystrokes go to whatever has focus: wait for the target app to be frontmost and verify it, trying once to bring it back.
  const guardFocus = async (target: ActTarget | undefined): Promise<string | null> => {
    if (!target) return 'no app was named for this action, so I will not guess where it goes'
    const never = refuseNeverActTarget(target)
    if (never) return never
    const readFront = async (): Promise<string | null> => {
      try {
        return await probe.frontmostApp()
      } catch {
        return null
      }
    }
    const ok = (front: string | null): front is string => !!front && ownerMatchesTarget(front, target)
    let front = await readFront()
    if (ok(front)) return null
    // Not there yet. If the assistant's own window took the focus (the approval prompt), ask the target app to come forward once;
    // if some other app is in front, do not fight the person for the focus: wait a moment in case it is settling, then refuse.
    if ('app' in target && platform === 'darwin' && front && isOwnApp(front)) {
      const asked = checkAppName(target.app)
      if (asked.ok) await openAppProcess(asked.value).catch(() => undefined)
    }
    for (let waited = 0; waited < focusTimeout; waited += focusPoll) {
      await sleep(focusPoll)
      front = await readFront()
      if (ok(front)) return null
    }
    return front ? `${front} has the focus, not ${'browser' in target ? 'a browser' : target.app}` : 'I could not tell which app has the focus'
  }
  const dry = (what: string): ActResult => {
    log('actuator', `DRYRUN ${what} (not performed)`)
    return { ok: true, reason: 'dry-run', detail: what }
  }
  // Tier 2 gate: macOS only, Accessibility granted. Dry run skips it because nothing is performed.
  const tier2 = (): ActResult | null => {
    if (platform !== 'darwin') return { ok: false, reason: 'failed', detail: 'this action is implemented for macOS only' }
    return trusted?.() ? null : { ok: false, reason: 'accessibility' }
  }
  const act = async (what: string, run: () => Promise<void> | void, needsAccessibility: boolean, guard?: { target: ActTarget | undefined; at?: { x: number; y: number } }): Promise<ActResult> => {
    // Understudy: while the global kill switch is on, nothing runs, not even a dry run.
    if (isKilled()) return blocked('the kill switch is on')
    if (dryRun) return dry(what)
    if (needsAccessibility) {
      const gate = tier2()
      if (gate) return gate
      // Real input proves where it will land first. No target, an unreadable desktop or a different app is a refusal.
      const why = guard ? (guard.at ? await guardPoint(guard.target, guard.at) : await guardFocus(guard.target)) : 'this action has no target guard'
      if (why) {
        log('actuator', `REFUSED ${what}: ${why}`)
        return blocked(why)
      }
      if (isKilled()) return blocked('the kill switch is on') // the switch may have been pressed while the desktop was being read
    }
    try {
      await run()
      log('actuator', what)
      return { ok: true }
    } catch (err) {
      return { ok: false, reason: 'failed', detail: message(err) }
    }
  }

  const point = (p: NormPoint): { x: number; y: number } | ActResult => {
    if (!isValidNormPoint(p)) return blocked('the point is outside the display')
    const b = bounds?.()
    if (!b) return { ok: false, reason: 'failed', detail: 'display bounds unavailable' }
    return normToPoints(p, b)
  }
  const isResult = (v: { x: number; y: number } | ActResult): v is ActResult => 'ok' in v

  return {
    status: () => ({ accessibility: platform === 'darwin' && (trusted?.() ?? false), dryRun }),
    displayInfo() {
      const b = bounds?.()
      const f = scale?.()
      return b && f && b.width > 0 && b.height > 0 ? { width: b.width, height: b.height, scaleFactor: f } : null
    },
    canClick: () => dryRun || (platform === 'darwin' && (trusted?.() ?? false)),

    async openUrl(url) {
      const c = checkUrl(url)
      if (!c.ok) return blocked(c.detail)
      const browser = platform === 'darwin' ? checkAppName(process.env.ALONGSIDE_BROWSER_APP ?? '') : null
      if (browser?.ok) return act(`openUrl ${c.value} in ${browser.value}`, () => runOpenUrlIn(browser.value, c.value), false)
      return act(`openUrl ${c.value}`, () => openExternal?.(c.value) ?? Promise.reject(new Error('openExternal unavailable')), false)
    },

    async openApp(name) {
      const c = checkAppName(name)
      if (!c.ok) return blocked(c.detail)
      if (platform !== 'darwin' && !dryRun) return { ok: false, reason: 'failed', detail: 'opening apps by name is implemented for macOS only' }
      return act(`openApp ${c.value}`, () => openAppProcess(c.value), false)
    },

    async revealPath(p) {
      if (typeof p !== 'string' || p.length === 0 || p.length > 1024 || p.includes('\0')) return blocked('the path is empty, too long or invalid')
      const expanded = p.startsWith('~/') ? path.join(home, p.slice(2)) : p
      if (!path.isAbsolute(expanded)) return blocked('an absolute path (or one starting with ~/) is needed')
      const resolved = path.resolve(expanded)
      if (!exists(resolved)) return { ok: false, reason: 'failed', detail: 'that file or folder does not exist' }
      return act(`revealPath ${resolved}`, () => showItemInFolder?.(resolved), false)
    },

    async openSettingsPane(pane) {
      const c = checkSettingsPane(pane)
      if (!c.ok) return blocked(c.detail)
      return act(`openSettingsPane ${pane}`, () => openExternal?.(c.value) ?? Promise.reject(new Error('openExternal unavailable')), false)
    },

    async clickAt(p, opts = {}) {
      const at = point(p)
      if (isResult(at)) return at
      const double = opts.double === true
      return act(`${double ? 'double ' : ''}click at ${at.x},${at.y}`, () => osascript(clickScript(at.x, at.y, double)), true, { target: opts.target, at })
    },

    async typeText(text, opts = {}) {
      const c = checkTypedText(text)
      if (!c.ok) return blocked(c.detail)
      // The log line carries the length only: typed text can be personal.
      return act(`typeText (${c.value.length} characters)`, () => osascript(typeScript(c.value)), true, { target: opts.target })
    },

    async pasteText(text, opts = {}) {
      const c = checkTypedText(text)
      if (!c.ok) return blocked(c.detail)
      const keys = checkKeyCombo('cmd+v')
      if (!keys.ok) return blocked(keys.detail)
      const statement = keys.value.statement
      return act(
        `pasteText (${c.value.length} characters)`,
        async () => {
          const previous = await readClipboard()
          await writeClipboard(c.value)
          try {
            await osascript(['-e', statement])
            // Give the target app a moment to read the clipboard before it is put back.
            await new Promise((r) => setTimeout(r, 250))
          } finally {
            await writeClipboard(previous).catch(() => undefined)
          }
        },
        true,
        { target: opts.target },
      )
    },

    async pressKeys(combo, opts = {}) {
      const c = checkKeyCombo(combo)
      if (!c.ok) return blocked(c.detail)
      return act(`pressKeys ${c.value.canonical}`, () => osascript(['-e', c.value.statement]), true, { target: opts.target })
    },

    async scroll(p, dy, opts = {}) {
      const lines = checkScrollDelta(dy)
      if (!lines.ok) return blocked(lines.detail)
      const at = point(p)
      if (isResult(at)) return at
      return act(`scroll ${lines.value} lines at ${at.x},${at.y}`, () => osascript(scrollScript(at.x, at.y, lines.value)), true, { target: opts.target, at })
    },
  }
}
