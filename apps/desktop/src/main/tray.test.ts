import path from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => {
  class FakeTray {
    static instances: FakeTray[] = []
    handlers: Record<string, () => void> = {}
    destroyed = false
    image: unknown
    tooltip = ''
    title = ''
    popped: { items: unknown[] }[] = []
    setImage = (img: unknown) => {
      this.image = img
    }
    setToolTip = (t: string) => {
      this.tooltip = t
    }
    setTitle = (t: string) => {
      this.title = t
    }
    setIgnoreDoubleClickEvents = () => undefined
    on = (event: string, cb: () => void) => {
      this.handlers[event] = cb
      return this
    }
    popUpContextMenu = (menu: { items: unknown[] }) => {
      this.popped.push(menu)
    }
    getBounds = () => ({ x: 900, y: 0, width: 24, height: 24 })
    destroy = () => {
      this.destroyed = true
    }
    constructor(image: unknown) {
      this.image = image
      FakeTray.instances.push(this)
    }
  }
  return { FakeTray, registered: new Set<string>(['CommandOrControl+Alt+Space', 'CommandOrControl+Alt+M']) }
})

vi.mock('electron', () => ({
  app: { getAppPath: () => process.cwd(), quit: vi.fn() },
  globalShortcut: { isRegistered: (a: string) => mocks.registered.has(a), register: vi.fn(), unregister: vi.fn() },
  Menu: { buildFromTemplate: (items: unknown[]) => ({ items }) },
  nativeImage: {
    createFromPath: (file: string) => ({ file, isEmpty: () => false, setTemplateImage: vi.fn() }),
    createEmpty: () => ({ file: null, isEmpty: () => true, setTemplateImage: vi.fn() }),
  },
  Tray: mocks.FakeTray,
}))

import { Bus } from './bus'
import { SettingsStore } from './settings'
import { StateStore } from './state'
import { buildMenuEntries, describeStatus, iconKind, registerTray } from './tray'
import type { TrayModel } from './tray'
import { trayTitle } from './panel-rules'
import type { TrayStateInput } from './panel-rules'

const base: TrayModel = { phase: 'asleep', micMuted: false, persona: null, dockVisible: true, showtimeRunning: false }
const labels = (m: Partial<TrayModel> = {}) => buildMenuEntries({ ...base, ...m }).filter((e) => !e.separator).map((e) => e.label)
const byId = (m: Partial<TrayModel>, id: string) => buildMenuEntries({ ...base, ...m }).find((e) => e.id === id)

describe('menu content', () => {
  it('has every required item, in plain sentence case without emoji', () => {
    const all = labels()
    expect(all).toEqual([
      'Asleep',
      'Show panel',
      'Talk to Marcus',
      'Talk to Amelia',
      'Type instead',
      'Mute microphone',
      'Stop',
      'Run the demo walkthrough',
      'Set up again…',
      'Permissions…',
      'Quit Alongside',
    ])
    for (const label of all) expect(label).not.toMatch(/\p{Extended_Pictographic}/u)
  })

  it('describes each phase', () => {
    expect(describeStatus({ phase: 'asleep', micMuted: false, persona: null })).toBe('Asleep')
    expect(describeStatus({ phase: 'listening_for_name', micMuted: false, persona: null })).toBe('Waiting to hear its name')
    expect(describeStatus({ phase: 'connecting', micMuted: false, persona: 'amelia' })).toBe('Connecting to Amelia…')
    expect(describeStatus({ phase: 'live', micMuted: false, persona: 'amelia' })).toBe('Live with Amelia')
    expect(describeStatus({ phase: 'thinking', micMuted: false, persona: null })).toBe('Marcus is thinking')
    expect(describeStatus({ phase: 'speaking', micMuted: false, persona: 'marcus' })).toBe('Marcus is speaking')
    expect(describeStatus({ phase: 'error', micMuted: false, persona: null })).toBe('Something went wrong')
    expect(describeStatus({ phase: 'live', micMuted: true, persona: 'marcus' })).toBe('Microphone muted')
  })

  it('picks the icon from mute first, then session activity', () => {
    expect(iconKind({ phase: 'asleep', micMuted: false })).toBe('idle')
    expect(iconKind({ phase: 'listening_for_name', micMuted: false })).toBe('idle')
    for (const phase of ['connecting', 'live', 'thinking', 'speaking'] as const) expect(iconKind({ phase, micMuted: false })).toBe('live')
    expect(iconKind({ phase: 'live', micMuted: true })).toBe('muted')
    expect(iconKind({ phase: 'asleep', micMuted: true })).toBe('muted')
  })

  it('enables Stop only while a session is active', () => {
    expect(byId({ phase: 'asleep' }, 'stop')?.enabled).toBe(false)
    expect(byId({ phase: 'listening_for_name' }, 'stop')?.enabled).toBe(false)
    expect(byId({ phase: 'live' }, 'stop')?.enabled).toBe(true)
    expect(byId({ phase: 'connecting' }, 'stop')?.enabled).toBe(true)
  })

  it('flips the mute, panel and demo labels with state', () => {
    expect(byId({ micMuted: true }, 'mute')?.label).toBe('Unmute microphone')
    expect(byId({ dockVisible: false }, 'panel')).toMatchObject({ label: 'Show panel', checked: false })
    expect(byId({ dockVisible: true }, 'panel')).toMatchObject({ label: 'Show panel', checked: true })
    expect(byId({ showtimeRunning: true }, 'demo')?.label).toBe('Stop the demo walkthrough')
  })

  it('shows the real hotkeys on the persona the hotkey starts, and on Stop', () => {
    const m = { startAccelerator: 'CommandOrControl+Alt+Space', stopAccelerator: 'CommandOrControl+Alt+M' }
    expect(byId({ ...m, persona: null }, 'talk:marcus')?.accelerator).toBe(m.startAccelerator)
    expect(byId({ ...m, persona: null }, 'talk:amelia')?.accelerator).toBeUndefined()
    expect(byId({ ...m, persona: 'amelia' }, 'talk:amelia')?.accelerator).toBe(m.startAccelerator)
    expect(byId({ ...m, phase: 'live' }, 'stop')?.accelerator).toBe(m.stopAccelerator)
    expect(byId({}, 'stop')?.accelerator).toBeUndefined()
  })
})

function setup(opts: { showMenuBarIcon?: boolean; iconDir?: string; dockVisible?: boolean } = {}) {
  mocks.FakeTray.instances.length = 0
  const bus = new Bus()
  const settings = new SettingsStore(null)
  settings.patch({ onboardingDone: true }) // setup done: the panel may be hidden
  if (opts.showMenuBarIcon === false) settings.patch({ showMenuBarIcon: false })
  const state = new StateStore(settings.get())
  let visible = opts.dockVisible ?? true
  const windows = {
    showDock: vi.fn(() => {
      visible = true
    }),
    hideDock: vi.fn(() => {
      visible = false
    }),
    isDockVisible: () => visible,
    sendDock: vi.fn(),
  }
  const stop = vi.fn()
  const quit = vi.fn()
  const events: unknown[] = []
  bus.on('session:request', (e) => events.push({ name: 'session:request', ...e }))
  bus.on('showtime:request', (e) => events.push({ name: 'showtime:request', ...e }))
  const shell = registerTray({ bus, state, settings, windows, stop, quit, log: () => undefined, iconDir: opts.iconDir ?? path.join(process.cwd(), 'resources', 'tray') })
  return { shell, bus, settings, state, windows, stop, quit, events, tray: () => mocks.FakeTray.instances.at(-1)! }
}

describe('tray lifecycle', () => {
  beforeEach(() => mocks.FakeTray.instances.splice(0))

  it('creates the menu bar item when showMenuBarIcon is on and loads the template icon', () => {
    const { shell, tray } = setup()
    expect(shell.hasTray()).toBe(true)
    expect(tray().image).toMatchObject({ file: expect.stringContaining('trayTemplate.png') })
    expect(tray().tooltip).toBe('Alongside: Asleep')
    expect(shell.info().bounds).toEqual({ x: 900, y: 0, width: 24, height: 24 })
  })

  it('does not create it when the setting is off, and follows the setting live', () => {
    const { shell, settings } = setup({ showMenuBarIcon: false })
    expect(shell.hasTray()).toBe(false)
    expect(mocks.FakeTray.instances).toHaveLength(0)
    settings.patch({ showMenuBarIcon: true })
    expect(shell.hasTray()).toBe(true)
    const first = mocks.FakeTray.instances[0]
    settings.patch({ showMenuBarIcon: false })
    expect(first.destroyed).toBe(true)
    expect(shell.hasTray()).toBe(false)
    settings.patch({ showMenuBarIcon: true })
    expect(mocks.FakeTray.instances).toHaveLength(2)
  })

  it('ignores unrelated setting changes', () => {
    const { settings } = setup()
    settings.patch({ captions: false })
    expect(mocks.FakeTray.instances).toHaveLength(1)
  })

  it('updates icon and tooltip with state, and only when they change', () => {
    const { state, tray } = setup()
    const spy = vi.spyOn(tray(), 'setImage')
    state.patch({ phase: 'listening_for_name' })
    expect(tray().tooltip).toBe('Alongside: Waiting to hear its name')
    expect(spy).toHaveBeenCalledTimes(1) // tooltip changed, same idle icon key set
    state.patch({ phase: 'live', persona: 'amelia' })
    expect(tray().tooltip).toBe('Alongside: Live with Amelia')
    expect(tray().image).toMatchObject({ file: expect.stringContaining('trayLiveTemplate.png') })
    const calls = spy.mock.calls.length
    state.patch({ captions: [] }) // unrelated
    expect(spy.mock.calls.length).toBe(calls)
    state.patch({ micMuted: true })
    expect(tray().image).toMatchObject({ file: expect.stringContaining('trayMutedTemplate.png') })
    expect(tray().tooltip).toBe('Alongside: Microphone muted')
  })

  it('falls back to a text title if the icon files are missing', () => {
    const { tray, shell } = setup({ iconDir: path.join(process.cwd(), 'no-such-dir') })
    expect(tray().title).toBe('Alongside')
    expect(shell.hasTray()).toBe(true)
  })

  it('dispose removes the item and stops listening', () => {
    const { shell, tray, state } = setup()
    const t = tray()
    shell.dispose()
    expect(t.destroyed).toBe(true)
    state.patch({ phase: 'live' })
    expect(shell.hasTray()).toBe(false)
  })
})

describe('click handlers', () => {
  it('left click shows a hidden panel (and remembers it), a second click hides it again', () => {
    const { tray, windows, settings } = setup({ dockVisible: false })
    tray().handlers.click()
    expect(windows.showDock).toHaveBeenCalledTimes(1)
    expect(windows.sendDock).toHaveBeenLastCalledWith('shell:command', { type: 'expand' })
    expect(settings.get().showDock).toBe(true)
    tray().handlers.click()
    expect(windows.hideDock).toHaveBeenCalledTimes(1)
    expect(settings.get().showDock).toBe(false)
  })

  it('right click pops up a fresh menu built from the current state', () => {
    const { tray, state } = setup()
    state.patch({ phase: 'live', micMuted: true })
    tray().handlers['right-click']()
    expect(tray().popped).toHaveLength(1)
    const items = tray().popped[0].items as { label?: string; enabled?: boolean; type?: string }[]
    expect(items.find((i) => i.label === 'Unmute microphone')).toBeTruthy()
    expect(items.find((i) => i.label === 'Stop')?.enabled).toBe(true)
    expect(items.filter((i) => i.type === 'separator')).toHaveLength(4)
  })

  it('menu clicks run the entry', () => {
    const { tray, events } = setup()
    tray().handlers['right-click']()
    const items = tray().popped[0].items as { label?: string; click?: () => void }[]
    items.find((i) => i.label === 'Talk to Amelia')?.click?.()
    expect(events).toEqual([{ name: 'session:request', personaId: 'amelia', source: 'button' }])
  })
})

describe('menu actions', () => {
  it('Talk to <persona> emits session:request from the button', () => {
    const { shell, events } = setup()
    expect(shell.activate('talk:marcus')).toBe(true)
    expect(shell.activate('talk:amelia')).toBe(true)
    expect(events).toEqual([
      { name: 'session:request', personaId: 'marcus', source: 'button' },
      { name: 'session:request', personaId: 'amelia', source: 'button' },
    ])
  })

  it('Type instead opens the chat view and shows the dock', () => {
    const { shell, windows } = setup({ dockVisible: false })
    shell.activate('type')
    expect(windows.showDock).toHaveBeenCalled()
    expect(windows.sendDock).toHaveBeenCalledWith('shell:command', { type: 'view', view: 'chat' })
  })

  it('Type instead never saves textOnly (it is a one-off chat mode, not a preference)', () => {
    const { shell, settings } = setup()
    const patch = vi.spyOn(settings, 'patch')
    shell.activate('type')
    expect(patch).not.toHaveBeenCalled()
    expect(settings.get().textOnly).toBe(false)
  })

  it('Mute toggles micMuted in state', () => {
    const { shell, state } = setup()
    shell.activate('mute')
    expect(state.get().micMuted).toBe(true)
    shell.activate('mute')
    expect(state.get().micMuted).toBe(false)
  })

  it('Stop calls the session stop only while active', () => {
    const { shell, state, stop } = setup()
    expect(shell.activate('stop')).toBe(false)
    expect(stop).not.toHaveBeenCalled()
    state.patch({ phase: 'live' })
    expect(shell.activate('stop')).toBe(true)
    expect(stop).toHaveBeenCalledWith('stop')
  })

  it('the Show panel checkbox toggles the dock window and persists showDock', () => {
    const { shell, windows, settings } = setup()
    shell.activate('panel')
    expect(windows.hideDock).toHaveBeenCalledTimes(1)
    expect(settings.get().showDock).toBe(false)
    shell.activate('panel')
    expect(windows.showDock).toHaveBeenCalledTimes(1)
    expect(windows.sendDock).toHaveBeenLastCalledWith('shell:command', { type: 'expand' })
    expect(settings.get().showDock).toBe(true)
  })

  it('the panel stays up while setup is unfinished, even when asked to hide', () => {
    const { shell, windows, settings } = setup()
    settings.patch({ onboardingDone: false })
    shell.activate('panel') // visible -> hide requested
    expect(windows.hideDock).not.toHaveBeenCalled()
  })

  it('the Settings switch (showDock) shows and hides the panel like the checkbox', () => {
    const { windows, settings } = setup({ dockVisible: false })
    settings.patch({ showDock: true })
    expect(windows.showDock).toHaveBeenCalledTimes(1)
    settings.patch({ showDock: false })
    expect(windows.hideDock).toHaveBeenCalledTimes(1)
  })

  it('Type instead from a hidden panel shows it, and the panel hides again when that session ends', () => {
    const { shell, windows, state } = setup({ dockVisible: false })
    shell.activate('type')
    expect(windows.showDock).toHaveBeenCalledTimes(1)
    state.patch({ phase: 'live' })
    state.patch({ phase: 'listening_for_name' })
    expect(windows.hideDock).toHaveBeenCalledTimes(1)
  })

  it('Type instead leaves a panel the user keeps open alone', () => {
    const { shell, windows, state, settings } = setup({ dockVisible: true })
    settings.patch({ showDock: true })
    shell.activate('type')
    state.patch({ phase: 'live' })
    state.patch({ phase: 'listening_for_name' })
    expect(windows.hideDock).not.toHaveBeenCalled()
  })

  it('Run the demo walkthrough emits showtime:request from the tray', () => {
    const { shell, events } = setup()
    shell.activate('demo')
    expect(events).toEqual([{ name: 'showtime:request', source: 'tray' }])
  })

  it('Set up again resets onboarding and opens that view', () => {
    const { shell, settings, windows } = setup()
    settings.patch({ onboardingDone: true })
    shell.activate('setup')
    expect(settings.get().onboardingDone).toBe(false)
    expect(windows.sendDock).toHaveBeenCalledWith('shell:command', { type: 'view', view: 'onboarding' })
  })

  it('Permissions opens the permissions view', () => {
    const { shell, windows } = setup()
    shell.activate('permissions')
    expect(windows.sendDock).toHaveBeenCalledWith('shell:command', { type: 'view', view: 'permissions' })
  })

  it('Quit quits the app', () => {
    const { shell, quit } = setup()
    shell.activate('quit')
    expect(quit).toHaveBeenCalledTimes(1)
  })

  it('rejects unknown ids and the status line', () => {
    const { shell, events } = setup()
    expect(shell.activate('nope')).toBe(false)
    expect(shell.activate('status')).toBe(false)
    expect(shell.activate('talk:bob')).toBe(false)
    expect(events).toEqual([])
  })

  it('shows only hotkeys that are actually registered', () => {
    mocks.registered.clear()
    const { shell } = setup()
    expect(shell.info().menu.some((e) => e.accelerator)).toBe(false)
    mocks.registered.add('CommandOrControl+Alt+Shift+Space')
    expect(setup().shell.info().menu.find((e) => e.id === 'talk:marcus')?.accelerator).toBe('CommandOrControl+Alt+Shift+Space')
    mocks.registered.add('CommandOrControl+Alt+Space')
    mocks.registered.add('CommandOrControl+Alt+M')
  })
})

describe('menu bar state', () => {
  beforeEach(() => mocks.FakeTray.instances.splice(0))

  it('maps every state to a short sentence-case word (asleep shows the icon alone)', () => {
    const t = (m: Partial<TrayStateInput>) => trayTitle({ phase: 'asleep', micMuted: false, ...m })
    expect(t({})).toBe('')
    expect(t({ phase: 'listening_for_name' })).toBe('Listening')
    expect(t({ phase: 'connecting' })).toBe('Connecting')
    expect(t({ phase: 'live' })).toBe('Live')
    expect(t({ phase: 'thinking' })).toBe('Thinking')
    expect(t({ phase: 'speaking' })).toBe('Speaking')
    expect(t({ phase: 'live', micMuted: true })).toBe('Muted')
    expect(t({ phase: 'live', agents: [{ status: 'running' }] })).toBe('Working…')
    expect(t({ phase: 'live', agents: [{ status: 'done' }] })).toBe('Live')
    expect(t({ phase: 'error', micMuted: true })).toBe('Problem')
    for (const phase of ['asleep', 'listening_for_name', 'connecting', 'live', 'thinking', 'speaking', 'error'] as const) expect(t({ phase })).not.toMatch(/\p{Extended_Pictographic}/u)
  })

  it('sets the tray title and tooltip as state changes, including an agent working for the user', () => {
    const { state, tray, shell } = setup()
    state.patch({ phase: 'listening_for_name' })
    expect(tray().title).toBe('Listening')
    expect(shell.info().title).toBe('Listening')
    state.patch({ phase: 'live', persona: 'marcus' })
    expect(tray().title).toBe('Live')
    state.patch({ agents: [{ id: 'a1', kind: 'act_for_me', title: 't', status: 'running', startedAt: 1 }] as never })
    expect(tray().title).toBe('Working…')
    expect(tray().tooltip).toBe('Alongside: Marcus is working for you')
    state.patch({ agents: [] })
    state.patch({ micMuted: true })
    expect(tray().title).toBe('Muted')
    state.patch({ micMuted: false, phase: 'error' })
    expect(tray().title).toBe('Problem')
    state.patch({ phase: 'asleep' })
    expect(tray().title).toBe('')
  })

  it('reports the checkbox state and title in the debug info', () => {
    const { shell } = setup({ dockVisible: false })
    expect(shell.info().menu.find((e) => e.id === 'panel')).toMatchObject({ label: 'Show panel', checked: false })
    expect(shell.info().panelVisible).toBe(false)
  })
})
