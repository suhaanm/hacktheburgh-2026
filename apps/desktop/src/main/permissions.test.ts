import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  media: { microphone: 'granted', screen: 'granted' } as Record<string, string>,
  trusted: false,
  askForMediaAccess: vi.fn(async (_kind: string) => true),
  isTrustedAccessibilityClient: vi.fn((_prompt: boolean) => false),
  getMediaAccessStatus: vi.fn((kind: string) => 'unknown'),
  getSources: vi.fn(async (_opts: unknown) => [] as { thumbnail: { isEmpty(): boolean } }[]),
  openExternal: vi.fn(async (_url: string) => undefined),
  relaunch: vi.fn(),
  exit: vi.fn(),
  isPackaged: false,
}))

vi.mock('electron', () => ({
  app: {
    get isPackaged() {
      return mocks.isPackaged
    },
    relaunch: mocks.relaunch,
    exit: mocks.exit,
  },
  desktopCapturer: { getSources: mocks.getSources },
  shell: { openExternal: mocks.openExternal },
  systemPreferences: {
    getMediaAccessStatus: mocks.getMediaAccessStatus,
    askForMediaAccess: mocks.askForMediaAccess,
    isTrustedAccessibilityClient: mocks.isTrustedAccessibilityClient,
  },
}))

import { IPC } from '../shared/ipc'
import { buildPermissionHint, createPermissions, findLaunchingApp, probeScreenCapture } from './permissions'
import type { PermissionSender } from './permissions'

const source = (empty = false) => ({ thumbnail: { isEmpty: () => empty } })
const noLog = () => undefined

function make(over: Partial<Parameters<typeof createPermissions>[0]> = {}) {
  return createPermissions({ platform: 'darwin', log: noLog, readProcessTable: async () => '', ...over })
}

function fakeSender(id = 1) {
  const handlers: Record<string, () => void> = {}
  const sender = {
    id,
    destroyed: false,
    isDestroyed() {
      return this.destroyed
    },
    send: vi.fn(),
    once(event: string, cb: () => void) {
      handlers[event] = cb
      return this
    },
  }
  return { sender: sender as unknown as PermissionSender & { destroyed: boolean; send: ReturnType<typeof vi.fn> }, fire: (e: string) => handlers[e]?.() }
}

beforeEach(() => {
  vi.useRealTimers()
  mocks.media.microphone = 'granted'
  mocks.media.screen = 'granted'
  mocks.trusted = false
  mocks.isPackaged = false
  for (const m of [mocks.askForMediaAccess, mocks.isTrustedAccessibilityClient, mocks.getMediaAccessStatus, mocks.getSources, mocks.openExternal, mocks.relaunch, mocks.exit]) m.mockClear()
  mocks.getMediaAccessStatus.mockImplementation((kind: string) => mocks.media[kind] ?? 'unknown')
  mocks.isTrustedAccessibilityClient.mockImplementation(() => mocks.trusted)
  mocks.getSources.mockImplementation(async () => [source()])
  mocks.askForMediaAccess.mockImplementation(async () => true)
})

describe('status', () => {
  it('reports everything granted off macOS without touching Electron', async () => {
    const p = createPermissions({ platform: 'win32', log: noLog })
    expect(await p.status()).toEqual({ microphone: 'granted', screen: 'granted', accessibility: true, probe: 'skipped', needsRestart: false, hint: '' })
    expect(mocks.getMediaAccessStatus).not.toHaveBeenCalled()
    expect(mocks.getSources).not.toHaveBeenCalled()
  })

  it('maps microphone and accessibility from the OS', async () => {
    mocks.media.microphone = 'denied'
    mocks.trusted = true
    const s = await make().status()
    expect(s.microphone).toBe('denied')
    expect(s.accessibility).toBe(true)
    expect(mocks.isTrustedAccessibilityClient).toHaveBeenCalledWith(false)
  })

  it.each([['restricted'], ['not-determined'], ['granted'], ['denied']])('passes %s through', async (value) => {
    mocks.media.microphone = value
    expect((await make().status()).microphone).toBe(value)
  })

  it('maps an unexpected OS value to unknown', async () => {
    mocks.media.microphone = 'something-new'
    expect((await make().status()).microphone).toBe('unknown')
  })

  it('screen is granted when the probe returns sources', async () => {
    const s = await make().status()
    expect(s).toMatchObject({ screen: 'granted', probe: 'ok', needsRestart: false })
  })

  it('screen is granted by an inherited permission even when the OS says denied', async () => {
    mocks.media.screen = 'denied'
    expect(await make().status()).toMatchObject({ screen: 'granted', probe: 'ok' })
  })

  it('OS granted but nothing captured asks for a restart', async () => {
    mocks.getSources.mockImplementation(async () => [])
    const p = createPermissions({ platform: 'darwin', log: noLog, readProcessTable: async () => '', probe: () => probeScreenCapture(1) })
    expect(await p.status()).toMatchObject({ screen: 'unknown', probe: 'empty', needsRestart: true })
  })

  it('OS granted but the probe throws is unknown without a restart prompt', async () => {
    const s = await make({ probe: async () => 'error' }).status()
    expect(s).toMatchObject({ screen: 'unknown', probe: 'error', needsRestart: false })
  })

  it('OS denied and an empty probe stays denied', async () => {
    mocks.media.screen = 'denied'
    expect(await make({ probe: async () => 'empty' }).status()).toMatchObject({ screen: 'denied', probe: 'empty', needsRestart: false })
  })

  it('does not probe (and so never prompts) while the OS says not-determined', async () => {
    mocks.media.screen = 'not-determined'
    const probe = vi.fn(async () => 'ok' as const)
    const p = make({ probe })
    expect(await p.status()).toMatchObject({ screen: 'not-determined', probe: 'skipped' })
    expect(probe).not.toHaveBeenCalled()
    // requestScreen is the one explicit way to trigger the macOS prompt
    expect(await p.requestScreen()).toMatchObject({ screen: 'granted', probe: 'ok' })
    expect(probe).toHaveBeenCalledTimes(1)
  })

  it('caches a good probe for 30 s and a failed one for 4 s', async () => {
    let t = 1000
    const probe = vi.fn<() => Promise<'ok' | 'empty'>>(async () => 'ok')
    const p = make({ probe, now: () => t })
    await p.status()
    t += 29_000
    await p.status()
    expect(probe).toHaveBeenCalledTimes(1)
    t += 2000
    await p.status()
    expect(probe).toHaveBeenCalledTimes(2)

    probe.mockResolvedValue('empty')
    t += 31_000
    await p.status()
    expect(probe).toHaveBeenCalledTimes(3)
    t += 3000
    await p.status()
    expect(probe).toHaveBeenCalledTimes(3)
    t += 2000
    await p.status()
    expect(probe).toHaveBeenCalledTimes(4)
  })

  it('probes again right away when the OS status changes', async () => {
    const probe = vi.fn(async () => 'ok' as const)
    const p = make({ probe })
    await p.status()
    mocks.media.screen = 'denied'
    await p.status()
    expect(probe).toHaveBeenCalledTimes(2)
  })

  it('includes the hint', async () => {
    const s = await make({ readProcessTable: async () => ` 10 5 /System/Applications/Utilities/Terminal.app/Contents/MacOS/Terminal\n ${process.pid} 10 /bin/zsh\n` }).status()
    expect(s.hint).toContain('Terminal')
  })
})

describe('probeScreenCapture', () => {
  it('retries an empty first answer and succeeds', async () => {
    mocks.getSources.mockResolvedValueOnce([]).mockResolvedValueOnce([]).mockResolvedValueOnce([source()])
    expect(await probeScreenCapture()).toBe('ok')
    expect(mocks.getSources).toHaveBeenCalledTimes(3)
    expect(mocks.getSources.mock.calls[0][0]).toMatchObject({ types: ['screen'] })
  })

  it('treats blank thumbnails as no source', async () => {
    mocks.getSources.mockResolvedValue([source(true)])
    expect(await probeScreenCapture()).toBe('empty')
    expect(mocks.getSources).toHaveBeenCalledTimes(3)
  })

  it('reports error when every attempt throws, empty when the last one just came back empty', async () => {
    mocks.getSources.mockRejectedValue(new Error('boom'))
    expect(await probeScreenCapture()).toBe('error')
    mocks.getSources.mockReset()
    mocks.getSources.mockRejectedValueOnce(new Error('boom')).mockRejectedValueOnce(new Error('boom')).mockResolvedValueOnce([])
    expect(await probeScreenCapture()).toBe('empty')
  })
})

describe('requests and links', () => {
  it('asks for microphone access', async () => {
    expect(await make().requestMicrophone()).toBe(true)
    expect(mocks.askForMediaAccess).toHaveBeenCalledWith('microphone')
    mocks.askForMediaAccess.mockResolvedValue(false)
    expect(await make().requestMicrophone()).toBe(false)
  })

  it('does not ask off macOS', async () => {
    expect(await createPermissions({ platform: 'linux', log: noLog }).requestMicrophone()).toBe(true)
    expect(mocks.askForMediaAccess).not.toHaveBeenCalled()
  })

  it('requestAccessibility opens the system prompt and returns the trust state', () => {
    mocks.isTrustedAccessibilityClient.mockReturnValue(true)
    expect(make().requestAccessibility()).toBe(true)
    expect(mocks.isTrustedAccessibilityClient).toHaveBeenCalledWith(true)
  })

  it.each([
    ['screen', 'Privacy_ScreenCapture'],
    ['microphone', 'Privacy_Microphone'],
    ['accessibility', 'Privacy_Accessibility'],
  ] as const)('opens the %s pane', (pane, anchor) => {
    make().openSettings(pane)
    expect(mocks.openExternal).toHaveBeenCalledWith(`x-apple.systempreferences:com.apple.preference.security?${anchor}`)
  })

  it('ignores an unknown pane and does nothing off macOS', () => {
    make().openSettings('keychain' as never)
    createPermissions({ platform: 'win32', log: noLog }).openSettings('screen')
    expect(mocks.openExternal).not.toHaveBeenCalled()
  })

  it('relaunch restarts then exits', () => {
    make().relaunch()
    expect(mocks.relaunch).toHaveBeenCalledTimes(1)
    expect(mocks.exit).toHaveBeenCalledWith(0)
  })
})

describe('change feed', () => {
  it('polls only while someone is subscribed and pushes only changes', async () => {
    vi.useFakeTimers()
    const p = make({ probe: async () => 'ok' })
    const { sender } = fakeSender()
    p.subscribe(sender)
    await vi.advanceTimersByTimeAsync(0)
    expect(sender.send).toHaveBeenCalledTimes(1) // the first snapshot
    expect(sender.send.mock.calls[0][0]).toBe(IPC.permissionsChanged)

    await vi.advanceTimersByTimeAsync(3000)
    expect(sender.send).toHaveBeenCalledTimes(1) // nothing changed

    mocks.media.microphone = 'denied'
    await vi.advanceTimersByTimeAsync(1500)
    expect(sender.send).toHaveBeenCalledTimes(2)
    expect(sender.send.mock.calls[1][1]).toMatchObject({ microphone: 'denied' })

    p.unsubscribe(sender)
    expect(p.subscriberCount()).toBe(0)
    mocks.getMediaAccessStatus.mockClear()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(mocks.getMediaAccessStatus).not.toHaveBeenCalled()
  })

  it('drops a destroyed renderer and stops polling', async () => {
    vi.useFakeTimers()
    const p = make({ probe: async () => 'ok' })
    const a = fakeSender(1)
    p.subscribe(a.sender)
    await vi.advanceTimersByTimeAsync(0)
    a.fire('destroyed')
    expect(p.subscriberCount()).toBe(0)
    mocks.getMediaAccessStatus.mockClear()
    await vi.advanceTimersByTimeAsync(5000)
    expect(mocks.getMediaAccessStatus).not.toHaveBeenCalled()
  })

  it('a second subscriber gets the next change and polling continues until both leave', async () => {
    vi.useFakeTimers()
    const p = make({ probe: async () => 'ok' })
    const a = fakeSender(1)
    const b = fakeSender(2)
    p.subscribe(a.sender)
    p.subscribe(b.sender)
    p.subscribe(a.sender) // duplicate subscribe is ignored
    expect(p.subscriberCount()).toBe(2)
    await vi.advanceTimersByTimeAsync(0)
    mocks.trusted = true
    await vi.advanceTimersByTimeAsync(1500)
    expect(a.sender.send.mock.calls.at(-1)?.[1]).toMatchObject({ accessibility: true })
    expect(b.sender.send.mock.calls.at(-1)?.[1]).toMatchObject({ accessibility: true })
    p.unsubscribe(a.sender)
    mocks.trusted = false
    await vi.advanceTimersByTimeAsync(1500)
    expect(b.sender.send.mock.calls.at(-1)?.[1]).toMatchObject({ accessibility: false })
    p.dispose()
    expect(p.subscriberCount()).toBe(0)
  })
})

describe('hint', () => {
  const ps = [
    '    1     0 /sbin/launchd',
    '  400     1 /Applications/iTerm.app/Contents/MacOS/iTerm2',
    '  401   400 /usr/bin/login',
    '  402   401 -zsh',
    '  500   402 node',
    '  600   500 /repo/node_modules/electron/dist/Electron.app/Contents/MacOS/Electron',
  ].join('\n')

  it('names the app the dev build was launched from', () => {
    expect(findLaunchingApp(ps, 600)).toBe('iTerm')
  })

  it('uses the outermost bundle name', () => {
    const table = ['  10   1 /Applications/Claude.app/Contents/MacOS/Claude', '  11  10 /Applications/Claude.app/Contents/Frameworks/Claude Helper.app/Contents/MacOS/Claude Helper', '  12  11 node'].join('\n')
    expect(findLaunchingApp(table, 12)).toBe('Claude')
  })

  it('returns null for a Finder or login launch (parent is launchd)', () => {
    expect(findLaunchingApp(['  1  0 /sbin/launchd', '  50  1 /Applications/Alongside.app/Contents/MacOS/Alongside'].join('\n'), 50)).toBeNull()
    expect(findLaunchingApp('', 50)).toBeNull()
  })

  it('does not report Electron itself as the launcher', () => {
    const table = ['  10   1 /x/Electron.app/Contents/MacOS/Electron', '  11  10 /x/Electron.app/Contents/Frameworks/Electron Helper.app/Contents/MacOS/Electron Helper'].join('\n')
    expect(findLaunchingApp(table, 11)).toBeNull()
  })

  it('words the hint for packaged, terminal and plain dev launches', () => {
    expect(buildPermissionHint({ packaged: true, launcher: null })).toContain('"Alongside"')
    expect(buildPermissionHint({ packaged: false, launcher: 'Terminal' })).toContain('"Terminal"')
    expect(buildPermissionHint({ packaged: false, launcher: null })).toContain('"Electron"')
  })
})
