import { mkdtemp, readFile, rm, stat, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import type { Settings } from '../../shared/settings'
import type { ShowtimeState } from '../../shared/showtime'
import { buildChapters } from './chapters'
import type { Driver } from './driver'
import { FakeClock } from './fake-clock'
import { Bus } from '../bus'
import { bindShowtimeBus, createShowtime, dockStopBox, type ShowtimeDeps } from './service'
import type { StageWindow } from './stage-window'
import type { Action } from './types'

let dir = ''
let assets = ''
beforeEach(async () => {
  dir = await mkdtemp(path.join(os.tmpdir(), 'showtime-svc-user-'))
  assets = await mkdtemp(path.join(os.tmpdir(), 'showtime-svc-assets-'))
  await writeFile(path.join(assets, 'demo-profile.md'), '# demo seed\n')
})
afterEach(async () => {
  await rm(dir, { recursive: true, force: true })
  await rm(assets, { recursive: true, force: true })
})

async function until(cond: () => boolean | Promise<boolean>, ms = 3000): Promise<void> {
  const end = Date.now() + ms
  while (Date.now() < end) {
    if (await cond()) return
    await new Promise((r) => setTimeout(r, 10))
  }
  throw new Error('timed out waiting for condition')
}
const exists = (f: string): Promise<boolean> => stat(f).then(() => true, () => false)
const total = (full = false): number => buildChapters({ full }).reduce((s, c) => s + c.durationMs, 0)

function setup(over: { settings?: Record<string, unknown>; openStage?: () => Promise<StageWindow>; env?: NodeJS.ProcessEnv; phase?: string; userDataDir?: string | null } = {}) {
  const clock = new FakeClock()
  const actions: Action[] = []
  const published: ShowtimeState[] = []
  const calls: string[] = []
  const stage = { close: () => calls.push('stage.close'), isOpen: () => true } as unknown as StageWindow
  const driver: Driver = {
    exec: async (a) => void actions.push(a),
    pauseAudio: () => undefined,
    resumeAudio: () => undefined,
    teardown: async () => void calls.push('driver.teardown'),
  }
  const deps: ShowtimeDeps = {
    ctx: {
      state: { get: () => ({ phase: over.phase ?? 'asleep' }) },
      bus: undefined,
      settings: { get: () => ({ agency: 'ask_each', wakeEnabled: true, ...(over.settings ?? {}) }) as unknown as Settings },
      userDataDir: over.userDataDir === undefined ? dir : over.userDataDir,
    } as unknown as ShowtimeDeps['ctx'],
    openStage: over.openStage ?? (async () => stage),
    makeDriver: () => driver,
    publish: (s) => published.push(s),
    stopSession: () => calls.push('stopSession'),
    reloadLearner: async () => void calls.push('reloadLearner'),
    hasFiles: () => true,
    assetsDir: assets,
    log: () => undefined,
    clock,
    env: over.env ?? {},
  }
  return { svc: createShowtime(deps), clock, actions, published, calls }
}

describe('showtime service', () => {
  it('starts in scripted mode by default with the badge on, and publishes state', async () => {
    const h = setup()
    await h.svc.start()
    const s = h.svc.state()
    expect(s.running).toBe(true)
    expect(s.mode).toBe('scripted')
    expect(s.badge).toBe(true)
    expect(s.full).toBe(false)
    expect(h.svc.active()).toBe(true)
    expect(h.published.length).toBeGreaterThan(0)
    await h.clock.advance(1000)
    expect(h.actions[0]).toMatchObject({ type: 'baseline' })
    await h.svc.stop()
  })

  it('honours explicit options and the badge / mode environment switches', async () => {
    const h = setup({ env: { ALONGSIDE_SHOWTIME_BADGE: '0', ALONGSIDE_SHOWTIME_MODE: 'live' } })
    await h.svc.start({ full: true })
    const s = h.svc.state()
    expect(s.badge).toBe(false)
    expect(s.mode).toBe('live')
    expect(s.full).toBe(true)
    await h.svc.stop()
    const h2 = setup({ env: { ALONGSIDE_SHOWTIME_MODE: 'live' } })
    await h2.svc.start({ mode: 'scripted' })
    expect(h2.svc.state().mode).toBe('scripted')
    await h2.svc.stop()
  })

  it('a second start while running does nothing', async () => {
    const h = setup()
    await h.svc.start()
    const n = h.published.length
    await h.svc.start()
    expect(h.published.length).toBe(n)
    await h.svc.stop()
  })

  it('stop tears everything down, restores the real profile and reports idle', async () => {
    await writeFile(path.join(dir, 'profile.md'), '# my real profile\n')
    const h = setup()
    await h.svc.start()
    expect(await readFile(path.join(dir, 'profile.md'), 'utf8')).toBe('# demo seed\n')
    await h.clock.advance(5000)
    await h.svc.stop()
    expect(await readFile(path.join(dir, 'profile.md'), 'utf8')).toBe('# my real profile\n')
    expect(h.calls).toContain('driver.teardown')
    expect(h.calls).toContain('stage.close')
    expect(h.svc.active()).toBe(false)
    expect(h.svc.state().running).toBe(false)
    expect(h.published.at(-1)?.running).toBe(false)
    expect(h.published.at(-1)?.chapterIndex).toBe(-1)
    expect(h.clock.pending).toBe(0)
  })

  it('a missing profile is removed again after the tour', async () => {
    const h = setup()
    await h.svc.start()
    expect(await exists(path.join(dir, 'profile.md'))).toBe(true)
    await h.svc.stop()
    expect(await exists(path.join(dir, 'profile.md'))).toBe(false)
  })

  it('a finished tour restores profile and settings but keeps the practice desktop until Stop', async () => {
    await writeFile(path.join(dir, 'profile.md'), '# mine\n')
    const h = setup()
    await h.svc.start()
    await h.clock.advance(total() + 2000)
    const s = h.svc.state()
    expect(s.running).toBe(false)
    expect(s.handover).toBe(true)
    expect(h.svc.active()).toBe(true)
    // The real profile comes back (file I/O is real, so wait for it).
    await until(async () => (await readFile(path.join(dir, 'profile.md'), 'utf8')) === '# mine\n')
    expect(h.calls).toContain('driver.teardown')
    expect(h.calls).not.toContain('stage.close')
    await h.svc.stop()
    expect(h.calls).toContain('stage.close')
    expect(h.svc.active()).toBe(false)
  })

  it('every chapter runs in order in a full-length scripted run', async () => {
    const h = setup()
    await h.svc.start()
    await h.clock.advance(total() + 1000)
    const baselines = h.actions.filter((a) => a.type === 'baseline').length
    expect(baselines).toBe(11)
    await h.svc.stop()
  })

  it('next, prev and pause reach the machine', async () => {
    const h = setup()
    await h.svc.start()
    h.svc.next()
    expect(h.svc.state().chapterIndex).toBe(1)
    h.svc.prev()
    expect(h.svc.state().chapterIndex).toBe(0)
    h.svc.pause()
    expect(h.svc.state().paused).toBe(true)
    h.svc.pause()
    expect(h.svc.state().paused).toBe(false)
    await h.svc.stop()
  })

  it('next, prev, pause and stop while idle are harmless', async () => {
    const h = setup()
    h.svc.next()
    h.svc.prev()
    h.svc.pause()
    await h.svc.stop()
    expect(h.svc.state().running).toBe(false)
    expect(h.svc.active()).toBe(false)
  })

  it('skips the agency chapter when this build has no agency setting, and the tour still completes', async () => {
    const clock = new FakeClock()
    const states: ShowtimeState[] = []
    const svc = createShowtime({
      ctx: { state: { get: () => ({ phase: 'asleep' }) }, settings: { get: () => ({ wakeEnabled: true }) as unknown as Settings }, userDataDir: null } as unknown as ShowtimeDeps['ctx'],
      openStage: async () => ({ close: () => undefined }) as unknown as StageWindow,
      makeDriver: () => ({ exec: async () => undefined, pauseAudio: () => undefined, resumeAudio: () => undefined, teardown: async () => undefined }),
      publish: (s) => states.push(s),
      stopSession: () => undefined,
      reloadLearner: async () => undefined,
      hasFiles: () => true,
      assetsDir: assets,
      log: () => undefined,
      clock,
      env: {},
    })
    await svc.start()
    const agency = svc.state().chapters.find((c) => c.id === 'do-it-for-you')
    expect(agency?.status).toBe('unavailable')
    expect(agency?.reason).toMatch(/agency/)
    await clock.advance(total() + 1000)
    expect(svc.state().handover).toBe(true)
    await svc.stop()
  })

  it('in live mode the files chapter is skipped when the files service is absent', async () => {
    const clock = new FakeClock()
    const svc = createShowtime({
      ctx: { state: { get: () => ({ phase: 'asleep' }) }, settings: { get: () => ({ agency: 'off', wakeEnabled: true }) as unknown as Settings }, userDataDir: null } as unknown as ShowtimeDeps['ctx'],
      openStage: async () => ({ close: () => undefined }) as unknown as StageWindow,
      makeDriver: () => ({ exec: async () => undefined, pauseAudio: () => undefined, resumeAudio: () => undefined, teardown: async () => undefined }),
      publish: () => undefined,
      stopSession: () => undefined,
      reloadLearner: async () => undefined,
      hasFiles: () => false,
      assetsDir: assets,
      log: () => undefined,
      clock,
      env: {},
    })
    await svc.start({ mode: 'live' })
    expect(svc.state().chapters.find((c) => c.id === 'your-files')?.status).toBe('unavailable')
    await svc.stop()
    await svc.start({ mode: 'scripted' })
    expect(svc.state().chapters.find((c) => c.id === 'your-files')?.status).not.toBe('unavailable')
    await svc.stop()
  })

  it('if the practice desktop cannot open, nothing is left changed and the tour never runs', async () => {
    await writeFile(path.join(dir, 'profile.md'), '# mine\n')
    const h = setup({
      openStage: async () => {
        throw new Error('no display')
      },
    })
    await h.svc.start()
    expect(h.svc.state().running).toBe(false)
    expect(h.svc.active()).toBe(false)
    expect(await readFile(path.join(dir, 'profile.md'), 'utf8')).toBe('# mine\n')
    expect(await exists(path.join(dir, 'profile.md.showtime-backup'))).toBe(false)
  })

  it('starting ends a running Live session first', async () => {
    const h = setup({ phase: 'live' })
    await h.svc.start()
    expect(h.calls[0]).toBe('stopSession')
    await h.svc.stop()
    const idle = setup({ phase: 'asleep' })
    await idle.svc.start()
    expect(idle.calls).not.toContain('stopSession')
    await idle.svc.stop()
  })

  it('works without a user data directory (no profile swap)', async () => {
    const h = setup({ userDataDir: null })
    await h.svc.start()
    expect(h.svc.state().running).toBe(true)
    await h.svc.stop()
    expect(h.calls).toContain('stage.close')
  })

  it('stop requested while the stage is still opening cancels the start', async () => {
    let release: ((s: StageWindow) => void) | null = null
    const closed: string[] = []
    const h = setup({ openStage: () => new Promise<StageWindow>((r) => (release = r)) })
    const starting = h.svc.start()
    await until(() => release !== null)
    const stopping = h.svc.stop()
    ;(release as unknown as (s: StageWindow) => void)({ close: () => closed.push('closed') } as unknown as StageWindow)
    await starting
    await stopping
    await until(() => closed.length > 0)
    expect(h.svc.state().running).toBe(false)
    expect(closed).toEqual(['closed'])
  })
})

describe('showtime bus requests', () => {
  it('the tray request starts the tour, a second tray click stops it, and the dock Stop button ends it too', async () => {
    const bus = new Bus()
    const h = setup()
    bindShowtimeBus(bus, h.svc, () => undefined)
    bus.emit('showtime:request', { source: 'tray' })
    await until(() => h.svc.state().running)
    expect(h.svc.state().mode).toBe('scripted')
    bus.emit('showtime:request', { source: 'tray', stop: true })
    await until(() => !h.svc.active())
    expect(h.calls).toContain('stage.close')

    bus.emit('showtime:request', { source: 'dock', full: true })
    await until(() => h.svc.state().running)
    expect(h.svc.state().full).toBe(true)
    bus.emit('session:ended', { reason: 'idle' })
    expect(h.svc.state().running).toBe(true)
    bus.emit('session:ended', { reason: 'stop' })
    await until(() => !h.svc.active())
  })

  it('a stop request with nothing running is harmless', async () => {
    const bus = new Bus()
    const h = setup()
    bindShowtimeBus(bus, h.svc, () => undefined)
    bus.emit('showtime:request', { source: 'tray', stop: true })
    bus.emit('session:ended', { reason: 'stop' })
    expect(h.svc.active()).toBe(false)
  })
})

describe('dock stop box', () => {
  it('lands inside the display, bottom-right, in 0..1000 space', () => {
    const b = dockStopBox({ x: 0, y: 0, width: 1440, height: 900 }, { x: 0, y: 25, width: 1440, height: 875 })
    for (const v of [b.xmin, b.ymin, b.xmax, b.ymax]) {
      expect(v).toBeGreaterThanOrEqual(0)
      expect(v).toBeLessThanOrEqual(1000)
    }
    expect(b.xmax).toBeGreaterThan(b.xmin)
    expect(b.ymax).toBeGreaterThan(b.ymin)
    expect(b.xmin).toBeGreaterThan(800)
    expect(b.ymin).toBeGreaterThan(800)
  })
})
