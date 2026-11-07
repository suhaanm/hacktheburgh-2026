import { describe, expect, it, vi } from 'vitest'
import { createVoiceLock, PREEMPTS, type LockOwner } from './lock'

const mk = () => {
  let t = 1_000_000
  const lock = createVoiceLock(() => t)
  return { lock, tick: (ms: number) => void (t += ms) }
}

describe('the one-voice lock', () => {
  it('is free at first, then belongs to whoever took it', () => {
    const { lock } = mk()
    expect(lock.holder()).toBeNull()
    expect(lock.acquire('cue', 12_000)).toBe(true)
    expect(lock.holder()?.owner).toBe('cue')
    expect(lock.acquire('notice', 20_000)).toBe(false)
    expect(lock.acquire('decision', 20_000)).toBe(false)
    expect(lock.acquire('glance', 2_000)).toBe(false)
  })

  it('runs out by itself so a crashed holder never blocks everything', () => {
    const { lock, tick } = mk()
    expect(lock.acquire('cue', 12_000)).toBe(true)
    tick(11_999)
    expect(lock.holder()).not.toBeNull()
    tick(2)
    expect(lock.holder()).toBeNull()
    expect(lock.acquire('notice', 20_000)).toBe(true)
  })

  it('a non-positive or silly ttl still expires (never forever)', () => {
    const { lock, tick } = mk()
    expect(lock.acquire('cue', Number.NaN)).toBe(true)
    tick(1_001)
    expect(lock.holder()).toBeNull()
    expect(lock.acquire('cue', Number.POSITIVE_INFINITY)).toBe(true)
    tick(120_001)
    expect(lock.holder()).toBeNull()
  })

  it('only safety preempts a holder, and the holder is told to hide at once', () => {
    const { lock } = mk()
    const hide = vi.fn()
    expect(lock.acquire('cue', 12_000, hide)).toBe(true)
    expect(lock.acquire('decision', 20_000)).toBe(false)
    expect(lock.acquire('safety', 20_000)).toBe(true)
    expect(hide).toHaveBeenCalledTimes(1)
    expect(lock.holder()?.owner).toBe('safety')
    expect(lock.acquire('safety', 20_000)).toBe(true) // the same owner continuing
    expect(lock.acquire('cue', 12_000)).toBe(false)
    expect(lock.acquire('asked', 12_000)).toBe(false)
  })

  it("the worker's own ask preempts a cue or a notice but not an approval toast or safety", () => {
    const { lock } = mk()
    const hide = vi.fn()
    lock.acquire('cue', 12_000, hide)
    expect(lock.acquire('asked', 12_000)).toBe(true)
    expect(hide).toHaveBeenCalledTimes(1)
    lock.release('asked')
    lock.acquire('decision', 20_000)
    expect(lock.acquire('asked', 12_000)).toBe(false)
  })

  it('two things of the same owner never coexist: the same key continues, another waits', () => {
    const { lock } = mk()
    expect(lock.acquire('decision', 20_000, undefined, 'confirm_1')).toBe(true)
    expect(lock.acquire('decision', 20_000, undefined, 'confirm_1')).toBe(true)
    expect(lock.acquire('decision', 20_000, undefined, 'i_other')).toBe(false)
    expect(lock.available('decision', 'i_other')).toBe(false)
    lock.release('decision', 'i_other')
    expect(lock.holder()?.key).toBe('confirm_1')
    lock.release('decision', 'confirm_1')
    expect(lock.acquire('decision', 20_000, undefined, 'i_other')).toBe(true)
  })

  it('a holder that throws while hiding does not keep the voice', () => {
    const { lock } = mk()
    lock.acquire('notice', 20_000, () => {
      throw new Error('boom')
    })
    expect(lock.acquire('safety', 20_000)).toBe(true)
  })

  it('release is a no-op for a non-holder; extend only lengthens the holder', () => {
    const { lock, tick } = mk()
    lock.acquire('cue', 5_000)
    lock.release('notice')
    expect(lock.holder()?.owner).toBe('cue')
    lock.extend('notice', 60_000)
    lock.extend('cue', 10_000)
    tick(9_000)
    expect(lock.holder()?.owner).toBe('cue')
    lock.release('cue')
    expect(lock.holder()).toBeNull()
  })

  it('available() agrees with acquire() without taking anything', () => {
    const { lock } = mk()
    lock.acquire('cue', 12_000)
    const owners: LockOwner[] = ['safety', 'asked', 'decision', 'cue', 'notice', 'glance']
    for (const o of owners) {
      expect(lock.available(o)).toBe(o === 'cue' || PREEMPTS[o].includes('cue'))
    }
    expect(lock.holder()?.owner).toBe('cue')
  })
})
