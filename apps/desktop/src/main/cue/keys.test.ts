import { describe, expect, it, vi } from 'vitest'
import { CueCardActionSchema, CueSizeSchema } from './action-schema'
import { createKeys, type ShortcutApi } from './keys'

function fakeApi(taken: string[] = [], failing: string[] = []): ShortcutApi & { bound: Map<string, () => void>; log: string[] } {
  const bound = new Map<string, () => void>()
  const log: string[] = []
  return {
    bound,
    log,
    register(a, cb) {
      if (failing.includes(a)) throw new Error('rejected')
      if (taken.includes(a) || bound.has(a)) return false
      bound.set(a, cb)
      log.push(`+${a}`)
      return true
    },
    unregister(a) {
      bound.delete(a)
      log.push(`-${a}`)
    },
    isRegistered: (a) => taken.includes(a) || bound.has(a),
  }
}
const handlers = () => ({ answer: vi.fn(), other: vi.fn(), dismiss: vi.fn() })

describe('the keys while a cue is up', () => {
  it('a question with three options takes Alt+1..3, Alt+0 and Alt+Escape, and nothing else', () => {
    const api = fakeApi()
    const h = handlers()
    createKeys(api, h).set({ answers: 3, dismiss: true })
    expect([...api.bound.keys()].sort()).toEqual(['Alt+0', 'Alt+1', 'Alt+2', 'Alt+3', 'Alt+Escape'])
    api.bound.get('Alt+2')?.()
    api.bound.get('Alt+0')?.()
    api.bound.get('Alt+Escape')?.()
    expect(h.answer).toHaveBeenCalledWith(2)
    expect(h.other).toHaveBeenCalledOnce()
    expect(h.dismiss).toHaveBeenCalledOnce()
  })

  it('a chip takes only Alt+Escape; nothing at all when nothing is up', () => {
    const api = fakeApi()
    const k = createKeys(api, handlers())
    k.set({ answers: 0, dismiss: true })
    expect([...api.bound.keys()]).toEqual(['Alt+Escape'])
    k.set({ answers: 0, dismiss: false })
    expect(api.bound.size).toBe(0)
  })

  it('gives every key back when the cue goes, and again when the keys are changed', () => {
    const api = fakeApi()
    const k = createKeys(api, handlers())
    k.set({ answers: 4, dismiss: true })
    expect(api.bound.size).toBe(6)
    k.set({ answers: 2, dismiss: true })
    expect([...api.bound.keys()].sort()).toEqual(['Alt+0', 'Alt+1', 'Alt+2', 'Alt+Escape'])
    k.off()
    expect(api.bound.size).toBe(0)
    expect(k.registered()).toEqual([])
  })

  it('never more than four answers', () => {
    const api = fakeApi()
    createKeys(api, handlers()).set({ answers: 9, dismiss: false })
    expect([...api.bound.keys()].filter((a) => /^Alt\+\d$/.test(a)).sort()).toEqual(['Alt+0', 'Alt+1', 'Alt+2', 'Alt+3', 'Alt+4'])
  })

  it('a combination that someone else owns is left alone and not released by us; a rejected one costs nothing', () => {
    const api = fakeApi(['Alt+2'], ['Alt+3'])
    const k = createKeys(api, handlers())
    k.set({ answers: 3, dismiss: true })
    expect(k.registered().sort()).toEqual(['Alt+0', 'Alt+1', 'Alt+Escape'])
    k.off()
    expect(api.log.filter((l) => l === '-Alt+2')).toEqual([])
    expect(api.isRegistered('Alt+2')).toBe(true)
  })
})

describe('what the panel page may ask for', () => {
  it('accepts the eight actions and nothing else', () => {
    for (const a of [{ type: 'answer', id: 'cliff_a' }, { type: 'other' }, { type: 'dismiss' }, { type: 'why', open: true }, { type: 'show_me' }, { type: 'know_this' }, { type: 'offer', yes: false }, { type: 'touch' }]) {
      expect(CueCardActionSchema.safeParse(a).success, JSON.stringify(a)).toBe(true)
    }
    for (const bad of [{ type: 'answer' }, { type: 'answer', id: '<x>' }, { type: 'answer', id: 'a', extra: 1 }, { type: 'kill' }, { type: 'why', open: 'yes' }, 'dismiss', null, { type: 'offer' }]) {
      expect(CueCardActionSchema.safeParse(bad).success, JSON.stringify(bad)).toBe(false)
    }
  })
  it('sizes are whole numbers in a sane range', () => {
    expect(CueSizeSchema.safeParse({ w: 292, h: 202 }).success).toBe(true)
    for (const bad of [{ w: 0, h: 10 }, { w: 5000, h: 10 }, { w: 1.5, h: 10 }, { w: 10 }, { w: Number.NaN, h: 1 }]) expect(CueSizeSchema.safeParse(bad).success).toBe(false)
  })
})
