import { describe, expect, it } from 'vitest'
import { createKeepAwake, desiredBlocker, type BlockerPort, type BlockerType } from './keep-awake'

function fakePort(over: { throwOnStart?: boolean } = {}) {
  const live = new Map<number, BlockerType>()
  const calls: string[] = []
  let next = 1
  const port: BlockerPort = {
    start: (t) => {
      if (over.throwOnStart) throw new Error('no power service')
      const id = next++
      live.set(id, t)
      calls.push(`start ${t}`)
      return id
    },
    stop: (id) => {
      live.delete(id)
      calls.push(`stop ${id}`)
    },
    isStarted: (id) => live.has(id),
  }
  return { port, live, calls }
}

describe('what to hold', () => {
  it('nothing unless a run is working and the setting is on', () => {
    expect(desiredBlocker({ working: false, realScreen: false, enabled: true })).toBeNull()
    expect(desiredBlocker({ working: true, realScreen: true, enabled: false })).toBeNull()
  })
  it('the app alone for a run in the background, and the display too for a run on the real screen', () => {
    expect(desiredBlocker({ working: true, realScreen: false, enabled: true })).toBe('prevent-app-suspension')
    expect(desiredBlocker({ working: true, realScreen: true, enabled: true })).toBe('prevent-display-sleep')
  })
})

describe('holding it only for a run', () => {
  it('takes one blocker when the run starts, none while idle, and gives it back when the run ends', () => {
    const f = fakePort()
    const k = createKeepAwake(f.port)
    k.update({ working: false, realScreen: false, enabled: true })
    expect(f.calls).toEqual([])
    k.update({ working: true, realScreen: false, enabled: true })
    k.update({ working: true, realScreen: false, enabled: true }) // the same state again: nothing more
    expect(f.calls).toEqual(['start prevent-app-suspension'])
    expect(k.held()).toBe('prevent-app-suspension')
    k.update({ working: false, realScreen: false, enabled: true })
    expect(f.calls).toEqual(['start prevent-app-suspension', 'stop 1'])
    expect(f.live.size).toBe(0)
    expect(k.held()).toBeNull()
  })
  it('swaps to the stronger blocker when the run turns out to use the real screen, never holding two', () => {
    const f = fakePort()
    const k = createKeepAwake(f.port)
    k.update({ working: true, realScreen: false, enabled: true })
    k.update({ working: true, realScreen: true, enabled: true })
    expect(f.calls).toEqual(['start prevent-app-suspension', 'stop 1', 'start prevent-display-sleep'])
    expect(f.live.size).toBe(1)
  })
  it('lets go when the setting is switched off mid-run, and when the app quits', () => {
    const f = fakePort()
    const k = createKeepAwake(f.port)
    k.update({ working: true, realScreen: false, enabled: true })
    k.update({ working: true, realScreen: false, enabled: false })
    expect(f.live.size).toBe(0)
    k.update({ working: true, realScreen: false, enabled: true })
    expect(f.live.size).toBe(1)
    k.dispose()
    expect(f.live.size).toBe(0)
    k.dispose() // twice is fine
  })
  it('a blocker that cannot be taken never stops a run', () => {
    const f = fakePort({ throwOnStart: true })
    const logs: unknown[][] = []
    const k = createKeepAwake(f.port, (...a) => void logs.push(a))
    expect(() => k.update({ working: true, realScreen: false, enabled: true })).not.toThrow()
    expect(k.held()).toBeNull()
    expect(logs.some((l) => String(l[1]).startsWith('could not hold'))).toBe(true)
  })
  it('forgets a blocker the system already dropped', () => {
    const f = fakePort()
    const k = createKeepAwake(f.port)
    k.update({ working: true, realScreen: false, enabled: true })
    f.live.clear() // the system took it away
    k.update({ working: false, realScreen: false, enabled: true })
    expect(f.calls).toEqual(['start prevent-app-suspension'])
    expect(k.held()).toBeNull()
  })
})
