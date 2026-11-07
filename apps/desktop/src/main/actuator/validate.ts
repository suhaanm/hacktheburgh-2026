// Input validation for every actuator primitive. Nothing the model or the screen produced is ever interpolated into
// AppleScript source: typed text travels as an osascript ARGUMENT (argv), key combos and settings panes come from
// fixed tables, and numbers are formatted by us. Anything outside these allowlists is "blocked".
export type Checked<T> = { ok: true; value: T } | { ok: false; detail: string }
const ok = <T>(value: T): Checked<T> => ({ ok: true, value })
const no = (detail: string): Checked<never> => ({ ok: false, detail })

// ---- URLs: http/https only, no credentials. localhost is fine. ----
export function checkUrl(raw: string): Checked<string> {
  if (typeof raw !== 'string') return no('the address must be text')
  const text = raw.trim()
  if (text.length === 0 || text.length > 2048) return no('the address is empty or too long')
  // `new URL` silently drops tabs and newlines, which hides tricks such as "java\nscript:"; refuse them outright.
  if (/[\u0000- \u007f]/.test(text)) return no('the address contains spaces or control characters')
  let url: URL
  try {
    url = new URL(text)
  } catch {
    return no('not a valid web address')
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return no(`only http and https addresses are allowed, not ${url.protocol}`)
  if (url.username || url.password) return no('addresses with a user name or password are not allowed')
  if (!url.hostname) return no('the address has no host')
  return ok(url.href)
}

// ---- App names: letters, digits, space, dot, dash; must start with a letter or digit. No shell is involved. ----
const APP_RE = /^[A-Za-z0-9][A-Za-z0-9 .-]{0,59}$/
// Apps that turn "type some text" into "run anything": the learner can open these themselves.
const BLOCKED_APPS = /^(terminal|iterm2?|script editor|automator|keychain access|warp|alacritty|kitty|hyper)$/i

export function checkAppName(raw: string): Checked<string> {
  if (typeof raw !== 'string') return no('the app name must be text')
  // Only plain spaces may separate words: a newline or tab must not be quietly turned into a space.
  if (/[\u0000-\u001f\u007f]/.test(raw)) return no('app names may not contain line breaks, tabs or control characters')
  const name = raw.trim().replace(/ +/g, ' ')
  if (!APP_RE.test(name)) return no('app names may only contain letters, digits, spaces, dots and dashes')
  if (BLOCKED_APPS.test(name)) return no(`${name} is not opened for the learner`)
  return ok(name)
}

// ---- Typed text ----
export const MAX_TYPED_CHARS = 300
export function checkTypedText(text: string): Checked<string> {
  if (typeof text !== 'string' || text.length === 0) return no('there is no text to type')
  if (text.length > MAX_TYPED_CHARS) return no(`at most ${MAX_TYPED_CHARS} characters can be typed at once`)
  // Return and tab can submit a form or jump to another field: they are pressKeys decisions, never part of typed text.
  if (/[\u0000-\u001f\u007f]/.test(text)) return no('typed text may not contain line breaks, tabs or control characters')
  return ok(text)
}

// ---- Key combos ----
const NAMED_KEYS: Record<string, number> = { return: 36, tab: 48, space: 49, escape: 53, left: 123, right: 124, down: 125, up: 126 }
const CMD_LETTERS = new Set(['l', 't', 'w', 'v', 'c', 'a', 'f'])
const ALIASES: Record<string, string> = { enter: 'return', esc: 'escape', command: 'cmd', meta: 'cmd', super: 'cmd', uparrow: 'up', downarrow: 'down', leftarrow: 'left', rightarrow: 'right' }

export interface KeyPress {
  canonical: string
  // The one fixed AppleScript statement for this key. Built from the tables above, never from the raw input.
  statement: string
}

export function checkKeyCombo(raw: string): Checked<KeyPress> {
  if (typeof raw !== 'string') return no('the key must be text')
  const tokens = raw
    .toLowerCase()
    .trim()
    .split('+')
    .map((t) => ALIASES[t.trim()] ?? t.trim())
  if (tokens.length === 1 && tokens[0] in NAMED_KEYS) {
    return ok({ canonical: tokens[0], statement: `tell application "System Events" to key code ${NAMED_KEYS[tokens[0]]}` })
  }
  if (tokens.length === 2 && tokens[0] === 'cmd' && CMD_LETTERS.has(tokens[1])) {
    return ok({ canonical: `cmd+${tokens[1]}`, statement: `tell application "System Events" to keystroke "${tokens[1]}" using {command down}` })
  }
  return no(`the key combination "${raw.slice(0, 30)}" is not on the allowed list (return, tab, escape, space, arrows, cmd+l/t/w/v/c/a/f)`)
}

// ---- Settings panes: fixed deep links only ----
export const SETTINGS_PANES = {
  screen: 'x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture',
  microphone: 'x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone',
  accessibility: 'x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility',
  privacy: 'x-apple.systempreferences:com.apple.preference.security',
  displays: 'x-apple.systempreferences:com.apple.Displays-Settings.extension',
  'accessibility-display': 'x-apple.systempreferences:com.apple.Accessibility-Settings.extension',
  sound: 'x-apple.systempreferences:com.apple.Sound-Settings.extension',
  wifi: 'x-apple.systempreferences:com.apple.wifi-settings-extension',
  bluetooth: 'x-apple.systempreferences:com.apple.BluetoothSettings',
  notifications: 'x-apple.systempreferences:com.apple.Notifications-Settings.extension',
  keyboard: 'x-apple.systempreferences:com.apple.Keyboard-Settings.extension',
  general: 'x-apple.systempreferences:com.apple.systempreferences.GeneralSettings',
} as const
export type SettingsPane = keyof typeof SETTINGS_PANES

export function checkSettingsPane(pane: string): Checked<string> {
  return typeof pane === 'string' && Object.prototype.hasOwnProperty.call(SETTINGS_PANES, pane) ? ok(SETTINGS_PANES[pane as SettingsPane]) : no(`unknown settings pane "${String(pane).slice(0, 30)}"`)
}

// ---- Scroll ----
export const MAX_SCROLL_LINES = 50
export function checkScrollDelta(dy: number): Checked<number> {
  if (!Number.isFinite(dy)) return no('scroll amount must be a number')
  const lines = Math.round(dy)
  if (lines === 0 || Math.abs(lines) > MAX_SCROLL_LINES) return no(`scroll between 1 and ${MAX_SCROLL_LINES} lines at a time`)
  return ok(lines)
}
