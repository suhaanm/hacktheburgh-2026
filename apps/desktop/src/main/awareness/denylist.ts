// What a glance must never look at (AWR-2). Deterministic, by bundle id, in two layers:
//
//   always   password managers, Keychain/Passwords, macOS authentication prompts, the login window, and a few finance apps. Cannot be switched off.
//   strict   (the default) messaging and mail apps by bundle id AND by app kind (chat, email); an app we cannot read is "unknown", and
//            unknown means no glance. Strict mode can be turned off by the worker; the layer above stays.
//   worker   the worker's own list (settings: glanceDenylist), added to the above, never replacing it.
//
// Limits, said plainly: browser-based banking and webmail are just "a browser" to this check (no titles or URLs are read, on purpose).
// What protects them is secure input (a password field has focus) and the worker's own list. Excluding a site would need the browser
// extension's hashed domains; that is not built.
import type { AppKind, AppKindOrUnknown } from './types'

export type DenyCategory = 'password_manager' | 'system_auth' | 'finance' | 'messaging' | 'mail' | 'worker_list'

// Exact bundle ids (lower case) and prefixes (ending in "."), per category.
const ALWAYS: Array<{ category: DenyCategory; exact: string[]; prefix: string[] }> = [
  {
    category: 'password_manager',
    exact: [
      'com.apple.keychainaccess',
      'com.apple.passwords', // the Passwords app (macOS 15 and later)
      'org.keepassxc.keepassxc',
      'com.callpod.keepermac',
      'com.enpass.enpass-mac',
      'com.nordsec.nordpass',
      'in.sinew.enpass-desktop',
    ],
    prefix: ['com.agilebits.', 'com.1password.', 'com.bitwarden.', 'com.dashlane.', 'com.lastpass.', 'com.protonpass.', 'com.keepersecurity.'],
  },
  {
    category: 'system_auth',
    exact: ['com.apple.securityagent', 'com.apple.loginwindow', 'com.apple.screensaver.engine', 'com.apple.coreservices.uiagent'],
    prefix: [],
  },
  {
    // Few banks ship macOS apps; a bank's website is a browser tab and cannot be told apart here. These are personal-finance apps.
    category: 'finance',
    exact: ['com.youneedabudget.ynab', 'com.intuit.quicken', 'com.mint.internal', 'com.monarchmoney.desktop'],
    prefix: ['com.intuit.quickbooks', 'com.ynab.'],
  },
]

const STRICT: Array<{ category: DenyCategory; exact: string[]; prefix: string[] }> = [
  {
    category: 'messaging',
    exact: [
      'com.apple.mobilesms', // Messages
      'com.tinyspeck.slackmacgap', // Slack
      'net.whatsapp.whatsapp', // WhatsApp
      'org.whispersystems.signal-desktop', // Signal
      'com.microsoft.teams',
      'com.microsoft.teams2', // Teams
      'ru.keepcoder.telegram',
      'com.hnc.discord',
      'com.facebook.archon', // Messenger
      'com.apple.facetime',
      'us.zoom.xos',
    ],
    prefix: ['com.tinyspeck.', 'com.microsoft.teams'],
  },
  {
    category: 'mail',
    exact: ['com.apple.mail', 'com.microsoft.outlook', 'com.readdle.smartemail-mac', 'com.google.gmail', 'com.superhuman.electron', 'com.freron.mailmate'],
    prefix: ['com.microsoft.outlook'],
  },
]

export interface DenyOptions {
  strict: boolean
  // The worker's list: exact ids, or a prefix written as "com.foo.*".
  workerList: readonly string[]
}

export type AppVerdict = { verdict: 'allow' } | { verdict: 'deny'; category: DenyCategory } | { verdict: 'unknown' }

const norm = (s: string): string => s.trim().toLowerCase()

function matches(id: string, group: { exact: string[]; prefix: string[] }): boolean {
  return group.exact.includes(id) || group.prefix.some((p) => id.startsWith(p))
}

export function workerListMatches(id: string, list: readonly string[]): boolean {
  for (const raw of list) {
    const e = norm(raw)
    if (e.endsWith('.*') ? id.startsWith(e.slice(0, -1)) : id === e) return true
  }
  return false
}

/** The verdict for the frontmost app. `bundleId` null means it could not be read (unknown); never guessed. */
export function decideApp(bundleId: string | null, kind: AppKindOrUnknown | null, opts: DenyOptions): AppVerdict {
  if (bundleId === null || bundleId.trim() === '') return { verdict: 'unknown' }
  const id = norm(bundleId)
  for (const g of ALWAYS) if (matches(id, g)) return { verdict: 'deny', category: g.category }
  if (workerListMatches(id, opts.workerList)) return { verdict: 'deny', category: 'worker_list' }
  if (opts.strict) {
    for (const g of STRICT) if (matches(id, g)) return { verdict: 'deny', category: g.category }
    if (kind === 'chat') return { verdict: 'deny', category: 'messaging' }
    if (kind === 'email') return { verdict: 'deny', category: 'mail' }
  }
  return { verdict: 'allow' }
}

// ------------------------------------------------------------------------------------------------ app kind
// Frontmost bundle id -> coarse kind. A small table on purpose: unlisted apps are 'other', unreadable ones 'unknown'.
const KINDS: Array<{ kind: AppKind; exact: string[]; prefix: string[] }> = [
  {
    kind: 'browser',
    exact: [
      'com.apple.safari', 'com.apple.safaritechnologypreview', 'com.google.chrome', 'com.google.chrome.canary', 'org.mozilla.firefox',
      'org.mozilla.firefoxdeveloperedition', 'com.microsoft.edgemac', 'com.brave.browser', 'company.thebrowser.browser', // Arc
      'com.operasoftware.opera', 'com.vivaldi.vivaldi', 'org.chromium.chromium', 'com.kagi.kagimacos',
    ],
    prefix: ['com.google.chrome.', 'org.mozilla.'],
  },
  {
    kind: 'spreadsheet',
    exact: ['com.microsoft.excel', 'com.apple.iwork.numbers', 'org.libreoffice.script', 'com.google.drivefs', 'org.openoffice.script'],
    prefix: [],
  },
  { kind: 'email', exact: STRICT[1].exact, prefix: STRICT[1].prefix },
  {
    kind: 'code_editor',
    exact: [
      'com.microsoft.vscode', 'com.microsoft.vscodeinsiders', 'com.apple.dt.xcode', 'com.sublimetext.4', 'com.sublimetext.3', 'dev.zed.zed',
      'com.vscodium', 'com.todesktop.230313mzl4w4u92', // Cursor
      'com.panic.nova', 'com.github.atom', 'com.macromates.textmate', 'org.vim.macvim', 'com.neovide.neovide',
    ],
    prefix: ['com.jetbrains.'],
  },
  {
    kind: 'terminal',
    exact: ['com.apple.terminal', 'com.googlecode.iterm2', 'dev.warp.warp-stable', 'net.kovidgoyal.kitty', 'org.alacritty', 'com.github.wez.wezterm', 'co.zeit.hyper', 'com.mitchellh.ghostty'],
    prefix: [],
  },
  { kind: 'chat', exact: STRICT[0].exact.filter((x) => x !== 'us.zoom.xos' && x !== 'com.apple.facetime'), prefix: ['com.tinyspeck.', 'com.microsoft.teams'] },
]

export function appKindFor(bundleId: string | null): AppKindOrUnknown {
  if (bundleId === null || bundleId.trim() === '') return 'unknown'
  const id = norm(bundleId)
  for (const g of KINDS) if (matches(id, g)) return g.kind
  return 'other'
}

export const BUNDLE_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{1,120}$/

/** Lists the default categories for the Privacy screen: what is skipped always, and what strict adds. Ids only. */
export function describeDenylist(): { always: Record<string, string[]>; strict: Record<string, string[]> } {
  const out = (groups: typeof ALWAYS): Record<string, string[]> => Object.fromEntries(groups.map((g) => [g.category, [...g.exact, ...g.prefix.map((p) => `${p}*`)]]))
  return { always: out(ALWAYS), strict: out(STRICT) }
}
