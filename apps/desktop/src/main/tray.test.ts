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
import { ATTENTION_DOT, attentionLine, buildMenuEntries, describeStatus, iconKind, registerTray } from './tray'
import type { TrayModel } from './tray'
import { trayTitle } from './panel-rules'
import type { TrayStateInput } from './panel-rules'

const base: TrayModel = { phase: 'asleep', micMuted: false, persona: null, dockVisible: true, showtimeRunning: false, voiceMenu: true }
const labels = (m: Partial<TrayModel> = {}) => buildMenuEntries({ ...base, ...m }).filter((e) => !e.separator).map((e) => e.label)
const byId = (m: Partial<TrayModel>, id: string) => buildMenuEntries({ ...base, ...m }).find((e) => e.id === id)

describe('menu content', () => {
  it('has every required item, in plain sentence case without emoji', () => {
    const all = labels()
    expect(all).toEqual([
      'Asleep',
      'Show panel',
      'Talk to Knack',
      'Pause for 1 hour',
      'Type instead',
      'Mute microphone',
      'Stop',
      'Stop everything',
      'Open dashboard',
      'Open morning queue',
      'Run the walkthrough',
      'Set up again…',
      'Permissions…',
      'Quit Knack',
    ])
    for (const label of all) expect(label).not.toMatch(/\p{Extended_Pictographic}/u)
  })

  it('the calm menu (voice off, the default): help level, talk, pause, awareness, stop everything, dashboard, queue, quit', () => {
    const calm = { voiceMenu: false, coach: 'Help level 1: Watch me', awareness: { enabled: false, onTrigger: false, periodic: false } }
    expect(labels(calm)).toEqual([
      'Asleep',
      'Help level 1: Watch me',
      'Show panel',
      'Talk to Knack',
      'Pause for 1 hour',
      'Awareness',
      'Glance when I seem stuck',
      'Look now and then',
      'Stop everything',
      'Open dashboard',
      'Open morning queue',
      'Permissions…',
      'Quit Knack',
    ])
    // the glance switches are the AWARENESS settings, unavailable until awareness itself is on
    expect(byId(calm, 'awareness')).toMatchObject({ checked: false, enabled: true })
    expect(byId(calm, 'glance_trigger')).toMatchObject({ checked: false, enabled: false })
    const on = { ...calm, awareness: { enabled: true, onTrigger: true, periodic: false } }
    expect(byId(on, 'glance_trigger')).toMatchObject({ checked: true, enabled: true })
    expect(byId(on, 'glance_periodic')).toMatchObject({ checked: false, enabled: true })
    expect(byId({ voiceMenu: false }, 'type')).toBeUndefined()
    expect(byId({ voiceMenu: false }, 'mute')).toBeUndefined()
  })

  it('shows the talk key next to Talk to Knack, and offers Resume now while paused (with the time in the status line)', () => {
    expect(byId({ talkAccelerator: 'Alt+Space' }, 'talk:understudy')?.accelerator).toBe('Alt+Space')
    const now = new Date(2026, 10, 7, 17, 30).getTime()
    const until = now + 60 * 60_000
    const entries = buildMenuEntries({ ...base, pausedUntil: until }, now)
    expect(entries[0]!.label).toBe('Paused until 18:30')
    expect(entries.find((e) => e.id === 'unpause')?.label).toBe('Resume now')
    expect(entries.find((e) => e.id === 'pause')).toBeUndefined()
    expect(buildMenuEntries({ ...base, pausedUntil: now - 1 }, now).find((e) => e.id === 'pause')).toBeTruthy() // an ended pause is no pause
  })

  it('describes each phase', () => {
    expect(describeStatus({ phase: 'asleep', micMuted: false, persona: null })).toBe('Asleep')
    expect(describeStatus({ phase: 'listening_for_name', micMuted: false, persona: null })).toBe('Waiting to hear its name')
    expect(describeStatus({ phase: 'connecting', micMuted: false, persona: 'amelia' })).toBe('Connecting to Amelia…')
    expect(describeStatus({ phase: 'live', micMuted: false, persona: 'amelia' })).toBe('Live with Amelia')
    expect(describeStatus({ phase: 'thinking', micMuted: false, persona: null })).toBe('Knack is thinking')
    expect(describeStatus({ phase: 'speaking', micMuted: false, persona: 'understudy' })).toBe('Knack is speaking')
    expect(describeStatus({ phase: 'error', micMuted: false, persona: null })).toBe('Something went wrong')
    expect(describeStatus({ phase: 'live', micMuted: true, persona: 'understudy' })).toBe('Microphone muted')
  })

  it('picks the icon badge: paused first, then a glance in flight, then an agent acting; mute no longer changes it', () => {
    expect(iconKind({ phase: 'asleep', micMuted: false })).toBe('idle')
    expect(iconKind({ phase: 'listening_for_name', micMuted: false })).toBe('idle')
    for (const phase of ['connecting', 'live', 'thinking', 'speaking'] as const) expect(iconKind({ phase, micMuted: false })).toBe('acting')
    expect(iconKind({ phase: 'live', micMuted: true })).toBe('acting')
    expect(iconKind({ phase: 'asleep', micMuted: true })).toBe('idle')
    expect(iconKind({ phase: 'asleep', micMuted: false, agents: [{ status: 'running' }] })).toBe('acting')
    expect(iconKind({ phase: 'asleep', micMuted: false, agentActing: true })).toBe('acting') // an agent-service run counts
    expect(iconKind({ phase: 'asleep', micMuted: false, glanceInFlight: true })).toBe('glance')
    expect(iconKind({ phase: 'live', micMuted: false, glanceInFlight: true, paused: true })).toBe('paused')
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
    expect(byId({ showtimeRunning: true }, 'demo')?.label).toBe('Stop the walkthrough')
  })

  it('shows the real hotkeys on the persona the hotkey starts, and on Stop', () => {
    const m = { startAccelerator: 'CommandOrControl+Alt+Space', stopAccelerator: 'CommandOrControl+Alt+M' }
    expect(byId({ ...m, persona: null }, 'talk:understudy')?.accelerator).toBe(m.startAccelerator)
    expect(byId({ ...m, phase: 'live' }, 'stop')?.accelerator).toBe(m.stopAccelerator)
    expect(byId({}, 'stop')?.accelerator).toBeUndefined()
  })
})

function setup(opts: { showMenuBarIcon?: boolean; iconDir?: string; dockVisible?: boolean; voice?: boolean; cue?: boolean; now?: () => number; openDashboard?: () => void; glanceInFlight?: () => boolean; awareness?: boolean; extra?: Record<string, unknown> } = {}) {
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
  bus.on('talk', (e) => events.push({ name: 'talk', ...e }))
  // A stand-in for the awareness module: its own store, the same consent rule (glances need the card first).
  const aw = { enabled: false, onTrigger: false, periodic: false, calls: 0, lastSkip: null as string | null, consented: false, switches: [] as string[] }
  const awareness = opts.awareness === false ? undefined : {
    view: () => ({ enabled: aw.enabled, onTrigger: aw.onTrigger, periodic: aw.periodic, calls: aw.calls, lastSkip: aw.lastSkip }),
    setSwitch: (name: 'enabled' | 'trigger' | 'periodic', on: boolean) => {
      aw.switches.push(`${name}:${on}`)
      if (name === 'enabled') aw.enabled = on
      else if (on && !aw.consented) return { needsConsent: true }
      else if (name === 'trigger') aw.onTrigger = on
      else aw.periodic = on
      return { needsConsent: false }
    },
  }
  const shell = registerTray({ bus, state, settings, windows, stop, quit, log: () => undefined, awareness, iconDir: opts.iconDir ?? path.join(process.cwd(), 'resources', 'tray'), voiceMenu: () => opts.voice ?? true, cueMenu: () => opts.cue ?? false, now: opts.now, openDashboard: opts.openDashboard, glanceInFlight: opts.glanceInFlight, ...(opts.extra as object) })
  return { shell, bus, settings, state, windows, stop, quit, events, aw, tray: () => mocks.FakeTray.instances.at(-1)! }
}

describe('tray lifecycle', () => {
  beforeEach(() => mocks.FakeTray.instances.splice(0))

  it('creates the menu bar item when showMenuBarIcon is on and loads the template icon', () => {
    const { shell, tray } = setup()
    expect(shell.hasTray()).toBe(true)
    expect(tray().image).toMatchObject({ file: expect.stringContaining('trayTemplate.png') })
    expect(tray().tooltip).toBe('Knack: Asleep')
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
    expect(tray().tooltip).toBe('Knack: Waiting to hear its name')
    expect(spy).toHaveBeenCalledTimes(1) // tooltip changed, same idle icon key set
    state.patch({ phase: 'live', persona: 'understudy' })
    expect(tray().tooltip).toBe('Knack: Live with Knack')
    expect(tray().image).toMatchObject({ file: expect.stringContaining('trayActingTemplate.png') })
    const calls = spy.mock.calls.length
    state.patch({ captions: [] }) // unrelated
    expect(spy.mock.calls.length).toBe(calls)
    state.patch({ micMuted: true })
    expect(tray().image).toMatchObject({ file: expect.stringContaining('trayActingTemplate.png') }) // the badge says an agent or session is on, mute or not
    expect(tray().tooltip).toBe('Knack: Microphone muted')
  })

  it('falls back to a text title if the icon files are missing', () => {
    const { tray, shell } = setup({ iconDir: path.join(process.cwd(), 'no-such-dir') })
    expect(tray().title).toBe('Knack')
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
    expect(items.filter((i) => i.type === 'separator')).toHaveLength(6)
  })

  it('menu clicks run the entry', () => {
    const { tray, events } = setup()
    tray().handlers['right-click']()
    const items = tray().popped[0].items as { label?: string; click?: () => void }[]
    items.find((i) => i.label === 'Talk to Knack')?.click?.()
    expect(events).toEqual([{ name: 'session:request', personaId: 'understudy', source: 'button' }])
  })
})

describe('menu actions', () => {
  it('Talk to Knack emits session:request from the button while the old voice menu is on', () => {
    const { shell, events } = setup()
    expect(shell.activate('talk:understudy')).toBe(true)
    expect(shell.activate('talk:amelia')).toBe(false) // the legacy personas are not offered
    expect(events).toEqual([{ name: 'session:request', personaId: 'understudy', source: 'button' }])
  })

  it('with voice off (the default) Talk to Knack raises the panel and emits talk from the tray, and starts no session', () => {
    const { shell, events, windows } = setup({ voice: false })
    expect(shell.activate('talk:understudy')).toBe(true)
    expect(windows.showDock).toHaveBeenCalled()
    expect(events).toEqual([{ name: 'talk', source: 'tray', phase: 'press' }])
    expect(shell.info().menu.some((e) => e.id === 'type' || e.id === 'mute' || e.id === 'demo' || e.id === 'setup')).toBe(false)
  })

  it('Pause for 1 hour sets pausedUntil an hour ahead, shows the paused icon, and Resume now clears it', () => {
    const { shell, settings, tray } = setup({ now: () => 1_000_000 })
    expect(shell.activate('pause')).toBe(true)
    expect(settings.get().pausedUntil).toBe(1_000_000 + 3_600_000)
    expect(tray().image).toMatchObject({ file: expect.stringContaining('trayPausedTemplate.png') })
    expect(shell.activate('pause')).toBe(false) // offered as Resume now while paused
    expect(shell.activate('unpause')).toBe(true)
    expect(settings.get().pausedUntil).toBeNull()
    expect(tray().image).toMatchObject({ file: expect.stringContaining('trayTemplate.png') })
  })

  it('the awareness checkboxes read and write through the awareness module, never through settings.json', () => {
    const { shell, settings, aw, windows } = setup()
    expect(shell.activate('glance_trigger')).toBe(false) // awareness is off: the glance switches are disabled
    expect(shell.activate('awareness')).toBe(true)
    expect(aw.enabled).toBe(true)
    expect(Object.keys(settings.get())).not.toContain('awarenessEnabled')
    expect(Object.keys(settings.get())).not.toContain('glanceOnTrigger')
    expect(Object.keys(settings.get())).not.toContain('glancePeriodic')
    // glances up need the consent card first: the tray opens it (the settings view) and changes nothing
    expect(shell.activate('glance_trigger')).toBe(true)
    expect(aw.onTrigger).toBe(false)
    expect(windows.sendDock).toHaveBeenCalledWith(expect.anything(), { type: 'view', view: 'settings' })
    aw.consented = true // the worker agreed on the card
    expect(shell.activate('glance_trigger')).toBe(true)
    expect(shell.activate('glance_periodic')).toBe(true)
    expect(aw).toMatchObject({ onTrigger: true, periodic: true })
    expect(shell.activate('glance_periodic')).toBe(true) // and back down
    expect(aw.periodic).toBe(false)
    expect(shell.activate('awareness')).toBe(true)
    expect(aw.enabled).toBe(false)
  })

  it('shows the glance count and the last skip in plain words, only while awareness is on', () => {
    const { shell, aw } = setup()
    expect(shell.info().menu.some((e) => e.id === 'glance_info')).toBe(false)
    aw.enabled = true
    aw.calls = 3
    aw.lastSkip = 'secure_input'
    shell.refresh?.()
    const line = shell.info().menu.find((e) => e.id === 'glance_info')
    expect(line).toMatchObject({ label: 'Looks today: 3, last skipped: a password field', enabled: false })
    aw.calls = 0
    aw.lastSkip = null
    expect(shell.info().menu.some((e) => e.id === 'glance_info')).toBe(false)
  })

  it('without an awareness module the menu has no awareness items and the entries do nothing', () => {
    const { shell } = setup({ awareness: false })
    expect(shell.info().menu.some((e) => e.id === 'awareness')).toBe(false)
    expect(shell.activate('awareness')).toBe(false)
  })

  it('shows a glance in flight with its own badge', () => {
    let inFlight = false
    const { shell, tray, state } = setup({ glanceInFlight: () => inFlight })
    inFlight = true
    state.patch({ captions: [] }) // any change refreshes the icon
    shell.info()
    state.patch({ phase: 'listening_for_name' })
    expect(tray().image).toMatchObject({ file: expect.stringContaining('trayGlanceTemplate.png') })
  })

  it('Open dashboard opens the dashboard', () => {
    const open = vi.fn()
    const { shell } = setup({ openDashboard: open })
    expect(shell.activate('dashboard')).toBe(true)
    expect(open).toHaveBeenCalledTimes(1)
    expect(setup().shell.activate('dashboard')).toBe(false) // nothing wired
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
    expect(setup().shell.info().menu.find((e) => e.id === 'talk:understudy')?.accelerator).toBe('CommandOrControl+Alt+Shift+Space')
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
    state.patch({ phase: 'live', persona: 'understudy' })
    expect(tray().title).toBe('Live')
    state.patch({ agents: [{ id: 'a1', kind: 'act_for_me', title: 't', status: 'running', startedAt: 1 }] as never })
    expect(tray().title).toBe('Working…')
    expect(tray().tooltip).toBe('Knack: Knack is working for you')
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

describe('Understudy menu items', () => {
  it('Stop everything triggers the kill switch, then offers Resume; Open morning queue opens the queue', () => {
    const calls: string[] = []
    let killed = false
    mocks.FakeTray.instances.length = 0
    const settings = new SettingsStore(null)
    settings.patch({ onboardingDone: true })
    const state = new StateStore(settings.get())
    const windows = { showDock: vi.fn(), hideDock: vi.fn(), isDockVisible: () => true, sendDock: vi.fn() }
    const shell = registerTray({
      bus: new Bus(),
      state,
      settings,
      windows,
      stop: vi.fn(),
      quit: vi.fn(),
      log: () => undefined,
      iconDir: path.join(process.cwd(), 'resources', 'tray'),
      kill: { trigger: () => void (calls.push('kill'), (killed = true)), clear: () => void (calls.push('resume'), (killed = false)), isKilled: () => killed },
      openQueue: () => void calls.push('queue'),
    })
    expect(shell.activate('kill')).toBe(true)
    expect(shell.info().menu.find((e) => e.id === 'resume')?.label).toBe('Resume after stopping everything')
    expect(shell.info().menu.some((e) => e.id === 'kill')).toBe(false)
    expect(shell.activate('queue')).toBe(true)
    expect(shell.activate('resume')).toBe(true)
    expect(shell.info().menu.some((e) => e.id === 'kill')).toBe(true)
    expect(calls).toEqual(['kill', 'queue', 'resume'])
  })

  it('both entries do nothing (and report false) when no kill switch or queue is wired', () => {
    const { shell } = setup()
    expect(shell.activate('kill')).toBe(false)
    expect(shell.activate('queue')).toBe(false)
  })
})

describe('desk capture line in the menu', () => {
  it('says plainly when capture is off or on, and is omitted when unknown', () => {
    expect(labels({})).not.toContain('Desk capture is off. Turn it on in setup to share when you are active.')
    expect(labels({ capture: 'off' })[1]).toBe('Desk capture is off. Turn it on in setup to share when you are active.')
    expect(labels({ capture: 'times_only' })[1]).toMatch(/times only/)
    expect(byId({ capture: 'off' }, 'capture')?.enabled).toBe(false)
  })
})

describe('coach line in the menu (the coach is not drawn on the screen)', () => {
  it('names the help level plainly, as a disabled line under the capture line, and is omitted when unknown', () => {
    expect(labels({})).not.toContain('Help level 1: Watch me')
    expect(labels({ capture: 'times_only', coach: 'Help level 1: Watch me' })[2]).toBe('Help level 1: Watch me')
    expect(byId({ coach: 'Help level 1: Watch me' }, 'coach')?.enabled).toBe(false)
  })
})

describe('Cue entries (the UNDERSTUDY_X_CUE experiment) and the queue count', () => {
  const now = new Date(2026, 10, 7, 9, 5).getTime()
  const cue = (quietUntil: number | null) => buildMenuEntries({ ...base, voiceMenu: false, cue: { quietUntil } }, now)

  it('offers "Quiet Cue for an hour", and while it is quiet a disabled "Cue is quiet until HH:MM" with "Resume Cue"', () => {
    expect(cue(null).find((e) => e.id === 'cue_quiet')?.label).toBe('Quiet Cue for an hour')
    const quiet = cue(now + 3_600_000)
    expect(quiet.find((e) => e.id === 'cue_status')).toMatchObject({ label: 'Cue is quiet until 10:05', enabled: false })
    expect(quiet.find((e) => e.id === 'cue_resume')?.label).toBe('Resume Cue')
    expect(quiet.find((e) => e.id === 'cue_quiet')).toBeUndefined()
    expect(cue(now - 1).find((e) => e.id === 'cue_quiet')).toBeTruthy() // a quiet period that ended is no quiet period
    expect(buildMenuEntries({ ...base, voiceMenu: false }, now).some((e) => e.id.startsWith('cue_'))).toBe(false) // no experiment, no entries
  })

  it('Quiet Cue sets cueQuietUntil an hour ahead and Resume Cue clears it', () => {
    const { shell, settings } = setup({ now: () => 5_000_000, cue: true })
    expect(shell.activate('cue_quiet')).toBe(true)
    expect(settings.get().cueQuietUntil).toBe(5_000_000 + 3_600_000)
    expect(shell.activate('cue_quiet')).toBe(false) // offered as Resume Cue now
    expect(shell.activate('cue_resume')).toBe(true)
    expect(settings.get().cueQuietUntil).toBeNull()
  })

  it('says how many approvals wait in the morning queue (the screen no longer does)', () => {
    expect(buildMenuEntries({ ...base, queuePending: 3 }, now).find((e) => e.id === 'queue')?.label).toBe('Open morning queue (3)')
    expect(buildMenuEntries({ ...base, queuePending: 0 }, now).find((e) => e.id === 'queue')?.label).toBe('Open morning queue')
    expect(buildMenuEntries({ ...base, queuePending: null }, now).find((e) => e.id === 'queue')?.label).toBe('Open morning queue')
  })
})

describe('settings keys for the new tracks', () => {
  it('default as the owner chose (Cue on, balanced, spoken cues off, the old wake word off), and reject bad values key by key', () => {
    const s = new SettingsStore(null)
    expect(s.get()).toMatchObject({ cueEnabled: true, cueProactivity: 'balanced', cueVoice: false, cueQuietUntil: null, pausedUntil: null, talkHotkey: 'Alt+Space', wakeEnabled: false })
    s.patch({ cueProactivity: 'eager', cueQuietUntil: 1_700_000_000_000, cueEnabled: false })
    expect(s.get()).toMatchObject({ cueProactivity: 'eager', cueQuietUntil: 1_700_000_000_000, cueEnabled: false })
    s.patch({ cueProactivity: 'loud', cueQuietUntil: 'soon' })
    expect(s.get()).toMatchObject({ cueProactivity: 'eager', cueQuietUntil: 1_700_000_000_000 })
  })

  it('a saved Marcus or Amelia becomes Understudy, and a ring annotation accepts the light weight', async () => {
    const { coerceSettings } = await import('../shared/settings')
    expect(coerceSettings({ persona: 'marcus' }).persona).toBe('understudy')
    expect(coerceSettings({ persona: 'amelia' }).persona).toBe('understudy')
    expect(coerceSettings({}).persona).toBe('understudy')
    const { AnnotationSchema } = await import('../shared/protocol')
    const ring = { id: 'r', kind: 'ring', tone: 'guide', box: { xmin: 1, ymin: 2, xmax: 3, ymax: 4 } }
    expect(AnnotationSchema.safeParse({ ...ring, weight: 'light' }).success).toBe(true)
    expect(AnnotationSchema.safeParse({ ...ring, weight: 'regular' }).success).toBe(true)
    expect(AnnotationSchema.safeParse(ring).success).toBe(true)
    expect(AnnotationSchema.safeParse({ ...ring, weight: 'heavy' }).success).toBe(false)
  })
})

describe('the attention line and dot (REQ-8)', () => {
  it('says how many things need the worker, in plain words, and nothing at all when none do', () => {
    expect(attentionLine(undefined)).toBeUndefined()
    expect(attentionLine({ needsYou: 0, waiting: 3, marker: 'none' })).toBeUndefined()
    expect(attentionLine({ needsYou: 1, waiting: 0, marker: 'needs_you' })).toBe('1 thing needs you')
    expect(attentionLine({ needsYou: 2, waiting: 0, marker: 'needs_you' })).toBe('2 things need you')
    expect(labels({ attention: { needsYou: 2, waiting: 0, marker: 'needs_you' } })).toContain('2 things need you')
    expect(labels({ attention: { needsYou: 1, waiting: 0, marker: 'needs_you' } })).toContain('1 thing needs you')
    expect(byId({ attention: { needsYou: 2, waiting: 0, marker: 'needs_you' } }, 'attention')).toMatchObject({ enabled: false })
  })

  it('leaves the menu exactly as it was with nothing to say', () => {
    const plain = buildMenuEntries(base)
    expect(buildMenuEntries({ ...base, attention: { needsYou: 0, waiting: 0, marker: 'none' } })).toEqual(plain)
    expect(buildMenuEntries({ ...base, attention: undefined })).toEqual(plain)
    expect(plain.some((e) => e.id === 'attention')).toBe(false)
  })

  it('puts the line under the status lines, before the first separator, and keeps the kill entry as it is', () => {
    const ids = buildMenuEntries({ ...base, coach: 'Help level 2: Walk with me', attention: { needsYou: 2, waiting: 0, marker: 'needs_you' } }).map((e) => e.id)
    expect(ids.slice(0, 4)).toEqual(['status', 'coach', 'attention', 'sep1'])
    const stopped = byId({ killed: true, attention: { needsYou: 1, waiting: 0, marker: 'stopped' } }, 'resume')
    expect(stopped).toMatchObject({ label: 'Resume after stopping everything', enabled: true }) // the stop state is the kill switch's, never this layer's
  })

  it('a dot follows the title only while the marker says something needs the worker; the counts bind late and unbind cleanly', () => {
    const { shell, tray } = setup()
    expect(tray().title).toBe('')
    let a: { needsYou: number; waiting: number; marker: 'none' | 'needs_you' | 'stopped' } | null = { needsYou: 2, waiting: 1, marker: 'needs_you' }
    shell.setAttention(() => a)
    expect(tray().title).toBe(ATTENTION_DOT)
    expect(tray().tooltip).toBe('Knack: Asleep. 2 things need you')
    expect(shell.info().tooltip).toBe('Knack: Asleep. 2 things need you')
    expect(shell.info().menu.find((e) => e.id === 'attention')?.label).toBe('2 things need you')
    a = { needsYou: 0, waiting: 1, marker: 'none' }
    shell.refresh()
    expect(tray().title).toBe('')
    expect(tray().tooltip).toBe('Knack: Asleep')
    a = { needsYou: 1, waiting: 0, marker: 'stopped' }
    shell.refresh()
    expect(tray().title).toBe('') // stopped is the kill state: no extra mark from this layer
    a = { needsYou: 1, waiting: 0, marker: 'needs_you' }
    shell.refresh()
    expect(tray().title).toBe(ATTENTION_DOT)
    shell.setAttention(null)
    expect(tray().title).toBe('')
    expect(shell.info().menu.some((e) => e.id === 'attention')).toBe(false)
  })

  it('the dot goes after the state word, and after the fallback word when the icon files are missing', () => {
    const { shell, tray, state } = setup({ iconDir: path.join(process.cwd(), 'no-such-dir') })
    shell.setAttention(() => ({ needsYou: 1, waiting: 0, marker: 'needs_you' }))
    expect(tray().title).toBe(`Knack ${ATTENTION_DOT}`)
    state.patch({ phase: 'live', persona: 'understudy' })
    expect(tray().title).toMatch(new RegExp(`${ATTENTION_DOT}$`))
  })

  it('refresh is only a re-read: without a menu bar item it does nothing', () => {
    const { shell } = setup({ showMenuBarIcon: false })
    expect(() => shell.refresh()).not.toThrow()
    expect(() => shell.setAttention(() => null)).not.toThrow()
  })
})

// The Knack app has one set-up (the first run in its own window) and no side panel: nothing in the menu bar brings the old panel or its eight-step set-up back.
describe('in the Knack app the old side panel and its set-up never open from the menu bar', () => {
  const knackExtra = (calls: string[]) => ({
    knack: () => ({ working: null, needsYou: 0, stopped: false }),
    openApp: () => calls.push('openApp'),
    openSettings: () => calls.push('openSettings'),
    openSetup: () => calls.push('openSetup'),
    ask: () => calls.push('ask'),
  })
  it('the menu has no row that could open the old panel or its set-up (Set up again lives in the app menu and in Settings)', () => {
    const { shell, windows, settings } = setup({ extra: knackExtra([]) })
    const ids = shell.info().menu.map((e) => e.id)
    for (const old of ['setup', 'permissions', 'panel', 'type', 'demo', 'mute', 'stop'] as const) expect(ids, old).not.toContain(old)
    for (const old of ['setup', 'permissions', 'panel', 'type', 'demo'] as const) expect(shell.activate(old), old).toBe(false)
    expect(windows.showDock).not.toHaveBeenCalled()
    expect(settings.get().onboardingDone).toBe(true)
  })
  it('the Ask row goes to the Ask bar, never to the panel', () => {
    const calls: string[] = []
    const { shell, windows } = setup({ extra: knackExtra(calls) })
    expect(shell.activate('ask')).toBe(true)
    expect(calls).toEqual(['ask'])
    expect(windows.showDock).not.toHaveBeenCalled()
  })
  it('without the Knack hooks (the older build) the same rows still open the old panel set-up', () => {
    const { shell, settings, windows } = setup()
    expect(shell.activate('setup')).toBe(true)
    expect(settings.get().onboardingDone).toBe(false)
    expect(windows.sendDock).toHaveBeenLastCalledWith('shell:command', { type: 'view', view: 'onboarding' })
  })
  it('Option-Command-P pauses and resumes instead of opening a panel', () => {
    let now = 1_000_000
    const { shell, settings, windows } = setup({ extra: knackExtra([]), now: () => now })
    shell.togglePanel()
    expect(settings.get().pausedUntil).toBe(now + 60 * 60_000)
    shell.togglePanel()
    expect(settings.get().pausedUntil).toBeNull()
    now += 1
    expect(windows.showDock).not.toHaveBeenCalled()
    expect(windows.hideDock).not.toHaveBeenCalled()
  })
})

