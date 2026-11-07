// Adapted from farzaa/clicky (MIT) — hermes-clicky-plugin/safety_policy.py, hermes-clicky-plugin/permission_policy.py
// Pure, deterministic policy for everything the assistant may DO for a learner. No I/O, no clocks (time is passed in),
// no model: plain code decides, never the model's words. (One exception: checkPath asks the file system for the real
// location of a path, so a symlink inside a shared folder cannot point outside it.)
//
// Tiers (clicky's observe / point / confirmBeforeAction / scopedAutopilot) map onto the `agency` setting:
//   off          -> observe/point: nothing is ever done; the assistant teaches instead
//   ask_each     -> confirmBeforeAction: a real-click confirmation before EVERY action
//   ask_per_task -> scopedAutopilot: the plan is confirmed once; low-risk clicks/scrolls/waits then run, anything
//                   medium or high risk (typing, keys, apps, files, sending-shaped words) still asks each time
// There is no fullControl tier.
import { realpathSync } from 'node:fs'
import path from 'node:path'
import type { AgencyCode } from '../../shared/protocol'
import type { Settings } from '../../shared/settings'
import { denylistMatch } from '../actuator/policy'
import { isNeverActApp } from './scope'

export type Agency = Settings['agency']
export type Risk = 'low' | 'medium' | 'high'
export type ActionKind = 'open_url' | 'open_app' | 'open_file' | 'open_settings' | 'click' | 'double_click' | 'type' | 'keys' | 'scroll' | 'wait'

export interface ProposedAction {
  kind: ActionKind
  // What the action targets, in plain words (grounded label, the model's stated intent). Matched against the denylist.
  label?: string
  // Any further target text (the learner's goal, the element description).
  targetText?: string
  // Text that would be typed.
  text?: string
  // URL, app name, path, settings pane or key combo.
  value?: string
  // 0..1; below LOW_CONFIDENCE the action is treated as medium risk.
  confidence?: number
  // The loop believes the focused field is a password / secure field.
  secureField?: boolean
}

export interface PolicyContext {
  agency: Agency
  // The current lesson step is safetyCritical.
  safetyCriticalStep: boolean
  // A scam check is running or the learner is in the spot_scam skill.
  scamContext: boolean
  // The learner confirmed the plan for this task (ask_per_task).
  planApproved: boolean
  // The goal text itself explicitly asks to accept / agree to cookies or consent: consent words in a label then pass.
  goalAcceptsCookies?: boolean
  // Facts the loop gathered for the narrow Return allowance (see returnAfterTypeProblem); absent = Return stays blocked.
  returnFacts?: ReturnFacts
  // Our own practice stage origin, the only localhost address open_url may reach.
  stageOrigin?: string
  // Folders the learner consented to for file reveal; empty means the home folder only.
  fileRoots?: string[]
  homeDir?: string
}

export type PolicyDecision =
  | { allowed: false; code: Extract<AgencyCode, 'agency_off' | 'blocked' | 'safety_step' | 'scam_check' | 'invalid'>; reason: string; flags: string[] }
  | { allowed: true; ask: boolean; risk: Risk; reason: string; flags: string[] }

// ---------- the narrow Return allowance ----------
// Return is blocked, with ONE exception: it may submit a plain search query that was typed by the immediately preceding
// action of the same task, on a normal page of the app the task is about. Everything below must hold.
export interface ReturnFacts {
  // Text of the immediately preceding EXECUTED action when it was a `type`, else null.
  prevTypedText: string | null
  // Return presses already made in this task.
  returnsSoFar: number
  // AX subrole of the focused element is AXSecureTextField: true / false, or null when it could not be read.
  secureField: boolean | null
  // Title of the frontmost window, or null when it could not be read.
  windowTitle: string | null
  frontApp: string | null
  // The app the task is scoped to (scope.ts), and whether it is a browser or a named native app.
  targetApp: string | null
  targetKnown: boolean
  // The goal text holds no denylist word once negated clauses are removed.
  goalClean: boolean
}

export const MAX_RETURNS_PER_TASK = 2
export const MAX_QUERY_CHARS = 80
const RETURN_BAD_TITLE = /login|sign.?in|log.?in|password|checkout|payment|pay|billing|card|account|register|apply-now|submit/i

// Does the typed text look like an ordinary search? (It has already passed the typed-text scan to get this far.)
export function plainQuery(text: string | null | undefined): boolean {
  if (!text) return false
  const t = text.trim()
  if (!t || t.length > MAX_QUERY_CHARS || t.includes('@') || /\d{6,}/.test(t) || /(?:\d[ -]?){9,}/.test(t)) return false
  return !typedTextProblem(t)
}

// null = this Return may be pressed; otherwise the plain reason it is left to the person.
export function returnAfterTypeProblem(ctx: PolicyContext): string | null {
  const f = ctx.returnFacts
  const left = 'I only press Return straight after typing a plain search on the page you asked about. This is not that, so I leave it to you.'
  if (!f) return left
  if (f.prevTypedText === null) return left
  if (!plainQuery(f.prevTypedText)) return 'The text I typed is not a plain search, so I leave pressing Return to you.'
  if (f.returnsSoFar >= MAX_RETURNS_PER_TASK) return `I already pressed Return ${MAX_RETURNS_PER_TASK} times in this task, so I leave the rest to you.`
  if (ctx.agency === 'ask_per_task' && !ctx.planApproved) return left
  if (f.secureField === true) return 'The box in focus is a password or secure box, so I never press Return there.'
  if (f.windowTitle !== null && RETURN_BAD_TITLE.test(f.windowTitle)) return 'This page looks like a sign-in, payment or form page, so I leave pressing Return to you.'
  if (f.secureField === null && f.windowTitle === null) return 'I cannot tell what page this is, so I leave pressing Return to you.'
  if (f.frontApp !== null && isNeverActApp(f.frontApp)) return 'That app is one I never act in, so I leave pressing Return to you.'
  const sameApp = f.frontApp !== null && f.targetApp !== null && f.frontApp.trim().toLowerCase() === f.targetApp.trim().toLowerCase()
  if (!sameApp || !f.targetKnown) return 'The app in front is not the one this task is about, so I leave pressing Return to you.'
  if (!f.goalClean) return left
  return null
}

export const LOW_CONFIDENCE = 0.7
export const MAX_ACTIONS_PER_TASK = 12
export const MIN_ACTION_GAP_MS = 1500
export const MAX_TYPED_CHARS = 300

// Extra blocking wording from clicky's safety_policy.py (destructive / payment / credential_entry / permission_prompt)
// that the shared denylist does not already cover.
const EXTRA_BLOCK = new RegExp(
  `(?:^|[^a-z0-9])(?:${[
    'destroy',
    'wipe',
    'format',
    'discard',
    'permanent',
    'terminate\\s+account',
    'close\\s+account',
    'invoice',
    'wire\\b',
    'subscribe',
    'upgrade',
    'passcode',
    '2fa\\b',
    'two[\\s-]*factor',
    'otp\\b',
    'one[\\s-]*time\\s+code',
    'login\\s+code',
    'verification\\s+code',
    'api[\\s_-]*key',
    'secret',
    'private\\s+key',
    'seed\\s+phrase',
    'recovery\\s+phrase',
    'credential',
    'token',
    'pin\\b',
    'cvv\\b',
    'cvc\\b',
    'sort\\s+code',
    'iban\\b',
    'ssn\\b',
    'social\\s+security',
    'passport',
    'permission',
    'authori[sz]e',
    'security\\s*(?:&|and)\\s*privacy',
    'privacy\\s*(?:&|and)\\s*security',
    'system\\s+settings',
    'keychain',
    'sudo\\b',
    'terminal',
    'unlock',
  ].join('|')})`,
  'i',
)

// Sending-shaped words (clicky's send_message flag): never auto-run in ask_per_task, always ask.
const CONFIRM_WORDS = /(?:^|[^a-z0-9])(?:reply|compose|post|publish|tweet|dm\b|share|forward|invite|upload|download|print)/i

// Typed text that looks like a secret or a financial / identity number.
const CARD_LIKE = /\b(?:\d[ -]?){13,19}\b/
const LONG_DIGITS = /\d{6,}/
const SECRET_WORDS = /(?:^|[^a-z0-9])(?:password|passcode|pass\s*phrase|pin\s*code|cvv|cvc|sort\s*code|account\s*number|iban|ssn|national\s*insurance)/i

export const KEY_ALLOWLIST: ReadonlySet<string> = new Set([
  'return',
  'enter',
  'tab',
  'escape',
  'esc',
  'space',
  'up',
  'down',
  'left',
  'right',
  'cmd+l',
  'cmd+t',
  'cmd+w',
  'cmd+v',
  'cmd+c',
  'cmd+a',
  'cmd+f',
])

export function normaliseKeys(combo: string): string {
  return combo
    .toLowerCase()
    .replace(/\s+/g, '')
    .replace(/command|meta|super/g, 'cmd')
    .replace(/arrow/g, '')
    .replace(/control/g, 'ctrl')
    .replace(/option/g, 'alt')
    .replace(/\+\+/g, '+')
}

// Apps the model may never open for a learner (shells, scripting, credential stores, remote control).
const BLOCKED_APPS = [
  'terminal',
  'iterm',
  'script editor',
  'automator',
  'shortcuts',
  'keychain',
  'activity monitor',
  'disk utility',
  'console',
  'system settings',
  'system preferences',
  'screen sharing',
  'remote desktop',
  'installer',
  'xcode',
  'passwords',
  'wallet',
  'app store',
]
const APP_NAME_OK = /^[A-Za-z0-9][A-Za-z0-9 .\-]{0,39}$/

// Settings panes the learner may be taken to (names match the actuator's SettingsPane). The privacy, security and
// account panes the actuator also knows are never on this list.
export const SETTINGS_PANES = ['displays', 'accessibility-display', 'sound', 'wifi', 'bluetooth', 'notifications', 'keyboard', 'general'] as const
export type AgencyPane = (typeof SETTINGS_PANES)[number]
const PANE_ALIASES: Record<string, AgencyPane> = {
  display: 'displays',
  screen: 'displays',
  brightness: 'displays',
  text_size: 'accessibility-display',
  text: 'accessibility-display',
  bigger_text: 'accessibility-display',
  accessibility: 'accessibility-display',
  'accessibility_display': 'accessibility-display',
  wi_fi: 'wifi',
  internet: 'wifi',
  volume: 'sound',
  audio: 'sound',
}

// A friendly settings name -> the pane to open, or null when it is not an everyday pane.
export function resolvePane(value: string | undefined): AgencyPane | null {
  const key = (value ?? '').trim().toLowerCase().replace(/[\s-]+/g, '_')
  const direct = SETTINGS_PANES.find((p) => p.replace(/-/g, '_') === key)
  return direct ?? PANE_ALIASES[key] ?? null
}

const SENSITIVE_PATH = /(?:^|\/)(?:\.ssh|\.gnupg|\.aws|\.config\/gcloud|\.kube|\.docker|Library\/(?:Keychains|Cookies|Mail|Messages|Safari)|\.env[^/]*|id_(?:rsa|ed25519|ecdsa)[^/]*|[^/]*\.(?:pem|key|p12|keychain[^/]*))(?:\/|$)/i
const SENSITIVE_NAME = /(?:password|passwd|secret|credential|token|seed|wallet|recovery)/i

const blocked = (reason: string, flags: string[], code: 'blocked' | 'invalid' = 'blocked'): PolicyDecision => ({ allowed: false, code, reason, flags })

// ---------- URL rules ----------

export type UrlCheck = { ok: true; url: URL; secure: boolean; host: string } | { ok: false; code: 'blocked' | 'invalid'; reason: string }

const PRIVATE_V4 = /^(?:0\.|10\.|127\.|169\.254\.|172\.(?:1[6-9]|2\d|3[01])\.|192\.168\.|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.)/

function isLocalHost(host: string): boolean {
  const h = host.toLowerCase().replace(/^\[|\]$/g, '')
  return h === 'localhost' || h.endsWith('.localhost') || h.endsWith('.local') || h === '::1' || h === '::' || h === '0.0.0.0' || PRIVATE_V4.test(h) || /^f[cd][0-9a-f]{2}:/.test(h) || /^fe80:/.test(h)
}

export function checkUrl(raw: string, stageOrigin?: string): UrlCheck {
  const text = raw.trim()
  if (!text || text.length > 2000) return { ok: false, code: 'invalid', reason: 'That is not a web address I can use.' }
  // eslint-disable-next-line no-control-regex
  if (/[\u0000-\u001f\u007f\s]/.test(text)) return { ok: false, code: 'invalid', reason: 'That web address has characters I will not open.' }
  if (/^(?:javascript|data|file|vbscript|blob|about|chrome|ftp|ssh|smb|tel|sms|mailto|x-apple[a-z.-]*|itms[a-z-]*):/i.test(text)) {
    return { ok: false, code: 'blocked', reason: 'I only open ordinary web pages, not that kind of link.' }
  }
  let url: URL
  try {
    url = new URL(text)
  } catch {
    return { ok: false, code: 'invalid', reason: 'That is not a web address I can use.' }
  }
  if (url.protocol !== 'https:' && url.protocol !== 'http:') return { ok: false, code: 'blocked', reason: 'I only open ordinary web pages (http or https).' }
  if (url.username || url.password) return { ok: false, code: 'blocked', reason: 'That web address has a name or password hidden inside it, so I will not open it.' }
  const host = url.hostname.toLowerCase()
  if (!host) return { ok: false, code: 'invalid', reason: 'That is not a web address I can use.' }
  if (isLocalHost(host)) {
    const stage = stageOrigin ? safeOrigin(stageOrigin) : null
    if (!stage || url.origin !== stage) return { ok: false, code: 'blocked', reason: 'That address points at this computer or a private network, so I will not open it.' }
    return { ok: true, url, secure: false, host }
  }
  if (/^\d{1,3}(?:\.\d{1,3}){3}$/.test(host) || host.includes(':') || /^0x[0-9a-f]+$/i.test(host) || /^\d+$/.test(host)) {
    return { ok: false, code: 'blocked', reason: 'That address is a bare number instead of a website name, so I will not open it.' }
  }
  if (host.split('.').some((label) => label.startsWith('xn--'))) {
    return { ok: false, code: 'blocked', reason: 'That website name uses look-alike letters, which scammers use, so I will not open it.' }
  }
  if (!host.includes('.')) return { ok: false, code: 'invalid', reason: 'That is not a full website name.' }
  return { ok: true, url, secure: url.protocol === 'https:', host }
}

function safeOrigin(origin: string): string | null {
  try {
    return new URL(origin).origin
  } catch {
    return null
  }
}

// ---------- file rules ----------

// The real location of a path: symlinks resolved on the deepest part that exists, the rest kept as written.
function realLocation(p: string): string {
  const rest: string[] = []
  let cur = p
  for (;;) {
    try {
      return path.join(realpathSync(cur), ...rest.reverse())
    } catch {
      const parent = path.dirname(cur)
      if (parent === cur) return p
      rest.push(path.basename(cur))
      cur = parent
    }
  }
}

export function checkPath(raw: string, roots: string[], home: string): { ok: true; path: string } | { ok: false; reason: string } {
  const p = raw.trim()
  if (!p.startsWith('/') || p.includes('\0') || p.length > 1000) return { ok: false, reason: 'I need the full location of the file.' }
  if (p.split('/').includes('..')) return { ok: false, reason: 'That location is not allowed.' }
  const norm = p.replace(/\/+$/, '') || '/'
  const allowed = (roots.length ? roots : [home]).map((r) => r.replace(/\/+$/, ''))
  // Scope is judged at the REAL location (symlinks resolved) for both the file and the folders; the real name must not be sensitive.
  const real = realLocation(norm)
  const realRoots = allowed.map((r) => realLocation(r))
  if (!realRoots.some((r) => real === r || real.startsWith(`${r}/`))) return { ok: false, reason: 'That file is outside the folders you shared with me.' }
  for (const candidate of new Set([norm, real])) {
    if (SENSITIVE_PATH.test(candidate) || SENSITIVE_NAME.test(candidate.split('/').pop() ?? '')) return { ok: false, reason: 'That file may hold private information, so I leave it alone.' }
  }
  return { ok: true, path: norm }
}

// ---------- action evaluation ----------

// Words that make any action high risk, from the label / target text / typed text.
export function riskWords(...texts: (string | undefined)[]): string | null {
  const deny = denylistMatch(...texts)
  if (deny) return deny
  for (const t of texts) {
    if (!t) continue
    const m = EXTRA_BLOCK.exec(t)
    if (m) return m[0].replace(/^[^a-z0-9]/i, '').toLowerCase()
  }
  return null
}

// ---------- goal text: negated clauses ----------

// "do not sign in or submit anything", "never click Agree", "without paying", "avoid the ads", "leave any cookie banner alone":
// a clause the person wrote to RULE OUT something must not make the goal itself look like that thing. Each negation removes
// text up to the next period / semicolon / ", and" / ", then" / ", but" (or the end). Only the GOAL scan uses this; the
// label, target-text and typed-text scans never do. "never mind" is not a negation of the next words.
const NEGATED_CLAUSE =
  /(?:\b(?:do\s+not|don['’]t|do\s*n['’]t|never(?!\s+mind)|without|avoid|avoiding)\b|\bleave\b(?=[^.;]*\balone\b))[^.;]*?(?=,\s*(?:and|then|but)\b|[.;]|$)/gi

export function stripNegatedClauses(goal: string): string {
  return goal.replace(NEGATED_CLAUSE, ' ').replace(/\s+/g, ' ').trim()
}

// Privacy-preserving banner options: clicking these only DECLINES or hides the banner, so the consent words in their label
// (cookies, consent) do not block them. A label that also says accept / agree / allow is never one of them.
const PRIVACY_OPTION = /\b(?:decline|reject|reject\s+all|no\s+thanks|no,?\s+thank\s+you|only\s+(?:necessary|essential)|(?:necessary|essential)\s+only|dismiss|close|not\s+now|deny|refuse|continue\s+without\s+accepting)\b/i
const POSITIVE_CONSENT = /\b(?:accept|agree|allow|permit|enable|grant|yes|ok|okay|got\s+it)\b/i
export const isPrivacyOption = (label: string | undefined): boolean => !!label && PRIVACY_OPTION.test(label) && !POSITIVE_CONSENT.test(label)
// Wording that is only about consent (cookie banners).
const CONSENT_WORDS_RE = /\b(?:accept(?:ing)?(?:\s+all)?|allow(?:\s+all)?|i\s+agree|agree|consent|cookies?)\b/gi
const CONSENT_CONTEXT = /cookie|consent|banner|privacy/i
// "accept the cookies", "agree to cookies", "allow all cookies" in the GOAL: the person asked for it.
const GOAL_ACCEPTS_COOKIES = /\b(?:accept|agree\s+to|allow)(?:\s+(?:all|the|any|these|those|our|their))*\s+(?:cookies?|cookie\s+banner|consent)\b/gi
export const goalAcceptsCookies = (goal: string): boolean => {
  GOAL_ACCEPTS_COOKIES.lastIndex = 0
  return GOAL_ACCEPTS_COOKIES.test(stripNegatedClauses(goal))
}

// Consent / cookie words: the person's own choice, never made for them.
const CONSENT_WORD = /^(?:agree|i\s+agree|consent|cookie|allow\s+all|accept\s+all)/i
export const isConsentWord = (word: string): boolean => CONSENT_WORD.test(word.trim())

export function typedTextProblem(text: string, stageOrigin?: string): string | null {
  if (text.length > MAX_TYPED_CHARS) return 'that is too much text to type for someone'
  const word = riskWords(text)
  if (word) return `the text mentions "${word}"`
  if (SECRET_WORDS.test(text)) return 'the text looks like a password or account number'
  if (CARD_LIKE.test(text) || LONG_DIGITS.test(text)) return 'the text looks like a card, code or account number'
  const urlLike = text.match(/[a-z][a-z0-9+.-]*:\/\/\S+|(?:javascript|data|file):\S+/i)
  if (urlLike) {
    const check = checkUrl(urlLike[0], stageOrigin)
    if (!check.ok) return 'the text contains a link I would not open'
  }
  return null
}

export function appProblem(name: string): string | null {
  const n = name.trim()
  if (!APP_NAME_OK.test(n)) return 'That is not an app name I can use.'
  const lower = n.toLowerCase()
  if (BLOCKED_APPS.some((a) => lower === a || lower.includes(a))) return `I will not open ${n} for you: it can change things on your computer.`
  return null
}

function baseRisk(action: ProposedAction, ctx: PolicyContext, returnOk = false): Risk {
  if (returnOk && ctx.agency === 'ask_per_task' && ctx.planApproved) return 'low'
  // Plain typed text that already passed every text scan is part of the plan the learner approved (ask_per_task).
  if (action.kind === 'type' && ctx.agency === 'ask_per_task' && ctx.planApproved) return 'low'
  switch (action.kind) {
    case 'click':
    case 'double_click':
    case 'scroll':
    case 'wait':
    case 'open_url':
      return 'low'
    default:
      return 'medium'
  }
}

export function evaluateGoal(goal: string, ctx: PolicyContext): PolicyDecision {
  const gate = baseGate(ctx)
  if (gate) return gate
  let text = stripNegatedClauses(goal)
  // An explicit request to accept cookies is the person's own choice; the rest of the goal is still scanned.
  if (goalAcceptsCookies(goal)) text = text.replace(GOAL_ACCEPTS_COOKIES, ' ')
  const word = riskWords(text)
  if (word && isConsentWord(word)) return blocked(`"${word}" is a consent choice, so I leave it to you. Say "accept the cookies" if you want me to click it, or do it yourself and tell me to carry on.`, [`goal:${word}`])
  if (word) return blocked(`"${word}" could involve money, passwords, messages, deleting things or permissions, so I leave it to you. Do that part yourself; I can help with the steps around it.`, [`goal:${word}`])
  return { allowed: true, ask: true, risk: 'low', reason: 'goal accepted', flags: [] }
}

function baseGate(ctx: PolicyContext): Extract<PolicyDecision, { allowed: false }> | null {
  if (ctx.agency === 'off') return { allowed: false, code: 'agency_off', reason: '"Let me do things for you" is switched off. Teach the learner to do it instead, and tell them they can switch it on in settings.', flags: ['agency_off'] }
  if (ctx.scamContext) return { allowed: false, code: 'scam_check', reason: 'A scam check is in progress, so nothing is done for the learner. Show them where to look.', flags: ['scam_context'] }
  if (ctx.safetyCriticalStep) return { allowed: false, code: 'safety_step', reason: 'This lesson step is safety-critical, so the learner does it themselves. Show them, do not do it.', flags: ['safety_step'] }
  return null
}

export function evaluateAction(action: ProposedAction, ctx: PolicyContext): PolicyDecision {
  const gate = baseGate(ctx)
  if (gate) return gate
  const flags: string[] = []

  if (action.secureField) return blocked('That is a password or secure box, so I never type into it. I will leave it to you.', ['secure_field'])

  // Return is blocked unless the narrow allowance holds. When it does, the model's own words may say "submit the search":
  // that one word is ignored for the label scan only; every other denylist word still blocks.
  const isReturn = action.kind === 'keys' && ['return', 'enter'].includes(normaliseKeys(action.value ?? ''))
  let returnOk = false
  if (isReturn) {
    const why = returnAfterTypeProblem(ctx)
    if (why) return blocked(why, ['keys', 'return'])
    returnOk = true
    flags.push('return-after-type')
  }
  const unSubmit = (t?: string): string | undefined => (returnOk && t ? t.replace(/\bsubmit\w*/gi, ' ') : t)
  // A banner option that only declines or hides (No thanks, Reject all, Only necessary, Dismiss, Close, Not now): the consent words
  // in its label are fine. With an explicit "accept cookies" goal, consent wording passes too. Every other word still blocks.
  const declineBanner = (action.kind === 'click' || action.kind === 'double_click') && isPrivacyOption(action.label)
  const consentOk = declineBanner || (ctx.goalAcceptsCookies === true && (action.kind === 'click' || action.kind === 'double_click') && CONSENT_CONTEXT.test(`${action.label ?? ''} ${action.targetText ?? ''}`))
  const forScan = (t?: string): string | undefined => {
    const u = unSubmit(t)
    return consentOk && u ? u.replace(CONSENT_WORDS_RE, ' ') : u
  }

  // The hard denylist applies to the grounded label, the target text and any typed text.
  const word = riskWords(forScan(action.label), forScan(action.targetText), action.kind === 'type' ? action.text : undefined)
  if (word && isConsentWord(word)) return blocked(`"${word}" is a consent choice, so I leave consent choices to you. I did not click it: choose it yourself, or tell me to pick "No thanks" or "Reject all" instead.`, [`word:${word}`, 'consent'])
  if (word) return blocked(`"${word}" could involve money, passwords, messages, deleting things or permissions, so I leave it to you. I did not do it: please do that step yourself, then tell me to carry on.`, [`word:${word}`])

  switch (action.kind) {
    case 'open_url': {
      const check = checkUrl(action.value ?? '', ctx.stageOrigin)
      if (!check.ok) return blocked(check.reason, ['url'], check.code)
      if (!check.secure && !isLocalHost(check.host)) flags.push('http_not_https')
      break
    }
    case 'open_app': {
      const problem = appProblem(action.value ?? '')
      if (problem) return blocked(problem, ['app'], APP_NAME_OK.test((action.value ?? '').trim()) ? 'blocked' : 'invalid')
      break
    }
    case 'open_file': {
      const check = checkPath(action.value ?? '', ctx.fileRoots ?? [], ctx.homeDir ?? '/Users')
      if (!check.ok) return blocked(check.reason, ['path'])
      break
    }
    case 'open_settings': {
      if (!resolvePane(action.value)) return blocked('I can only take you to display, text size, sound, Wi-Fi and similar everyday settings, not privacy or account settings.', ['pane'])
      break
    }
    case 'type': {
      const text = action.text ?? ''
      if (!text.trim()) return blocked('There is nothing to type.', ['empty'], 'invalid')
      const problem = typedTextProblem(text, ctx.stageOrigin)
      if (problem) return blocked(`I will not type that: ${problem}.`, ['typed_text'])
      break
    }
    case 'keys': {
      const combo = normaliseKeys(action.value ?? '')
      if (!KEY_ALLOWLIST.has(combo)) return blocked('That key combination is not one I use.', ['keys'])
      break
    }
    case 'click':
    case 'double_click':
    case 'scroll':
    case 'wait':
      break
  }

  let risk = baseRisk(action, ctx, returnOk)
  if (CONFIRM_WORDS.test(`${action.label ?? ''} ${action.targetText ?? ''}`)) {
    flags.push('send_shaped')
    risk = 'medium'
  }
  if (action.confidence !== undefined && action.confidence < LOW_CONFIDENCE) {
    flags.push('low_confidence')
    risk = 'medium'
  }
  if (flags.includes('http_not_https')) risk = 'medium'

  // Tier decision. ask_each confirms everything; ask_per_task lets low-risk, plan-covered actions through.
  const ask = ctx.agency === 'ask_each' || ctx.agency === 'autonomous' || risk !== 'low' || !ctx.planApproved
  return { allowed: true, ask, risk, reason: ask ? 'ask the learner first' : 'covered by the confirmed plan', flags }
}

// ---------- rate / step limits ----------

export class ActionLimiter {
  private last = Number.NEGATIVE_INFINITY
  private count = 0
  private readonly recent: number[] = []

  // maxPerTask applies to one task (act_for_me); maxPerMinute is a global backstop against a runaway model.
  constructor(
    private readonly maxPerTask = MAX_ACTIONS_PER_TASK,
    private readonly gapMs = MIN_ACTION_GAP_MS,
    private readonly maxPerMinute = 16,
  ) {}

  // ok:true => the caller may act now (the action is counted). wait => retry the SAME check after waitMs (never the action).
  take(now: number): { ok: true } | { ok: false; why: 'gap'; waitMs: number } | { ok: false; why: 'task_limit' | 'minute_limit' } {
    if (this.count >= this.maxPerTask) return { ok: false, why: 'task_limit' }
    while (this.recent.length && now - this.recent[0] > 60_000) this.recent.shift()
    if (this.recent.length >= this.maxPerMinute) return { ok: false, why: 'minute_limit' }
    const wait = this.last + this.gapMs - now
    if (wait > 0) return { ok: false, why: 'gap', waitMs: Math.ceil(wait) }
    this.last = now
    this.count++
    this.recent.push(now)
    return { ok: true }
  }

  get used(): number {
    return this.count
  }
}
