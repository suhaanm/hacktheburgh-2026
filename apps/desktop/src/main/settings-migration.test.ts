import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { coerceSettings, DEFAULT_SETTINGS, SettingsSchema } from '../shared/settings'
import { SettingsStore } from './settings'

describe('the awareness switches left settings.json', () => {
  it('the schema no longer has them', () => {
    for (const k of ['awarenessEnabled', 'glanceOnTrigger', 'glancePeriodic']) {
      expect(Object.keys(SettingsSchema.shape)).not.toContain(k)
      expect(Object.keys(DEFAULT_SETTINGS)).not.toContain(k)
    }
  })

  it('an older saved file that still carries them loads without them (ignored, default off) and they are gone after the next save', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'settings-migration-'))
    fs.writeFileSync(path.join(dir, 'settings.json'), JSON.stringify({ theme: 'dark', awarenessEnabled: true, glanceOnTrigger: true, glancePeriodic: true }))
    expect(Object.keys(coerceSettings(JSON.parse(fs.readFileSync(path.join(dir, 'settings.json'), 'utf8'))))).not.toContain('glanceOnTrigger')
    const s = new SettingsStore(dir)
    expect(s.get().theme).toBe('dark')
    expect(Object.keys(s.get())).not.toContain('awarenessEnabled')
    s.patch({ captions: false })
    s.flush()
    const saved = JSON.parse(fs.readFileSync(path.join(dir, 'settings.json'), 'utf8')) as Record<string, unknown>
    expect(saved.theme).toBe('dark')
    for (const k of ['awarenessEnabled', 'glanceOnTrigger', 'glancePeriodic']) expect(saved).not.toHaveProperty(k)
  })

  it('a patch naming them (the debug server, model tools, a renderer) is dropped and cannot switch a glance on', () => {
    const s = new SettingsStore(null)
    s.patch({ awarenessEnabled: true, glanceOnTrigger: true, glancePeriodic: true }, { trusted: true })
    s.patch({ awarenessEnabled: true, glanceOnTrigger: true })
    expect(Object.keys(s.get())).not.toContain('glanceOnTrigger')
  })
})
