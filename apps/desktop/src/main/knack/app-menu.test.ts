import type { MenuItemConstructorOptions } from 'electron'
import { describe, expect, it, vi } from 'vitest'
import { APP_NAME } from '../../shared/brand'
import { buildAppMenuTemplate, buildDockMenuTemplate } from './app-menu'

const handlers = () => ({ openSettings: vi.fn(), openSetup: vi.fn(), showWindow: vi.fn(), stopEverything: vi.fn() })
const sub = (m: MenuItemConstructorOptions): MenuItemConstructorOptions[] => (m.submenu as MenuItemConstructorOptions[]) ?? []
const menu = (over: Partial<Parameters<typeof buildAppMenuTemplate>[0]> = {}) => buildAppMenuTemplate({ appName: APP_NAME, platform: 'darwin', isPackaged: true, killAccelerator: 'CommandOrControl+Alt+Shift+K', handlers: handlers(), ...over })
const labelled = (items: MenuItemConstructorOptions[]) => items.map((i) => i.label ?? i.role ?? i.type)

describe('the macOS application menu', () => {
  it('starts with the product menu: About, Settings…, Set up again…, Hide, Quit, each named after the brand', () => {
    const app = menu()[0]!
    expect(app.label).toBe('Knack')
    expect(labelled(sub(app))).toEqual(['About Knack', 'separator', 'Settings…', 'Set up again…', 'separator', 'services', 'separator', 'Hide Knack', 'hideOthers', 'unhide', 'separator', 'Quit Knack'])
    expect(sub(app).find((i) => i.label === 'Settings…')?.accelerator).toBe('CommandOrControl+,')
    expect(sub(app).find((i) => i.label === 'Quit Knack')?.role).toBe('quit') // Cmd-Q
    expect(sub(app).find((i) => i.label === 'About Knack')?.role).toBe('about')
  })
  it('has Edit with the standard roles so copy and paste work, and Window with minimize', () => {
    const m = menu()
    const edit = m.find((x) => x.label === 'Edit')!
    for (const role of ['undo', 'redo', 'cut', 'copy', 'paste', 'selectAll']) expect(sub(edit).some((i) => i.role === role), role).toBe(true)
    const win = m.find((x) => x.label === 'Window')!
    expect(sub(win).some((i) => i.role === 'minimize')).toBe(true)
    expect(sub(win).some((i) => i.label === 'Knack')).toBe(true)
  })
  it('Cmd-W closes the window (which the app turns into hiding it: the app stays in the menu bar)', () => {
    const file = menu().find((x) => x.label === 'File')!
    const close = sub(file).find((i) => i.role === 'close')!
    expect(close.accelerator).toBe('CommandOrControl+W')
  })
  it('Command-Shift-K stops everything while Knack is frontmost (an app-local accelerator; the global key stays Option-Shift-Command-K)', () => {
    const stop = sub(menu().find((x) => x.label === 'File')!).find((i) => i.label === 'Stop Everything')!
    expect(stop.accelerator).toBe('Shift+CommandOrControl+K')
    expect(stop.registerAccelerator).toBeUndefined() // a real menu accelerator: it fires only when the app is in front
  })
  it('wires the items to the shell', () => {
    const h = handlers()
    const m = menu({ handlers: h })
    sub(m[0]!).find((i) => i.label === 'Settings…')!.click!({} as never, undefined, {} as never)
    sub(m[0]!).find((i) => i.label === 'Set up again…')!.click!({} as never, undefined, {} as never)
    sub(m.find((x) => x.label === 'File')!).find((i) => i.label === 'Stop Everything')!.click!({} as never, undefined, {} as never)
    sub(m.find((x) => x.label === 'Window')!).find((i) => i.label === 'Knack')!.click!({} as never, undefined, {} as never)
    expect([h.openSettings.mock.calls.length, h.openSetup.mock.calls.length, h.stopEverything.mock.calls.length, h.showWindow.mock.calls.length]).toEqual([1, 1, 1, 1])
  })
  it('offers reload and developer tools only in a development build', () => {
    const roles = (packaged: boolean) => sub(menu({ isPackaged: packaged }).find((x) => x.label === 'View')!).map((i) => i.role)
    expect(roles(true)).toEqual(['togglefullscreen'])
    expect(roles(false)).toContain('toggleDevTools')
  })
})

describe('other platforms and the Dock menu', () => {
  it('has no product menu off macOS, and puts Settings and Quit under File', () => {
    const m = menu({ platform: 'linux' })
    expect(m[0]!.label).toBe('File')
    expect(labelled(sub(m[0]!))).toContain('Settings…')
    expect(labelled(sub(m[0]!))).toContain('Quit Knack')
  })
  it('the Dock menu has three rows: Needs you (n) when n is above 0, Pause for 1 hour, Stop everything', () => {
    const h = { ...handlers(), openNeedsYou: vi.fn(), pause: vi.fn(), resume: vi.fn() }
    expect(labelled(buildDockMenuTemplate({ handlers: h, needsYou: 0, paused: false, stopped: false }))).toEqual(['Pause for 1 hour', 'Stop everything'])
    const items = buildDockMenuTemplate({ handlers: h, needsYou: 2, paused: false, stopped: false })
    expect(labelled(items)).toEqual(['Needs you (2)', 'Pause for 1 hour', 'Stop everything'])
    for (const it of items) it.click!({} as never, undefined, {} as never)
    expect([h.openNeedsYou.mock.calls.length, h.pause.mock.calls.length, h.stopEverything.mock.calls.length]).toEqual([1, 1, 1])
  })
  it('the Dock menu turns Pause into Resume now and Stop into Resume after stopping, and never offers Open (a click on the icon opens the window)', () => {
    const h = { ...handlers(), openNeedsYou: vi.fn(), pause: vi.fn(), resume: vi.fn() }
    const items = buildDockMenuTemplate({ handlers: h, needsYou: 0, paused: true, stopped: true })
    expect(labelled(items)).toEqual(['Resume now', 'Resume after stopping'])
    for (const it of items) it.click!({} as never, undefined, {} as never)
    expect(h.resume).toHaveBeenCalledTimes(2)
  })
})
