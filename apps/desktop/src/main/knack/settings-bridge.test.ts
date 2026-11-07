import { describe, expect, it } from 'vitest'
import { SettingsStore } from '../settings'
import { dashboardSettingsPatch, dashboardSettingsView } from './settings-bridge'

describe('what the dashboard Settings may read', () => {
  it('is a small view: the switches it shows, and nothing about folders, the denylist or consent', () => {
    const s = new SettingsStore(null)
    const view = dashboardSettingsView(s.get())
    expect(Object.keys(view).sort()).toEqual(['cueEnabled', 'helpLevelMode', 'launchAtLogin', 'lockedLevel', 'minimiseWhileWorking', 'moveAsideWhileWorking', 'showInDock', 'useLiveModels'])
    expect(view).toMatchObject({ minimiseWhileWorking: true, moveAsideWhileWorking: true, useLiveModels: true, launchAtLogin: false })
  })
  it('answers both names of the move-aside switch with the same value', () => {
    const s = new SettingsStore(null)
    s.patch({ moveAsideWhileWorking: false })
    expect(dashboardSettingsView(s.get())).toMatchObject({ minimiseWhileWorking: false, moveAsideWhileWorking: false })
  })
})

describe('what the dashboard Settings may change', () => {
  it('lets the listed keys through and drops every other key', () => {
    const patch = dashboardSettingsPatch({ launchAtLogin: true, cueEnabled: true, helpLevelMode: 'locked', lockedLevel: 3, showInDock: false, moveAsideWhileWorking: false, useLiveModels: false, awaySeconds: 1, agency: 'autonomous', fileFolders: ['/'], denylist: [] })
    expect(patch).toEqual({ launchAtLogin: true, cueEnabled: true, helpLevelMode: 'locked', lockedLevel: 3, showInDock: false, moveAsideWhileWorking: false })
  })
  it('turns the dashboard name of the move-aside switch into the app name, and the app name wins when both are sent', () => {
    expect(dashboardSettingsPatch({ minimiseWhileWorking: false })).toEqual({ moveAsideWhileWorking: false })
    expect(dashboardSettingsPatch({ minimiseWhileWorking: false, moveAsideWhileWorking: true })).toEqual({ moveAsideWhileWorking: true })
  })
  it('accepts nothing that is not an object', () => {
    for (const bad of [null, undefined, 'launchAtLogin', 7, ['launchAtLogin']]) expect(dashboardSettingsPatch(bad)).toEqual({})
  })
  it('reaches the store as an ordinary, untrusted patch: the store keeps validating values and still drops the trusted-only keys', () => {
    const s = new SettingsStore(null)
    s.patch(dashboardSettingsPatch({ minimiseWhileWorking: false, launchAtLogin: 'yes', lockedLevel: 9, useLiveModels: false }))
    expect(s.get()).toMatchObject({ moveAsideWhileWorking: false, launchAtLogin: false, useLiveModels: true })
    expect(s.get().lockedLevel).not.toBe(9)
  })
})
