// The QA stage-capture override (src/main/dev/index.ts) must be impossible to enable without ALONGSIDE_DEV_STAGE=1.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Services } from '../../shared/contracts'
import type { ServiceContext } from '../context'

vi.mock('electron', () => ({
  BrowserWindow: class {
    static getAllWindows(): unknown[] {
      return []
    }
  },
  screen: { getPrimaryDisplay: () => ({ id: 1, bounds: { x: 0, y: 0, width: 100, height: 100 }, scaleFactor: 1 }) },
  systemPreferences: { getMediaAccessStatus: () => 'denied' },
}))

const SAVED = { ...process.env }
beforeEach(() => {
  delete process.env.ALONGSIDE_DEV_STAGE
  delete process.env.ALONGSIDE_RECORD
  delete process.env.ALONGSIDE_REPLAY
})
afterEach(() => {
  process.env = { ...SAVED }
})

function fakeServices(): Services {
  const capture = { grab: vi.fn(), liveFrame: vi.fn(), watch: vi.fn() }
  const overlay = { show: vi.fn(), clear: vi.fn(), caption: vi.fn(), chip: vi.fn() }
  const live = { inject: vi.fn() }
  return { capture, overlay, live } as unknown as Services
}

describe('dev capture override gating', () => {
  it('leaves capture, overlay and live untouched unless ALONGSIDE_DEV_STAGE=1', async () => {
    const { installDev } = await import('../dev')
    const services = fakeServices()
    const before = { ...services.capture }
    const overlayBefore = { ...services.overlay }
    const ctx = { userDataDir: null, log: vi.fn(), settings: {}, bus: {}, state: {} } as unknown as ServiceContext
    installDev({ ctx, services })
    expect(services.capture.grab).toBe(before.grab)
    expect(services.capture.liveFrame).toBe(before.liveFrame)
    expect(services.capture.watch).toBe(before.watch)
    expect(services.overlay.show).toBe(overlayBefore.show)
  })
  it('a different truthy value does not enable it (only the literal "1" does)', async () => {
    process.env.ALONGSIDE_DEV_STAGE = 'true'
    const { installDev } = await import('../dev')
    const services = fakeServices()
    const grab = services.capture.grab
    installDev({ ctx: { userDataDir: null, log: vi.fn() } as unknown as ServiceContext, services })
    expect(services.capture.grab).toBe(grab)
  })
})
