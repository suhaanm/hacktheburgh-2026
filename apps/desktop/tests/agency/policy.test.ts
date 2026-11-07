import { describe, expect, it } from 'vitest'
import { coerceSettings, reconcileAgency } from '../../src/shared/settings'
import { ActionLimiter, checkPath, checkUrl, evaluateAction, evaluateGoal, resolvePane, typedTextProblem, type PolicyContext, type ProposedAction } from '../../src/main/agency/policy'

const STAGE = 'http://127.0.0.1:5180'
const ctx = (over: Partial<PolicyContext> = {}): PolicyContext => ({ agency: 'ask_each', safetyCriticalStep: false, scamContext: false, planApproved: false, stageOrigin: STAGE, fileRoots: [], homeDir: '/Users/lily', ...over })
const verdict = (a: ProposedAction, over: Partial<PolicyContext> = {}) => evaluateAction(a, ctx(over))

describe('tiers', () => {
  const everyKind: ProposedAction[] = [
    { kind: 'open_url', value: 'https://www.ageuk.org.uk' },
    { kind: 'open_app', value: 'Safari' },
    { kind: 'open_file', value: '/Users/lily/Documents/a.pdf' },
    { kind: 'open_settings', value: 'displays' },
    { kind: 'click', label: 'Start call' },
    { kind: 'double_click', label: 'Photos' },
    { kind: 'type', text: 'weather' },
    { kind: 'keys', value: 'tab' },
    { kind: 'scroll', label: 'page' },
    { kind: 'wait' },
  ]
  it.each(everyKind.map((a) => [a.kind, a] as const))('agency off refuses %s', (_k, a) => {
    const d = verdict(a, { agency: 'off' })
    expect(d.allowed).toBe(false)
    if (!d.allowed) expect(d.code).toBe('agency_off')
  })
  it.each(everyKind.map((a) => [a.kind, a] as const))('ask_each asks before %s', (_k, a) => {
    const d = verdict(a)
    expect(d.allowed).toBe(true)
    if (d.allowed) expect(d.ask).toBe(true)
  })
  it('ask_per_task: low-risk actions run once the plan is approved, anything else still asks', () => {
    const per = (a: ProposedAction, planApproved = true) => verdict(a, { agency: 'ask_per_task', planApproved })
    for (const a of [{ kind: 'click', label: 'Start call' }, { kind: 'scroll', label: 'page' }, { kind: 'double_click', label: 'Photos' }] as ProposedAction[]) {
      const d = per(a)
      expect(d.allowed && d.ask).toBe(false)
    }
    for (const a of [{ kind: 'keys', value: 'tab' }, { kind: 'open_app', value: 'Safari' }, { kind: 'click', label: 'Reply' }, { kind: 'click', label: 'Start call', confidence: 0.4 }] as ProposedAction[]) {
      const d = per(a)
      expect(d.allowed && d.ask).toBe(true)
    }
    // plain scanned text typed under an approved plan is part of the plan; unapproved, or send-shaped, it still asks
    const typed = per({ kind: 'type', text: 'weather' })
    expect(typed.allowed && typed.ask).toBe(false)
    const typedUnplanned = per({ kind: 'type', text: 'weather' }, false)
    expect(typedUnplanned.allowed && typedUnplanned.ask).toBe(true)
    const typedLow = per({ kind: 'type', text: 'weather', confidence: 0.4 })
    expect(typedLow.allowed && typedLow.ask).toBe(true)
    const unplanned = per({ kind: 'click', label: 'Start call' }, false)
    expect(unplanned.allowed && unplanned.ask).toBe(true)
  })
  it('refuses during a scam check and on safety-critical steps, in every tier', () => {
    for (const agency of ['ask_each', 'ask_per_task'] as const) {
      const a = verdict({ kind: 'click', label: 'Start call' }, { agency, scamContext: true })
      const b = verdict({ kind: 'click', label: 'Start call' }, { agency, safetyCriticalStep: true })
      expect(!a.allowed && a.code).toBe('scam_check')
      expect(!b.allowed && b.code).toBe('safety_step')
    }
  })
  it('refuses a goal for the same reasons', () => {
    expect(evaluateGoal('turn the volume down', ctx()).allowed).toBe(true)
    expect(evaluateGoal('turn the volume down', ctx({ agency: 'off' })).allowed).toBe(false)
    expect(evaluateGoal('turn the volume down', ctx({ scamContext: true })).allowed).toBe(false)
  })
})

describe('hard denylist', () => {
  const bad = ['Pay now', 'Buy', 'Purchase', 'Place order', 'Checkout', 'Send', 'Submit', 'Delete', 'Remove', 'Erase', 'Transfer', 'Confirm', 'Sign in', 'Log in', 'Password', 'Card number', 'Allow', 'Grant access', 'Install', 'Accept all', 'Subscribe', 'Wipe disk', 'Enter 2FA code', 'Security & Privacy']
  it.each(bad)('blocks a click labelled %s', (label) => {
    expect(verdict({ kind: 'click', label }).allowed).toBe(false)
  })
  it.each(bad)('blocks when only the target text says %s', (label) => {
    expect(verdict({ kind: 'click', label: 'the button', targetText: label }).allowed).toBe(false)
  })
  it.each(['Start call', 'Settings', 'Bigger text', 'Photos', 'Messages', 'Join', 'Open', 'Next'])('allows a click labelled %s', (label) => {
    expect(verdict({ kind: 'click', label }).allowed).toBe(true)
  })
  it('never types into a secure field', () => {
    const d = verdict({ kind: 'type', text: 'hello', secureField: true })
    expect(!d.allowed && d.flags).toContain('secure_field')
  })
  it('refuses a goal that is about money, passwords, messages or deleting', () => {
    for (const g of ['pay my gas bill', 'log in to my email', 'send this to my son', 'delete my photos', 'buy shoes']) expect(evaluateGoal(g, ctx()).allowed).toBe(false)
  })
})

describe('typed text', () => {
  const bad: Array<[string, string]> = [
    ['password hunter2', 'password'],
    ['my pin code is 4412', 'pin'],
    ['4111 1111 1111 1111', 'card'],
    ['123456', 'digits'],
    ['sort code 12-34-56', 'sort'],
    ['javascript:alert(1)', 'js url'],
    ['https://user:pw@example.com', 'credentials'],
    ['x'.repeat(301), 'length'],
    ['pay the invoice', 'denylist'],
  ]
  it.each(bad)('refuses %s (%s)', (text) => {
    expect(typedTextProblem(text, STAGE)).not.toBeNull()
    expect(verdict({ kind: 'type', text }).allowed).toBe(false)
  })
  it.each(['weather in London', 'ageuk.org.uk', 'how do I make text bigger', 'https://www.ageuk.org.uk'])('allows %s', (text) => {
    expect(typedTextProblem(text, STAGE)).toBeNull()
  })
  it('refuses empty text', () => {
    expect(verdict({ kind: 'type', text: '  ' }).allowed).toBe(false)
  })
})

describe('urls', () => {
  const ok = ['https://www.ageuk.org.uk', 'https://www.google.com/search?q=bigger+text', 'http://example.com/page', 'https://sub.example.co.uk:8443/a?b=c#d', STAGE, `${STAGE}/index.html`]
  it.each(ok)('allows %s', (u) => expect(checkUrl(u, STAGE).ok).toBe(true))
  const bad = [
    'javascript:alert(1)',
    'JAVASCRIPT:alert(1)',
    'data:text/html,<script>1</script>',
    'file:///etc/passwd',
    'ftp://example.com',
    'vbscript:msgbox',
    'mailto:a@b.com',
    'x-apple.systempreferences:com.apple.preference.security',
    'https://user:pass@example.com',
    'https://user@example.com',
    'http://localhost:3000',
    'http://127.0.0.1:8080',
    'http://127.0.0.1:5181',
    'https://192.168.1.1',
    'http://10.0.0.5/admin',
    'http://169.254.169.254/latest',
    'http://[::1]:5180',
    'https://203.0.113.9',
    'https://0x7f000001',
    'https://xn--pple-43d.com',
    'https://printer.local',
    'https://localhost',
    'https://nodots',
    'https://exa mple.com',
    'https://example.com/\nfoo',
    '',
    'not a url',
    `https://example.com/${'a'.repeat(2100)}`,
  ]
  it.each(bad)('refuses %s', (u) => expect(checkUrl(u, STAGE).ok).toBe(false))
  it('localhost is refused when no stage origin is configured', () => {
    expect(checkUrl(STAGE).ok).toBe(false)
  })
  it('flags plain http on a public site as medium risk', () => {
    const d = verdict({ kind: 'open_url', value: 'http://example.com' })
    expect(d.allowed && d.flags).toContain('http_not_https')
    expect(d.allowed && d.risk).toBe('medium')
  })
  it('denylist words in a search URL do not block opening a search page', () => {
    expect(verdict({ kind: 'open_url', value: 'https://www.google.com/search?q=how+to+send+a+photo' }).allowed).toBe(true)
  })
})

describe('apps, files, settings panes, keys', () => {
  it.each(['Safari', 'Google Chrome', 'Zoom', 'FaceTime', 'Photos'])('opens %s', (name) => expect(verdict({ kind: 'open_app', value: name }).allowed).toBe(true))
  it.each(['Terminal', 'iTerm', 'Script Editor', 'Keychain Access', 'System Settings', 'Safari; rm -rf /', '../../bin/sh', '-a', '', 'Activity Monitor'])('refuses app %s', (name) => expect(verdict({ kind: 'open_app', value: name }).allowed).toBe(false))

  it('files: inside the consented folders only, nothing sensitive', () => {
    expect(checkPath('/Users/lily/Documents/bill.pdf', [], '/Users/lily').ok).toBe(true)
    expect(checkPath('/Users/lily/Documents/bill.pdf', ['/Users/lily/Documents'], '/Users/lily').ok).toBe(true)
    expect(checkPath('/Users/lily/Pictures/a.jpg', ['/Users/lily/Documents'], '/Users/lily').ok).toBe(false)
    for (const p of ['/Users/lily/.ssh/id_rsa', '/Users/lily/Documents/../.ssh/x', 'relative/path', '/etc/passwd', '/Users/lily/Library/Keychains/login.keychain-db', '/Users/lily/Documents/passwords.txt', '/Users/lily/.env']) {
      expect(checkPath(p, [], '/Users/lily').ok).toBe(false)
    }
    expect(checkPath('/Users/lilyevil/x', [], '/Users/lily').ok).toBe(false)
  })
  it('settings panes: everyday only, with friendly aliases', () => {
    expect(resolvePane('displays')).toBe('displays')
    expect(resolvePane('Text size')).toBe('accessibility-display')
    expect(resolvePane('wi-fi')).toBe('wifi')
    for (const p of ['privacy', 'microphone', 'accessibility-privacy', 'passwords', 'apple id', '']) expect(verdict({ kind: 'open_settings', value: p }).allowed).toBe(false)
  })
  it('keys: allowlist only; Return is blocked unless the narrow after-typing allowance holds (see return-after-type.test.ts)', () => {
    for (const k of ['Tab', 'escape', 'space', 'Up Arrow', 'Command+L', 'cmd+t', 'cmd+w', 'cmd+f']) expect(verdict({ kind: 'keys', value: k }).allowed).toBe(true)
    for (const k of ['cmd+q', 'cmd+shift+4', 'ctrl+c', 'f5', 'cmd+space', 'delete', '']) expect(verdict({ kind: 'keys', value: k }).allowed).toBe(false)
    const d = verdict({ kind: 'keys', value: 'return' })
    expect(d.allowed).toBe(false)
    expect(!d.allowed && d.reason).toMatch(/straight after typing a plain search/)
  })
})

describe('rate and step limits', () => {
  it('needs 1.5 s between actions and allows 12 per task', () => {
    const l = new ActionLimiter()
    expect(l.take(0)).toEqual({ ok: true })
    expect(l.take(1000)).toEqual({ ok: false, why: 'gap', waitMs: 500 })
    let t = 1500
    for (let i = 1; i < 12; i++, t += 1500) expect(l.take(t)).toEqual({ ok: true })
    expect(l.used).toBe(12)
    expect(l.take(t + 5000)).toEqual({ ok: false, why: 'task_limit' })
  })
  it('a runaway caller hits the per-minute backstop', () => {
    const l = new ActionLimiter(1000, 1500, 12)
    let t = 0
    for (let i = 0; i < 12; i++, t += 1500) expect(l.take(t).ok).toBe(true)
    expect(l.take(t)).toEqual({ ok: false, why: 'minute_limit' })
    expect(l.take(t + 61_000).ok).toBe(true)
  })
  it('a refused take does not use up a slot', () => {
    const l = new ActionLimiter()
    l.take(0)
    l.take(100)
    expect(l.used).toBe(1)
  })
})

describe('agency setting', () => {
  it('keeps doItForMeAllowed = agency !== off', () => {
    expect(reconcileAgency({ agency: 'off' }, { agency: 'ask_each' })).toMatchObject({ agency: 'ask_each', doItForMeAllowed: true })
    expect(reconcileAgency({ agency: 'ask_each' }, { agency: 'off' })).toMatchObject({ agency: 'off', doItForMeAllowed: false })
    expect(reconcileAgency({ agency: 'off' }, { doItForMeAllowed: true })).toMatchObject({ agency: 'ask_per_task', doItForMeAllowed: true })
    expect(reconcileAgency({ agency: 'ask_per_task' }, { doItForMeAllowed: true })).toMatchObject({ agency: 'ask_per_task' })
    expect(reconcileAgency({ agency: 'ask_each' }, { doItForMeAllowed: false })).toMatchObject({ agency: 'off' })
    expect(reconcileAgency({ agency: 'ask_each' }, { captions: false })).toEqual({ captions: false })
  })
  it('defaults to ask_per_task and reads older files', () => {
    expect(coerceSettings({}).agency).toBe('ask_per_task')
    expect(coerceSettings({}).doItForMeAllowed).toBe(true)
    expect(coerceSettings({ doItForMeAllowed: true })).toMatchObject({ agency: 'ask_per_task', doItForMeAllowed: true })
    expect(coerceSettings({ agency: 'ask_per_task' })).toMatchObject({ agency: 'ask_per_task', doItForMeAllowed: true })
    expect(coerceSettings({ agency: 'nonsense' })).toMatchObject({ agency: 'ask_per_task', doItForMeAllowed: true })
  })
})
