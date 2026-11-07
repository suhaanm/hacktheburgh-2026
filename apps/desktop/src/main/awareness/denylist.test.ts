import { describe, expect, it } from 'vitest'
import { appKindFor, decideApp, describeDenylist, workerListMatches } from './denylist'

const strict = { strict: true, workerList: [] as string[] }
const lax = { strict: false, workerList: [] as string[] }

describe('always denied', () => {
  it.each([
    ['com.1password.1password', 'password_manager'],
    ['com.agilebits.onepassword7', 'password_manager'],
    ['com.bitwarden.desktop', 'password_manager'],
    ['com.apple.keychainaccess', 'password_manager'],
    ['com.apple.Passwords', 'password_manager'],
    ['org.keepassxc.keepassxc', 'password_manager'],
    ['com.apple.SecurityAgent', 'system_auth'],
    ['com.apple.loginwindow', 'system_auth'],
    ['com.intuit.quicken', 'finance'],
  ])('%s is denied as %s, strict or not, and case does not matter', (id, category) => {
    expect(decideApp(id, appKindFor(id), lax)).toEqual({ verdict: 'deny', category })
    expect(decideApp(id.toUpperCase(), 'other', strict)).toEqual({ verdict: 'deny', category })
  })
})

describe('strict mode', () => {
  it.each(['com.apple.MobileSMS', 'com.apple.mail', 'com.tinyspeck.slackmacgap', 'net.whatsapp.WhatsApp', 'org.whispersystems.signal-desktop', 'com.microsoft.teams2', 'com.microsoft.Outlook'])(
    '%s is denied in strict mode and allowed when strict is off',
    (id) => {
      expect(decideApp(id, appKindFor(id), strict).verdict).toBe('deny')
      expect(decideApp(id, appKindFor(id), lax).verdict).toBe('allow')
    },
  )

  it('an app of kind chat or email is denied in strict mode even when its id is not in the list', () => {
    expect(decideApp('com.example.newchat', 'chat', strict)).toEqual({ verdict: 'deny', category: 'messaging' })
    expect(decideApp('com.example.newmail', 'email', strict)).toEqual({ verdict: 'deny', category: 'mail' })
    expect(decideApp('com.example.newchat', 'chat', lax).verdict).toBe('allow')
  })

  it('an unreadable app is unknown (the caller decides: strict means no glance), never guessed', () => {
    expect(decideApp(null, null, strict)).toEqual({ verdict: 'unknown' })
    expect(decideApp('  ', 'unknown', lax)).toEqual({ verdict: 'unknown' })
  })

  it('ordinary apps are allowed', () => {
    for (const id of ['com.apple.Safari', 'com.microsoft.Excel', 'com.microsoft.VSCode', 'com.apple.Terminal', 'com.figma.Desktop']) {
      expect(decideApp(id, appKindFor(id), strict).verdict).toBe('allow')
    }
  })
})

describe('the worker list', () => {
  it('adds to the defaults, exact or by prefix, and never replaces them', () => {
    const o = { strict: false, workerList: ['com.example.secret', 'com.acme.*'] }
    expect(decideApp('com.example.secret', 'other', o)).toEqual({ verdict: 'deny', category: 'worker_list' })
    expect(decideApp('com.acme.thing', 'other', o)).toEqual({ verdict: 'deny', category: 'worker_list' })
    expect(decideApp('com.acmeish.thing', 'other', o).verdict).toBe('allow') // the prefix ends at the dot
    expect(decideApp('com.1password.1password', 'other', o)).toEqual({ verdict: 'deny', category: 'password_manager' })
    expect(workerListMatches('com.x.y', ['COM.X.Y'])).toBe(true)
  })
})

describe('appKindFor', () => {
  it.each([
    ['com.apple.Safari', 'browser'],
    ['com.google.Chrome', 'browser'],
    ['company.thebrowser.Browser', 'browser'],
    ['com.microsoft.Excel', 'spreadsheet'],
    ['com.apple.iWork.Numbers', 'spreadsheet'],
    ['com.apple.mail', 'email'],
    ['com.microsoft.VSCode', 'code_editor'],
    ['com.jetbrains.intellij', 'code_editor'],
    ['com.apple.Terminal', 'terminal'],
    ['com.googlecode.iterm2', 'terminal'],
    ['com.tinyspeck.slackmacgap', 'chat'],
    ['com.apple.MobileSMS', 'chat'],
    ['com.figma.Desktop', 'other'],
  ])('%s is %s', (id, kind) => expect(appKindFor(id)).toBe(kind))

  it('no bundle id is unknown, not other', () => {
    expect(appKindFor(null)).toBe('unknown')
    expect(appKindFor('')).toBe('unknown')
  })

  it('describeDenylist lists ids and prefixes for the Privacy screen', () => {
    const d = describeDenylist()
    expect(d.always.password_manager).toContain('com.1password.*')
    expect(d.strict.messaging).toContain('com.apple.mobilesms')
  })
})
