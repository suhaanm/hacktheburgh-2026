// The actuator: every real action Alongside can take on the learner's computer goes through this ONE object.
//   Tier 1 (no Accessibility needed): openUrl, openApp, revealPath, openSettingsPane.
//   Tier 2 (needs macOS Accessibility, checked with isTrustedAccessibilityClient(false), which never prompts):
//   clickAt, typeText, pressKeys, scroll, via osascript.
// It is a primitive layer: WHETHER to act (settings, approvals, denylist, scam context, Stop) is decided by the callers
// (do_it_for_me in ./flow.ts, AGENCY's policy engine). Everything is validated against allowlists here as defence in depth;
// nothing the model or the screen produced is interpolated into script source.
// ALONGSIDE_ACTUATOR_DRYRUN=1 validates, logs every call and performs nothing (returns {ok:true, reason:'dry-run'}).
// electron is imported lazily so unit tests need no Electron.
import { execFile } from 'node:child_process'
import { existsSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import type { NormPoint } from '../../shared/protocol'
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

export interface Actuator {
  status(): { accessibility: boolean; dryRun: boolean }
  // True when a click/type/key action could run right now (Accessibility granted, or dry run).
  canClick(): boolean
  openUrl(url: string): Promise<ActResult>
  openApp(name: string): Promise<ActResult>
  revealPath(path: string): Promise<ActResult>
  openSettingsPane(pane: SettingsPane): Promise<ActResult>
  // One left click, or a double click when `double` is set (two clicks in one script: the OS decides if it counts as double).
  clickAt(p: NormPoint, opts?: { double?: boolean }): Promise<ActResult>
  // Types plain text (max 300 chars, no control characters) into whatever has focus.
  typeText(text: string): Promise<ActResult>
  // Allowlist only: return, tab, escape, space, arrows, cmd+l/t/w/v/c/a/f.
  pressKeys(combo: string): Promise<ActResult>
  // Fallback for typeText: puts the text on the clipboard, presses Cmd+V, then restores the previous clipboard text.
  pasteText?(text: string): Promise<ActResult>
  // Scrolls the window under `p`; dy > 0 reads further down, dy < 0 back up (lines, 1-50).
  scroll(p: NormPoint, dy: number): Promise<ActResult>
}

export interface ActuatorDeps {
  log?: (scope: string, ...args: unknown[]) => void
  dryRun?: boolean
  platform?: NodeJS.Platform
  isTrusted?: () => boolean
  displayBounds?: () => DisplayBounds
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

export const dryRunFromEnv = (): boolean => process.env.ALONGSIDE_ACTUATOR_DRYRUN === '1'

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
  let trusted = deps.isTrusted
  let bounds = deps.displayBounds
  let openExternal = deps.openExternal
  let showItemInFolder = deps.showItemInFolder
  if (!trusted || !bounds || !openExternal || !showItemInFolder) {
    void electron()
      .then(({ systemPreferences, screen, shell }) => {
        trusted ??= () => platform === 'darwin' && systemPreferences.isTrustedAccessibilityClient(false)
        bounds ??= () => screen.getPrimaryDisplay().bounds
        openExternal ??= (url) => shell.openExternal(url)
        showItemInFolder ??= (p) => shell.showItemInFolder(p)
      })
      .catch(() => undefined)
  }

  const blocked = (detail: string): ActResult => ({ ok: false, reason: 'blocked', detail })
  const dry = (what: string): ActResult => {
    log('actuator', `DRYRUN ${what} (not performed)`)
    return { ok: true, reason: 'dry-run', detail: what }
  }
  // Tier 2 gate: macOS only, Accessibility granted. Dry run skips it because nothing is performed.
  const tier2 = (): ActResult | null => {
    if (platform !== 'darwin') return { ok: false, reason: 'failed', detail: 'this action is implemented for macOS only' }
    return trusted?.() ? null : { ok: false, reason: 'accessibility' }
  }
  const act = async (what: string, run: () => Promise<void> | void, needsAccessibility: boolean): Promise<ActResult> => {
    if (dryRun) return dry(what)
    if (needsAccessibility) {
      const gate = tier2()
      if (gate) return gate
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
      return act(`${double ? 'double ' : ''}click at ${at.x},${at.y}`, () => osascript(clickScript(at.x, at.y, double)), true)
    },

    async typeText(text) {
      const c = checkTypedText(text)
      if (!c.ok) return blocked(c.detail)
      // The log line carries the length only: typed text can be personal.
      return act(`typeText (${c.value.length} characters)`, () => osascript(typeScript(c.value)), true)
    },

    async pasteText(text) {
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
      )
    },

    async pressKeys(combo) {
      const c = checkKeyCombo(combo)
      if (!c.ok) return blocked(c.detail)
      return act(`pressKeys ${c.value.canonical}`, () => osascript(['-e', c.value.statement]), true)
    },

    async scroll(p, dy) {
      const lines = checkScrollDelta(dy)
      if (!lines.ok) return blocked(lines.detail)
      const at = point(p)
      if (isResult(at)) return at
      return act(`scroll ${lines.value} lines at ${at.x},${at.y}`, () => osascript(scrollScript(at.x, at.y, lines.value)), true)
    },
  }
}
