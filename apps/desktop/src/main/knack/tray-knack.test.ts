import { describe, expect, it } from 'vitest'
import { MODELS_DOT_OFF, MODELS_DOT_ON, buildKnackMenuEntries, buildMenuEntries, knackIconKind, type TrayModel } from '../tray'

const base: TrayModel = { phase: 'asleep', micMuted: false, persona: null, dockVisible: false, showtimeRunning: false }
const knack = (over: Partial<TrayModel> & { k?: Partial<NonNullable<TrayModel['knack']>> } = {}): TrayModel => {
  const { k, ...rest } = over
  return { ...base, openApp: true, talkAccelerator: 'Alt+Space', panelAccelerator: 'CommandOrControl+Alt+P', killAccelerator: 'CommandOrControl+Alt+Shift+K', knack: { working: null, needsYou: 0, stopped: false, ...k }, ...rest }
}
const rows = (m: TrayModel, now = 0) => buildKnackMenuEntries(m, now).filter((e) => !e.separator)
const labels = (m: TrayModel, now = 0) => rows(m, now).map((e) => e.label)

describe('the menu bar menu in the Knack app: eight rows', () => {
  it('idle: the status line, Open, Ask, Pause, Stop, Settings, Quit', () => {
    expect(labels(knack())).toEqual(['Idle', 'Open Knack', 'Ask Knack…', 'Pause for 1 hour', 'Stop everything', 'Settings…', 'Quit Knack'])
  })
  it('at most eight rows, whatever is going on (the glance row is the ninth, and only while a glance mode is on)', () => {
    const busy = knack({ k: { working: 'filling in calculator B', needsYou: 2, stopped: false } })
    expect(rows(busy)).toHaveLength(8)
    expect(rows(knack({ k: { needsYou: 1 } }))).toHaveLength(8)
    const glance = knack({ awareness: { enabled: true, onTrigger: true, periodic: false }, k: { needsYou: 1 } })
    expect(rows(glance)).toHaveLength(9)
    expect(labels(glance)).toContain('Screen glances: when stuck')
    expect(labels(knack({ awareness: { enabled: false, onTrigger: true, periodic: true } }))).not.toContain('Screen glances: when stuck')
  })
  it('Hey Knack adds its one switch, only while the listener exists', () => {
    expect(labels(knack())).not.toContain('Listen for Hey Knack')
    const on = rows(knack({ wake: { on: true, line: 'Listening for Hey Knack' } })).find((r) => r.id === 'wake_listen')
    expect(on).toMatchObject({ label: 'Listen for Hey Knack', checked: true, enabled: true })
    expect(rows(knack({ wake: { on: false, line: 'Off' } })).find((r) => r.id === 'wake_listen')?.checked).toBe(false)
  })
  it('a listener that cannot listen says why in one quiet line above its switch; a listener that is listening adds no line', () => {
    const blocked = rows(knack({ wake: { on: true, line: 'Hey Knack needs the microphone. Turn it on in System Settings.' } }))
    expect(blocked.find((r) => r.id === 'wake_status')).toMatchObject({ label: 'Hey Knack needs the microphone. Turn it on in System Settings.', enabled: false })
    expect(blocked.map((r) => r.id).indexOf('wake_status')).toBe(blocked.map((r) => r.id).indexOf('wake_listen') - 1)
    expect(rows(knack({ wake: { on: true, line: 'Listening for Hey Knack. Stays on this Mac, nothing stored.' } })).some((r) => r.id === 'wake_status')).toBe(false)
    expect(rows(knack({ wake: { on: false, line: 'Hey Knack is off' } })).some((r) => r.id === 'wake_status')).toBe(false)
  })
  it('the first line says what is happening, in one line', () => {
    expect(labels(knack({ k: { working: 'filling in calculator B' } }))[0]).toBe('Knack is working: filling in calculator B')
    expect(labels(knack({ k: { stopped: true } }))[0]).toBe('Stopped. Nothing will run.')
    const paused = knack({ pausedUntil: Date.parse('2026-11-07T20:30:00') })
    expect(labels(paused, Date.parse('2026-11-07T19:30:00'))[0]).toMatch(/^Paused until \d\d:\d\d$/)
  })
  it('"1 thing needs you" only when true, and it opens Needs you', () => {
    expect(labels(knack())).not.toContain('1 thing needs you')
    expect(labels(knack({ k: { needsYou: 1 } }))[1]).toBe('1 thing needs you')
    expect(labels(knack({ k: { needsYou: 3 } }))[1]).toBe('3 things need you')
    expect(rows(knack({ k: { needsYou: 1 } })).find((r) => r.id === 'needs_you')?.enabled).toBe(true)
  })
  it('pause becomes Resume now, and Stop becomes Resume after stopping', () => {
    const paused = knack({ pausedUntil: 5_000_000 })
    expect(labels(paused, 1000)).toContain('Resume now')
    expect(labels(paused, 1000)).not.toContain('Pause for 1 hour')
    const stopped = knack({ k: { stopped: true } })
    expect(labels(stopped)).toContain('Resume after stopping')
    expect(labels(stopped)).not.toContain('Stop everything')
    expect(labels(knack({ killed: true }))).toContain('Resume after stopping')
  })
  it('the keys are on the rows: Option-Space, Option-Command-P, Option-Shift-Command-K, Command-comma, Command-Q', () => {
    const acc = (id: string) => rows(knack()).find((r) => r.id === id)?.accelerator
    expect(acc('ask')).toBe('Alt+Space')
    expect(acc('pause')).toBe('CommandOrControl+Alt+P')
    expect(acc('kill')).toBe('CommandOrControl+Alt+Shift+K')
    expect(acc('settings')).toBe('CommandOrControl+,')
    expect(acc('quit')).toBe('CommandOrControl+Q')
  })
  it('says Ask Knack, not Talk to anyone, and has none of the older rows', () => {
    const all = labels(knack({ voiceMenu: true })).join('|')
    expect(all).not.toMatch(/Talk to|Show panel|Open morning queue|Open dashboard|Permissions|Type instead/)
    expect(all).toContain('Ask Knack…')
  })
})

describe('the icon', () => {
  it('stopped (a square), paused, working (a dot), a glance (a ring), else the mark alone; stopped wins, then paused', () => {
    const k = { stopped: false, working: false, paused: false, glanceInFlight: false }
    expect(knackIconKind(k)).toBe('idle')
    expect(knackIconKind({ ...k, working: true })).toBe('acting')
    expect(knackIconKind({ ...k, glanceInFlight: true })).toBe('glance')
    expect(knackIconKind({ ...k, paused: true, working: true })).toBe('paused')
    expect(knackIconKind({ ...k, stopped: true, paused: true, working: true })).toBe('stopped')
  })
})

describe('the older menu is unchanged without the Knack option', () => {
  it('keeps the dot and models line, the Open Knack row and its place before Show panel', () => {
    const plain = buildMenuEntries(base, 0).filter((e) => !e.separator).map((e) => e.id)
    expect(plain.some((id) => id === 'knack' || id === 'models')).toBe(false)
    const old = buildMenuEntries({ ...base, openApp: true, models: { live: true, text: 'Live models' } }, 0)
    expect(old.find((e) => e.id === 'models')?.label).toBe(`${MODELS_DOT_ON} Live models`)
    expect(buildMenuEntries({ ...base, models: { live: false, text: 'Running with example data' } }, 0).find((e) => e.id === 'models')?.label).toBe(`${MODELS_DOT_OFF} Running with example data`)
  })
})
