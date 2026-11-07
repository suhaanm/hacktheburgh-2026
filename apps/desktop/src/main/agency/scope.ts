// Scope enforcement for act_for_me: "only for the scope of the user's request".
// The goal names (or the first step records) the app or site the task is about; before EVERY action the frontmost
// application is read again, and the task stops with a plain message when another app has come to the front.
// Reads the frontmost app with `lsappinfo` (no Accessibility or Automation prompt). Names only, never window contents.
import { execFile } from 'node:child_process'

export const BROWSERS = ['safari', 'google chrome', 'chrome', 'firefox', 'arc', 'microsoft edge', 'brave browser', 'opera', 'vivaldi', 'chromium']
// Alongside's own windows (dev builds run as "Electron"): allowed, they hold the confirmation prompt.
const OWN_APPS = ['alongside', 'electron']
// Never acted on, whatever the goal says: the assistant's own desktop app and terminals / shells.
const NEVER_ACT = ['claude', 'terminal', 'iterm', 'iterm2', 'ghostty', 'warp', 'wezterm', 'kitty', 'alacritty', 'hyper', 'tabby']

const norm = (name: string): string => name.trim().toLowerCase()
export const isOwnApp = (name: string): boolean => OWN_APPS.includes(norm(name))
export const isNeverActApp = (name: string): boolean => NEVER_ACT.includes(norm(name)) || /^claude\b/i.test(name.trim())
export const isBrowser = (name: string): boolean => BROWSERS.includes(norm(name))

export interface TaskScope {
  // 'browser' = any browser (web goals), 'app' = one named app (e.g. Calculator), 'first' = whatever the first step sees.
  kind: 'browser' | 'app' | 'first'
  app?: string
}

const WEB_WORDS = /\b(?:web\s*site|website|web\s*page|webpage|page|site|browser|safari|chrome|firefox|edge|brave|arc|online|careers?|https?:|www\.|[a-z0-9-]+\.(?:com|org|net|io|co\.uk|gov|edu|ai|dev)\b)/i
// Native apps a goal can name; the match is case-insensitive on the goal text.
const NAMED_APPS: Array<[RegExp, string]> = [
  [/\bcalculator\b/i, 'Calculator'],
  [/\bnotes\b(?=\s+app|\s+application)/i, 'Notes'],
  [/\bfinder\b/i, 'Finder'],
  [/\bphotos\b(?=\s+app|\s+application)/i, 'Photos'],
  [/\bmaps\b(?=\s+app|\s+application)/i, 'Maps'],
  [/\bcalendar\b(?=\s+app|\s+application)/i, 'Calendar'],
  [/\bpreview\b(?=\s+app|\s+application)/i, 'Preview'],
]

// What app or site the goal is about: a named native app wins, then a web goal (the browser family), else the first front app.
export function scopeFromGoal(goal: string): TaskScope {
  for (const [re, app] of NAMED_APPS) if (re.test(goal)) return { kind: 'app', app }
  if (WEB_WORDS.test(goal)) return { kind: 'browser' }
  return { kind: 'first' }
}

export interface ScopeState {
  scope: TaskScope
  // The first allowed non-Alongside app seen (locks 'first' scopes); the app to bring back before typing.
  target?: string
}

export type ScopeVerdict = { ok: true; app: string | null } | { ok: false; app: string; message: string }

// Pure decision: may the task act while `front` is the frontmost app? `front` null (unreadable) never blocks.
export function checkScope(state: ScopeState, front: string | null): ScopeVerdict {
  if (!front) return { ok: true, app: null }
  const app = front.trim()
  if (isOwnApp(app)) return { ok: true, app }
  if (isNeverActApp(app)) return { ok: false, app, message: `${app} came to the front, and I never act in it, so I stopped. Nothing else was done.` }
  const { scope } = state
  const allowed =
    scope.kind === 'browser' ? isBrowser(app) : scope.kind === 'app' ? norm(app) === norm(scope.app ?? '') : state.target === undefined || norm(app) === norm(state.target)
  if (!allowed) {
    const wanted = scope.kind === 'browser' ? 'your browser' : scope.kind === 'app' ? (scope.app as string) : (state.target as string)
    return { ok: false, app, message: `${app} came to the front, but this task is only about ${wanted}, so I stopped. Nothing was done in ${app}.` }
  }
  if (state.target === undefined) state.target = app
  return { ok: true, app }
}

// `lsappinfo info -only name <asn>` prints `"LSDisplayName"="Safari"`.
export function parseLsappinfoName(out: string): string | null {
  const m = /"LSDisplayName"\s*=\s*"([^"]{1,80})"/.exec(out)
  return m ? m[1] : null
}

const run = (args: string[], timeoutMs: number): Promise<string> =>
  new Promise((resolve) => {
    execFile('/usr/bin/lsappinfo', args, { timeout: timeoutMs, killSignal: 'SIGKILL' }, (err, stdout) => resolve(err ? '' : String(stdout)))
  })

export type FrontApp = () => Promise<string | null>

// What the narrow Return allowance needs to know about the frontmost window: whether the focused element is a secure
// text field (AX subrole only, never its value) and the window title. null = could not be read.
export interface FocusInfo {
  secure: boolean | null
  title: string | null
}
export type ReadFocus = () => Promise<FocusInfo>

export const FOCUS_JXA = `function run() {
  var se = Application('System Events');
  var procs = se.processes.whose({frontmost: true})();
  if (!procs.length) return '{}';
  var p = procs[0];
  var out = {secure: null, title: null};
  try { out.title = String(p.windows[0].name()); } catch (e) {}
  try {
    var f = p.attributes.byName('AXFocusedUIElement').value();
    out.secure = (String(f.attributes.byName('AXSubrole').value()) === 'AXSecureTextField');
  } catch (e) {}
  return JSON.stringify(out);
}`

export function parseFocusOutput(raw: string): FocusInfo {
  try {
    const j = JSON.parse(raw) as { secure?: unknown; title?: unknown }
    return { secure: typeof j.secure === 'boolean' ? j.secure : null, title: typeof j.title === 'string' && j.title.trim() ? j.title.slice(0, 200) : null }
  } catch {
    return { secure: null, title: null }
  }
}

export const readFocusInfo: ReadFocus = () =>
  new Promise((resolve) => {
    if (process.platform !== 'darwin') return resolve({ secure: null, title: null })
    execFile('/usr/bin/osascript', ['-l', 'JavaScript', '-e', FOCUS_JXA], { timeout: 1500, killSignal: 'SIGKILL' }, (err, stdout) => resolve(err ? { secure: null, title: null } : parseFocusOutput(String(stdout).trim())))
  })

export const readFrontApp: FrontApp = async () => {
  if (process.platform !== 'darwin') return null
  const asn = (await run(['front'], 1500)).trim()
  if (!asn) return null
  return parseLsappinfoName(await run(['info', '-only', 'name', asn], 1500))
}
