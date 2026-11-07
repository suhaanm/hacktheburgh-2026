import { describe, expect, it } from 'vitest'
import { MODELS_DOT_OFF, MODELS_DOT_ON, buildMenuEntries, type TrayModel } from '../tray'

const base: TrayModel = { phase: 'asleep', micMuted: false, persona: null, dockVisible: false, showtimeRunning: false }
const labels = (m: TrayModel) => buildMenuEntries(m, 0).filter((e) => !e.separator).map((e) => `${e.id}:${e.label}`)

describe('the menu bar menu in the Knack app', () => {
  it('offers Open Knack and one status line with a small dot for the models', () => {
    const live = labels({ ...base, openApp: true, models: { live: true, text: 'Live models' } })
    expect(live).toContain('knack:Open Knack')
    expect(live).toContain(`models:${MODELS_DOT_ON} Live models`)
    const example = labels({ ...base, openApp: true, models: { live: false, text: 'Running with example data' } })
    expect(example).toContain(`models:${MODELS_DOT_OFF} Running with example data`)
    expect(example.indexOf('knack:Open Knack')).toBeLessThan(example.indexOf('panel:Show panel'))
  })
  it('shows no models line while it is not known, and is exactly the old menu without the Knack options', () => {
    expect(labels({ ...base, openApp: true, models: { live: null, text: '' } }).some((l) => l.startsWith('models:'))).toBe(false)
    const plain = labels(base)
    expect(plain.some((l) => l.startsWith('knack:') || l.startsWith('models:'))).toBe(false)
  })
  it('the status line is information, not a button', () => {
    const e = buildMenuEntries({ ...base, models: { live: true, text: 'Live models' } }, 0).find((x) => x.id === 'models')
    expect(e?.enabled).toBe(false)
  })
})
