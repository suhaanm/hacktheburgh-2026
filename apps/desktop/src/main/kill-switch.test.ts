import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { isKilled, setKilled } from './kill-flag'
import { createKillSwitch, STOPPED_LINE, type KillDeps } from './kill-switch'

afterEach(() => setKilled(false))

function setup(over: Partial<KillDeps> = {}) {
  const calls: string[] = []
  let t = 1000
  const deps: KillDeps = {
    stopSession: (r) => void calls.push(`session:${r}`),
    stopAgency: () => void calls.push('agency'),
    stopCoach: () => void calls.push('ring'),
    stopShowtime: () => void calls.push('showtime'),
    cancelConfirm: () => void calls.push('confirm'),
    agents: () => [
      { id: 'a1', status: 'running' },
      { id: 'a2', status: 'done' },
    ],
    cancelAgent: (id) => void calls.push(`agent:${id}`),
    overlay: { clear: () => void calls.push('overlay.clear'), caption: (_s, text) => void calls.push(`caption:${text}`) },
    engine: { kill: async () => (calls.push('engine.kill'), { engine: true, agent: true }), clearKill: async () => (calls.push('engine.clear'), { engine: true, agent: false }) },
    now: () => (t += 5),
    ...over,
  }
  return { ks: createKillSwitch(deps), calls }
}

describe('kill switch', () => {
  it('stops everything local first, in order, sets the global flag, says so, then calls the engine and agent', async () => {
    const { ks, calls } = setup()
    const seen: boolean[] = []
    ks.subscribe((s) => seen.push(s.killed))
    const report = await ks.trigger('hotkey')
    expect(calls).toEqual(['agency', 'confirm', 'agent:a1', 'ring', 'showtime', 'session:stop', 'overlay.clear', `caption:${STOPPED_LINE}`, 'engine.kill'])
    expect(isKilled()).toBe(true)
    expect(ks.isKilled()).toBe(true)
    expect(report).toMatchObject({ source: 'hotkey', engine: true, agent: true })
    expect(ks.state()).toMatchObject({ killed: true, source: 'hotkey', engine: true, agent: true })
    expect(seen).toEqual([true, true]) // once after the local stop, once after the network leg
  })

  it('the flag is already on and the local stop already done before the network leg finishes (a slow engine never delays Stop)', async () => {
    let release: (v: { engine: boolean; agent: boolean }) => void = () => undefined
    const slow = new Promise<{ engine: boolean; agent: boolean }>((r) => (release = r))
    const { ks, calls } = setup({ engine: { kill: () => slow, clearKill: async () => ({ engine: true, agent: true }) } })
    const pending = ks.trigger('tray')
    expect(isKilled()).toBe(true)
    expect(calls).toContain('session:stop')
    expect(ks.state()).toMatchObject({ killed: true, engine: null })
    release({ engine: false, agent: false })
    expect(await pending).toMatchObject({ engine: false, agent: false })
  })

  it('every local step still runs when an earlier one throws, and an unreachable engine is not an error', async () => {
    const { ks, calls } = setup({
      stopAgency: () => {
        throw new Error('boom')
      },
      engine: {
        kill: async () => {
          throw new Error('ECONNREFUSED')
        },
        clearKill: async () => ({ engine: false, agent: false }),
      },
    })
    const report = await ks.trigger('hud')
    expect(calls).toContain('session:stop')
    expect(calls).toContain('overlay.clear')
    expect(report).toMatchObject({ engine: false, agent: false })
    expect(isKilled()).toBe(true)
  })

  it('stays on until Resume, which clears the flag and the engine kill', async () => {
    const { ks, calls } = setup()
    await ks.trigger('hotkey')
    await ks.trigger('hotkey') // pressing twice is harmless
    expect(isKilled()).toBe(true)
    await ks.clear()
    expect(isKilled()).toBe(false)
    expect(ks.state()).toMatchObject({ killed: false, source: null })
    expect(calls).toContain('engine.clear')
    expect(calls.at(-2)).toBe('caption:Resumed.')
  })

  it('the local stop takes far less than the one second the spec allows', async () => {
    const { ks } = setup({ now: () => Date.now() })
    const t0 = Date.now()
    const p = ks.trigger('cli')
    expect(Date.now() - t0).toBeLessThan(100) // everything before the first await is synchronous
    await p
  })
})

describe('data/KILL (the file the Python actuators poll)', () => {
  const fs = require('node:fs') as typeof import('node:fs')
  const os = require('node:os') as typeof import('node:os')
  const path = require('node:path') as typeof import('node:path')
  let dir = ''
  beforeEach(() => {
    dir = fs.mkdtempSync(path.join(os.tmpdir(), 'understudy-kill-'))
    process.env.UNDERSTUDY_DATA_DIR = dir
  })
  afterEach(() => {
    delete process.env.UNDERSTUDY_DATA_DIR
    fs.rmSync(dir, { recursive: true, force: true })
  })
  const make = (killFn: () => Promise<{ engine: boolean; agent: boolean }>) => {
    const noop = (): void => undefined
    return createKillSwitch({ stopSession: noop, stopAgency: noop, stopShowtime: noop, cancelConfirm: noop, agents: () => [], cancelAgent: noop, overlay: { clear: noop, caption: noop }, engine: { kill: killFn, clearKill: async () => ({ engine: false, agent: false }) } })
  }

  it('is on disk within 100 ms of the press, with no service running, from every source (hotkey, tray, HUD pill)', async () => {
    for (const source of ['hotkey', 'tray', 'hud'] as const) {
      const ks = make(async () => {
        throw new Error('ECONNREFUSED')
      })
      const t0 = Date.now()
      const done = ks.trigger(source) // not awaited: the file must not wait for the network leg
      expect(fs.existsSync(path.join(dir, 'KILL'))).toBe(true) // synchronous: already there when trigger() returned its promise
      expect(Date.now() - t0).toBeLessThan(100)
      const report = await done
      expect(report.file).toBe(true)
      expect(ks.state().file).toBe(true)
      const body = JSON.parse(fs.readFileSync(path.join(dir, 'KILL'), 'utf8')) as { source: string }
      expect(body.source).toBe(source)
      expect(fs.readdirSync(dir).filter((f) => f.endsWith('.tmp'))).toEqual([]) // written by rename: no half file left
      await ks.clear()
      expect(fs.existsSync(path.join(dir, 'KILL'))).toBe(false) // Resume removes it
    }
  })

  it('a failed write is reported, never thrown, and the rest of the stop still happens', async () => {
    process.env.UNDERSTUDY_DATA_DIR = path.join(dir, 'KILL-is-a-file', 'nope')
    fs.writeFileSync(path.join(dir, 'KILL-is-a-file'), 'x') // the data dir cannot be created under a regular file
    const stopped: string[] = []
    const noop = (): void => undefined
    const ks = createKillSwitch({ stopSession: () => void stopped.push('session'), stopAgency: noop, stopShowtime: noop, cancelConfirm: noop, agents: () => [], cancelAgent: noop, overlay: { clear: noop, caption: noop }, engine: { kill: async () => ({ engine: true, agent: true }), clearKill: async () => ({ engine: true, agent: true }) } })
    const report = await ks.trigger('hotkey')
    expect(report.file).toBe(false)
    expect(stopped).toEqual(['session'])
    expect(ks.isKilled()).toBe(true)
  })

  it('a test run without a private data dir never touches the shared <repo>/data/KILL', async () => {
    delete process.env.UNDERSTUDY_DATA_DIR
    const ks = make(async () => ({ engine: false, agent: false }))
    const report = await ks.trigger('hotkey')
    expect(report.file).toBe(false)
  })
})
