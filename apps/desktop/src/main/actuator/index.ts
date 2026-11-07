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
// WINDOW, not just app (S-05): the app name alone lets a second window of the same app (the owner's own browser window, another
// document) pass. At the start of a task the caller PINS the target window (`pinTarget`: the topmost normal window of the target app,
// its window number and pid). Every click, scroll, key and typed chunk then requires the window under the point (or the front window,
// for keystrokes) to be that very window; if it changes the action is refused and says so. An unpinned target is refused in real mode.
// STOP (S-03): typing goes in chunks of at most 6 characters, each re-verified and each preceded by a look at the kill flag, the
// data/KILL file and the caller's `cancelled()`; the osascript child in flight is killed by `abortInFlightInput()` (the kill switch calls it).
// CLIPBOARD (pasteText): a clipboard that holds anything but text (an image, files) is never overwritten: the paste is refused; the
// pasted text is marked concealed so clipboard managers skip it, and the previous text is put back.
// Pixels never reach this layer: callers pass a point normalised to the display (0-1000), converted to points with the display's
// own bounds (retina is already folded in), and the act_for_me loop refuses a screenshot whose shape does not match the display.
// electron is imported lazily so unit tests need no Electron.
import { execFile, type ChildProcess } from 'node:child_process'
import { existsSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import type { NormPoint } from '../../shared/protocol'
import { isKilled } from '../kill-flag'
import { killFileExists } from '../kill-file'
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
// The window a task started in (see the header): its window number and the pid of its owner.
export interface PinnedWindow {
  id: number
  pid: number
  owner: string
}
export type ActTarget = { app: string; window?: PinnedWindow } | { browser: true; window?: PinnedWindow }
export interface ActOpts {
  target?: ActTarget
  // The caller's Stop, yield or kill: looked at before each click and before each typed chunk.
  cancelled?: () => boolean
}

// The topmost window at a point, as the window server sees it (owner, window number and pid; never titles or contents).
export interface WindowHit {
  owner: string
  layer: number
  windowId?: number
  pid?: number
}
export interface DesktopProbe {
  // The app that has the keyboard focus, or null when it cannot be read.
  frontmostApp(): Promise<string | null>
  // The topmost window that would receive a click at this global point (our own click-through overlay is skipped), or null when unreadable.
  topWindowAt(p: { x: number; y: number }): Promise<WindowHit | null>
  // The topmost normal window on the screen (the one that has the keyboard), or null when unreadable. Used to pin and to verify keystrokes.
  frontWindow?(): Promise<WindowHit | null>
}

export interface Actuator {
  status(): { accessibility: boolean; dryRun: boolean }
  // Pins the window a task starts in: the topmost normal window of the target app. Returns the target with `window` filled in. In a dry
  // run nothing is read and the target comes back as it was. A refusal says why (another app is in front, the desktop cannot be read).
  pinTarget?(target: ActTarget): Promise<{ ok: true; target: ActTarget } | { ok: false; detail: string }>
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
  // What the clipboard holds: nothing, text only, or something else (an image, files). Anything else is never overwritten.
  clipboardKind?: () => Promise<'empty' | 'text' | 'other'>
  // Writes text as concealed (clipboard managers skip it). Default: pbcopy via a script that adds org.nspasteboard.ConcealedType.
  writeClipboard?: (text: string) => Promise<void>
  // Does data/KILL exist? Default: the real file (never the shared one under a unit test).
  killFileExists?: () => boolean
  // The longest run of characters typed in one keystroke script (default 6).
  typeChunk?: number
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
    const child = execFile('/usr/bin/osascript', args, { timeout: 8000, killSignal: 'SIGKILL' }, (err, _stdout, stderr) => {
      inFlight.delete(child)
      err ? reject(new Error(stderr.trim() || err.message)) : resolve()
    })
    inFlight.add(child)
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

// The text goes in as an argument to a JXA script (data, never part of the script): it is written as plain text AND flagged concealed
// (org.nspasteboard.ConcealedType), the convention clipboard managers honour, so what is pasted does not land in a history.
const CLIPBOARD_WRITE_JXA = `ObjC.import('AppKit');
function run(argv) {
  var pb = $.NSPasteboard.generalPasteboard;
  pb.clearContents;
  pb.declareTypesOwner($(['public.utf8-plain-text', 'org.nspasteboard.ConcealedType']), null);
  pb.setStringForType($(argv[0]), 'public.utf8-plain-text');
  pb.setStringForType($(''), 'org.nspasteboard.ConcealedType');
}`
const runClipboardWrite = (text: string): Promise<void> =>
  new Promise((resolve, reject) => {
    execFile('/usr/bin/osascript', ['-l', 'JavaScript', '-e', CLIPBOARD_WRITE_JXA, '--', text], { timeout: 3000 }, (err) => (err ? reject(new Error(err.message)) : resolve()))
  })
// Types only (never contents): is the clipboard empty, text, or something a text write would destroy?
const CLIPBOARD_KIND_JXA = `ObjC.import('AppKit');
function run() {
  var t = ObjC.deepUnwrap($.NSPasteboard.generalPasteboard.types) || [];
  if (t.length === 0) return 'empty';
  var texty = function (x) { return x === 'public.utf8-plain-text' || x === 'NSStringPboardType' || x === 'public.utf16-plain-text' || x === 'org.nspasteboard.ConcealedType' || x === 'org.nspasteboard.TransientType' || x === 'org.nspasteboard.source' || x.indexOf('dyn.') === 0; };
  return t.every(texty) ? 'text' : 'other';
}`
const runClipboardKind = (): Promise<'empty' | 'text' | 'other'> =>
  new Promise((resolve) => {
    execFile('/usr/bin/osascript', ['-l', 'JavaScript', '-e', CLIPBOARD_KIND_JXA], { timeout: 3000 }, (err, stdout) => {
      const out = String(stdout).trim()
      resolve(err ? 'other' : out === 'empty' ? 'empty' : out === 'text' ? 'text' : 'other') // unreadable counts as "other": never overwrite what cannot be read
    })
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
    return JSON.stringify({ owner: String(w.kCGWindowOwnerName), layer: Number(w.kCGWindowLayer), id: Number(w.kCGWindowNumber), pid: Number(w.kCGWindowOwnerPID) });
  }
  return 'null';
}`

// JXA: the topmost normal (layer 0) window on the screen, skipping the same furniture. It is the window with the keyboard focus.
const FRONT_WINDOW_JXA = `ObjC.import('CoreGraphics');
function run(argv) {
  var ownPid = Number(argv[0]), dw = Number(argv[1]), dh = Number(argv[2]);
  var list = ObjC.deepUnwrap(ObjC.castRefToObject($.CGWindowListCopyWindowInfo($.kCGWindowListOptionOnScreenOnly | $.kCGWindowListExcludeDesktopElements, $.kCGNullWindowID)));
  for (var i = 0; i < list.length; i++) {
    var w = list[i], b = w.kCGWindowBounds;
    if (!b || w.kCGWindowAlpha === 0 || Number(w.kCGWindowLayer) !== 0) continue;
    var name = String(w.kCGWindowOwnerName);
    if ((w.kCGWindowOwnerPID === ownPid || name === 'Dock' || name === 'Window Server') && b.Width >= dw - 2 && b.Height >= dh - 2) continue;
    return JSON.stringify({ owner: name, layer: 0, id: Number(w.kCGWindowNumber), pid: Number(w.kCGWindowOwnerPID) });
  }
  return 'null';
}`

export function parseWindowHit(out: string): WindowHit | null {
  try {
    const j = JSON.parse(out.trim()) as { owner?: unknown; layer?: unknown; id?: unknown; pid?: unknown } | null
    if (!(j && typeof j.owner === 'string' && j.owner.trim() && typeof j.layer === 'number')) return null
    const num = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : undefined)
    return { owner: j.owner.trim().slice(0, 80), layer: j.layer, ...(num(j.id) !== undefined ? { windowId: num(j.id) } : {}), ...(num(j.pid) !== undefined ? { pid: num(j.pid) } : {}) }
  } catch {
    return null
  }
}

/** The one place the pinned window is compared: same window number and same owner pid (a missing number never matches). */
export function isPinnedWindow(hit: WindowHit | null, pin: PinnedWindow): boolean {
  return !!hit && hit.windowId === pin.id && hit.pid === pin.pid
}

// ---- the osascript children in flight: the kill switch ends them at once (a long action must not outlive Stop) ----
const inFlight = new Set<ChildProcess>()
/** SIGKILLs every input script that is running right now. Called by the kill switch and by anything that stops a run. */
export function abortInFlightInput(): number {
  let n = 0
  for (const child of [...inFlight]) {
    try {
      child.kill('SIGKILL')
      n += 1
    } catch {
      /* already gone */
    }
  }
  inFlight.clear()
  return n
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
    frontWindow: () =>
      new Promise((resolve) => {
        const d = display()
        execFile('/usr/bin/osascript', ['-l', 'JavaScript', '-e', FRONT_WINDOW_JXA, '--', String(ownPid), String(d.width), String(d.height)], { timeout: 2000, killSignal: 'SIGKILL' }, (err, stdout) => resolve(err ? null : parseWindowHit(String(stdout))))
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
  const clipboardKind = deps.clipboardKind ?? (deps.readClipboard ? async () => 'text' as const : runClipboardKind)
  const killedFile = deps.killFileExists ?? (() => killFileExists())
  const chunkSize = Math.max(1, Math.min(6, deps.typeChunk ?? 6))
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
    return pinProblem(target, hit)
  }
  // The window the task started in must be the one that receives this action. No pinned window in real mode: refused, never assumed.
  const pinProblem = (target: ActTarget, hit: WindowHit | null): string | null => {
    if (!target.window) return 'no window was pinned for this task (pinTarget at its start), so I will not guess which window of that app to act in'
    return isPinnedWindow(hit, target.window) ? null : `the window under that action is not the one this task started in (${target.window.owner} window ${target.window.id}); something else is on top`
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
    // The app is frontmost; is the window that has the keys the pinned one?
    const windowOk = async (): Promise<string | null> => {
      let w: WindowHit | null = null
      try {
        w = (await probe.frontWindow?.()) ?? null
      } catch {
        w = null
      }
      if (!w) return 'I could not tell which window has the keyboard'
      if (!ownerMatchesTarget(w.owner, target)) return `the front window belongs to ${w.owner}, not to ${'browser' in target ? 'a browser' : target.app}`
      return pinProblem(target, w)
    }
    let front = await readFront()
    if (ok(front)) return windowOk()
    // Not there yet. If the assistant's own window took the focus (the approval prompt), ask the target app to come forward once;
    // if some other app is in front, do not fight the person for the focus: wait a moment in case it is settling, then refuse.
    if ('app' in target && platform === 'darwin' && front && isOwnApp(front)) {
      const asked = checkAppName(target.app)
      if (asked.ok) await openAppProcess(asked.value).catch(() => undefined)
    }
    for (let waited = 0; waited < focusTimeout; waited += focusPoll) {
      await sleep(focusPoll)
      front = await readFront()
      if (ok(front)) return windowOk()
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
  // Is anything telling this action to stop? The kill flag, the data/KILL file (a separate process may have written it), the caller's Stop.
  const stopReason = (cancelled?: () => boolean): string | null => {
    if (isKilled() || killedFile()) return 'the kill switch is on'
    if (cancelled?.()) return 'the run was stopped'
    return null
  }
  const act = async (what: string, run: () => Promise<void> | void, needsAccessibility: boolean, guard?: { target: ActTarget | undefined; at?: { x: number; y: number }; cancelled?: () => boolean }): Promise<ActResult> => {
    // Understudy: while the global kill switch is on, nothing runs, not even a dry run.
    const stopFirst = stopReason(guard?.cancelled)
    if (stopFirst) return blocked(stopFirst)
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
      const stopNow = stopReason(guard?.cancelled) // the switch may have been pressed while the desktop was being read
      if (stopNow) return blocked(stopNow)
      // S-18: the hit test and the click are two scripts. Read the window under the point AGAIN right before the click goes out: a window
      // that moved, a banner or a Space switch in between refuses the click. (The gap left is the launch of one osascript; an in-process
      // JXA click that tests and posts in one go would close it, and is the next step.)
      if (guard?.at) {
        const again = await guardPoint(guard.target, guard.at)
        if (again) {
          log('actuator', `REFUSED ${what}: ${again} (second look, right before sending)`)
          return blocked(`${again} (the window changed just before the click)`)
        }
        const last = stopReason(guard.cancelled)
        if (last) return blocked(last)
      }
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
      return act(`${double ? 'double ' : ''}click at ${at.x},${at.y}`, () => osascript(clickScript(at.x, at.y, double)), true, { target: opts.target, at, cancelled: opts.cancelled })
    },

    async typeText(text, opts = {}) {
      const c = checkTypedText(text)
      if (!c.ok) return blocked(c.detail)
      // The log line carries the length only: typed text can be personal. In a dry run one call says what would happen.
      if (dryRun) return act(`typeText (${c.value.length} characters)`, () => undefined, true, { target: opts.target, cancelled: opts.cancelled })
      // Real typing goes in short chunks, and EVERY chunk is its own guarded action: the kill flag, data/KILL, the caller's Stop and
      // the pinned window are looked at again before each one, so a stop or a window change ends the typing within a few characters.
      const chars = [...c.value]
      let typed = 0
      for (let i = 0; i < chars.length; i += chunkSize) {
        const chunk = chars.slice(i, i + chunkSize).join('')
        const r = await act(`typeText chunk (${chunk.length} of ${chars.length - typed} remaining characters)`, () => osascript(typeScript(chunk)), true, { target: opts.target, cancelled: opts.cancelled })
        if (!r.ok) return typed > 0 ? { ...r, detail: `${r.detail ?? 'stopped'}; typed ${typed} of ${chars.length} characters` } : r // a partial typing says how far it got
        typed += chunk.length
      }
      return { ok: true }
    },

    async pasteText(text, opts = {}) {
      const c = checkTypedText(text)
      if (!c.ok) return blocked(c.detail)
      const keys = checkKeyCombo('cmd+v')
      if (!keys.ok) return blocked(keys.detail)
      const statement = keys.value.statement
      // A clipboard with an image or files is never overwritten: say no and let the caller type instead.
      if (!dryRun) {
        const kind = await clipboardKind().catch(() => 'other' as const)
        if (kind === 'other') return blocked('the clipboard holds something other than text (an image or files) and I will not overwrite it')
      }
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
        { target: opts.target, cancelled: opts.cancelled },
      )
    },

    async pinTarget(target) {
      const never = refuseNeverActTarget(target)
      if (never) return { ok: false, detail: never }
      if (dryRun) return { ok: true, target }
      let w: WindowHit | null = null
      try {
        w = (await probe.frontWindow?.()) ?? null
      } catch {
        w = null
      }
      if (!w || w.windowId === undefined || w.pid === undefined) return { ok: false, detail: 'I could not read which window the task starts in' }
      if (!ownerMatchesTarget(w.owner, target)) return { ok: false, detail: `the front window belongs to ${w.owner}, not to ${'browser' in target ? 'a browser' : target.app}` }
      const window: PinnedWindow = { id: w.windowId, pid: w.pid, owner: w.owner }
      return { ok: true, target: 'browser' in target ? { browser: true, window } : { app: target.app, window } }
    },

    async pressKeys(combo, opts = {}) {
      const c = checkKeyCombo(combo)
      if (!c.ok) return blocked(c.detail)
      return act(`pressKeys ${c.value.canonical}`, () => osascript(['-e', c.value.statement]), true, { target: opts.target, cancelled: opts.cancelled })
    },

    async scroll(p, dy, opts = {}) {
      const lines = checkScrollDelta(dy)
      if (!lines.ok) return blocked(lines.detail)
      const at = point(p)
      if (isResult(at)) return at
      return act(`scroll ${lines.value} lines at ${at.x},${at.y}`, () => osascript(scrollScript(at.x, at.y, lines.value)), true, { target: opts.target, at, cancelled: opts.cancelled })
    },
  }
}
