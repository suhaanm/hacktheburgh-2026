import { describe, expect, it } from 'vitest'
import { createConsoleProbe, createFrontmostSource, createScreenShareProbe, parseBundleId, parseConsoleState, parseScreenShare, type Exec } from './probes'

// The "off" form below is the shape `ioreg -r -k IOConsoleUsers -d 1 -w 0` printed on the build Mac (user name replaced).
const IOREG_OFF = `+-o Root  <class IORegistryEntry, id 0x100000100, retain 35>
    {
      "IOKitBuildVersion" = "Darwin Kernel Version 25.2.0"
      "IOConsoleLocked" = No
      "IOConsoleUsers" = ({"kCGSSessionOnConsoleKey"=Yes,"kSCSecuritySessionID"=100022,"kCGSSessionSystemSafeBoot"=No,"kCGSessionLoginDoneKey"=Yes,"kCGSSessionIDKey"=257,"kCGSSessionUserNameKey"="canary_user_name","kCGSSessionGroupIDKey"=20,"CGSSessionUniqueSessionUUID"="D3317EB6-0000-0000-0000-19F1FEC07000","kCGSessionLongUserNameKey"="Canary Longname","kCGSSessionAuditIDKey"=100022,"kCGSSessionLoginwindowSafeLogin"=No,"kCGSSessionUserIDKey"=502})
    }
+-o IOResources  <class IOResources, id 0x10000029c, registered, matched, active, busy 0 (10879 ms), retain 104>
`
// The "on" form is constructed from the documented behaviour: the console entry gains kCGSSessionSecureInputPID.
const IOREG_ON = IOREG_OFF.replace('"kCGSSessionUserIDKey"=502}', '"kCGSSessionUserIDKey"=502,"kCGSSessionSecureInputPID"=48211}')
const IOREG_LOCKED = IOREG_OFF.replace('"IOConsoleLocked" = No', '"IOConsoleLocked" = Yes')

describe('frontmost app', () => {
  it('parses the bundle id from lsappinfo output and nothing else', () => {
    expect(parseBundleId('"CFBundleIdentifier"="com.anthropic.claudefordesktop"\n')).toBe('com.anthropic.claudefordesktop')
    expect(parseBundleId('"CFBundleIdentifier"=[ NULL ]')).toBeNull()
    expect(parseBundleId('')).toBeNull()
    expect(parseBundleId('"CFBundleIdentifier"="has spaces and ; semicolons"')).toBeNull()
    expect(parseBundleId('"CFBundleIdentifier"="' + 'a'.repeat(300) + '"')).toBeNull()
  })

  it('asks Launch Services for the front app with fixed arguments, and returns null on failure', async () => {
    const calls: Array<[string, readonly string[]]> = []
    const ok: Exec = async (f, a) => {
      calls.push([f, a])
      return { stdout: '"CFBundleIdentifier"="com.apple.Safari"' }
    }
    expect(await createFrontmostSource(ok).read()).toBe('com.apple.Safari')
    expect(calls).toEqual([['lsappinfo', ['info', '-only', 'bundleid', '-app', 'front']]])
    const bad: Exec = async () => {
      throw new Error('boom')
    }
    expect(await createFrontmostSource(bad).read()).toBeNull()
  })
})

describe('secure input and console lock', () => {
  it('off, on, locked and unreadable', () => {
    expect(parseConsoleState(IOREG_OFF)).toEqual({ secureInput: 'off', locked: false })
    expect(parseConsoleState(IOREG_ON)).toEqual({ secureInput: 'on', locked: false })
    expect(parseConsoleState(IOREG_LOCKED)).toEqual({ secureInput: 'off', locked: true })
    expect(parseConsoleState('')).toEqual({ secureInput: 'unknown', locked: null })
    expect(parseConsoleState('garbage output')).toEqual({ secureInput: 'unknown', locked: null })
  })

  it('returns only an enum and a boolean: the user name, pid and uuid in the raw output never come out', () => {
    for (const raw of [IOREG_OFF, IOREG_ON, IOREG_LOCKED]) {
      const text = JSON.stringify(parseConsoleState(raw))
      expect(text).not.toMatch(/canary|Longname|48211|D3317EB6|502/)
    }
  })

  it('a probe that cannot run says unknown (strict mode turns that into no glance)', async () => {
    const bad: Exec = async () => {
      throw new Error('ioreg missing')
    }
    expect(await createConsoleProbe(bad).read()).toEqual({ secureInput: 'unknown', locked: null })
    const calls: Array<readonly string[]> = []
    const ok: Exec = async (_f, a) => {
      calls.push(a)
      return { stdout: IOREG_ON }
    }
    expect((await createConsoleProbe(ok).read()).secureInput).toBe('on')
    expect(calls[0]).toEqual(['-r', '-k', 'IOConsoleUsers', '-d', '1', '-w', '0'])
  })
})

describe('screen sharing (heuristic)', () => {
  it('matches only exact helper names, by basename', () => {
    expect(parseScreenShare('/Applications/zoom.us.app/Contents/Frameworks/CptHost.app/Contents/MacOS/CptHost\n')).toBe(true)
    expect(parseScreenShare('/System/Library/CoreServices/RemoteManagement/screensharingd.bundle/Contents/MacOS/screensharingd')).toBe(true)
    // seen running all the time on the build Mac: not sharing
    expect(parseScreenShare('/System/Library/PrivateFrameworks/RemoteManagement.framework/XPCServices/ScreenSharingSubscriber.xpc/Contents/MacOS/ScreenSharingSubscriber')).toBe(false)
    expect(parseScreenShare('Core Audio Driver (ZoomAudioDevice.driver)')).toBe(false)
    expect(parseScreenShare('/sbin/launchd\n/usr/libexec/logd')).toBe(false)
  })

  it('returns null when the process list cannot be read', async () => {
    const bad: Exec = async () => {
      throw new Error('x')
    }
    expect(await createScreenShareProbe(bad).read()).toBeNull()
    expect(await createScreenShareProbe(async () => ({ stdout: '/sbin/launchd' })).read()).toBe(false)
  })
})
