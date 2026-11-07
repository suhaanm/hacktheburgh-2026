import { describe, expect, it } from 'vitest'
import { LoopWatcher, StopTracker, actionSignature, createLoopHasher, detectLoop } from './loop'

describe('actionSignature', () => {
  it('rounds coordinates into 24 px buckets, so near-identical repeats compare equal', () => {
    const a = actionSignature({ kind: 'stop', appKind: 'browser', x: 500, y: 300 })
    const b = actionSignature({ kind: 'stop', appKind: 'browser', x: 503, y: 311 }) // same 24 px bucket
    const c = actionSignature({ kind: 'stop', appKind: 'browser', x: 530, y: 300 }) // next bucket over
    expect(a).toBe(b)
    expect(a).not.toBe(c)
  })

  it('a zone beats coordinates; cosmetic fields cannot change the signature', () => {
    const a = actionSignature({ kind: 'click', zone: 'cliff_button', x: 1, y: 1 })
    const b = actionSignature({ kind: 'click', zone: 'cliff_button', x: 900, y: 700 })
    expect(a).toBe(b)
    expect(actionSignature({ kind: 'CLICK', zone: 'cliff_button' })).toBe(a.replace('|-|', '|-|'))
    expect(actionSignature({ kind: 'click', zone: 'case_note' })).not.toBe(a)
  })

  it('text enters only as the given hash', () => {
    const h = createLoopHasher(Buffer.from('salt-one'))
    const h2 = createLoopHasher(Buffer.from('salt-two'))
    const title = 'Quarterly review - Alice Smith'
    const sig = actionSignature({ kind: 'nav', textHash: h(title) })
    expect(sig).not.toContain('Alice')
    expect(h(title)).toMatch(/^[0-9a-f]{8}$/)
    expect(h(title)).toBe(h(title))
    expect(h(title)).not.toBe(h2(title)) // salted: not comparable across sessions
  })
})

describe('detectLoop', () => {
  it('same signature four times in a row', () => {
    expect(detectLoop(['a', 'a', 'a'])).toBeNull()
    expect(detectLoop(['a', 'a', 'a', 'a'])).toEqual({ kind: 'same', period: 1 })
    expect(detectLoop(['x', 'b', 'a', 'a', 'a', 'a'])).toEqual({ kind: 'same', period: 1 })
    expect(detectLoop(['a', 'a', 'b', 'a', 'a'])).toBeNull()
  })

  it('a cycle of period 2 to 4 repeated three times', () => {
    expect(detectLoop(['a', 'b', 'a', 'b'])).toBeNull()
    expect(detectLoop(['a', 'b', 'a', 'b', 'a', 'b'])).toEqual({ kind: 'cycle', period: 2 })
    expect(detectLoop(['z', 'a', 'b', 'c', 'a', 'b', 'c', 'a', 'b', 'c'])).toEqual({ kind: 'cycle', period: 3 })
    expect(detectLoop(['a', 'b', 'c', 'd', 'a', 'b', 'c', 'd', 'a', 'b', 'c', 'd'])).toEqual({ kind: 'cycle', period: 4 })
    // a cycle of period 5 is not a loop by this rule
    const p5 = ['a', 'b', 'c', 'd', 'e']
    expect(detectLoop([...p5, ...p5, ...p5])).toBeNull()
  })

  it('near misses are not loops', () => {
    expect(detectLoop(['a', 'b', 'a', 'b', 'a', 'c'])).toBeNull()
    expect(detectLoop(['a', 'b', 'c', 'a', 'b', 'a', 'b', 'c'])).toBeNull()
  })
})

describe('LoopWatcher', () => {
  it('fires once per loop and then starts fresh', () => {
    let t = 0
    const w = new LoopWatcher(() => t)
    expect([1, 2, 3].map(() => w.push('s'))).toEqual([null, null, null])
    expect(w.push('s')).toEqual({ kind: 'same', period: 1 })
    expect(w.size()).toBe(0)
    expect(w.push('s')).toBeNull()
  })

  it('forgets signatures older than the TTL, so a loop cannot span a long gap', () => {
    let t = 0
    const w = new LoopWatcher(() => t, 60_000)
    w.push('s')
    w.push('s')
    t += 120_000
    w.push('s')
    expect(w.push('s')).toBeNull() // only two are within the TTL
  })

  it('keeps only a short ring', () => {
    let t = 0
    const w = new LoopWatcher(() => t++, 1e9, 5)
    for (let i = 0; i < 20; i++) w.push(`s${i}`)
    expect(w.size()).toBe(5)
  })
})

describe('StopTracker', () => {
  const stop = (zone: string | null, bx = 10, by = 10, dwell = 1.9) => ({ dwell_s: dwell, anchor: { bx, by }, zone, appKind: 'browser' })

  it('a dwell that continues across windows at the same place is one stop', () => {
    const t = new StopTracker()
    const first = t.observe(stop(null))
    expect(first).toMatch(/^stop\|browser\|b:10,10/)
    expect(t.observe(stop(null))).toBeNull()
    expect(t.observe(stop(null))).toBeNull()
  })

  it('leaving and coming back is a new stop', () => {
    const t = new StopTracker()
    expect(t.observe(stop(null))).not.toBeNull()
    expect(t.observe({ dwell_s: 0, anchor: null, zone: null, appKind: 'browser' })).toBeNull()
    expect(t.observe(stop(null))).not.toBeNull()
  })

  it('four returns to the same button complete a loop through the watcher', () => {
    let t = 0
    const w = new LoopWatcher(() => t)
    const tracker = new StopTracker()
    let hit = null
    for (let i = 0; i < 4; i++) {
      const sig = tracker.observe(stop('calc_result'))
      if (sig) hit = w.push(sig)
      tracker.observe({ dwell_s: 0, anchor: null, zone: null, appKind: 'browser' })
      t += 4000
    }
    expect(hit).toEqual({ kind: 'same', period: 1 })
  })
})
