// The global keys that answer or dismiss a cue without taking focus from the app below. Registered only while a cue is on screen and given
// back the moment it goes: Alt+1..4 answer option 1..4, Alt+0 is "something else", Alt+Escape dismisses. A combination another part of the app
// (or another app) already owns is left alone, and a registration that fails costs nothing: the card still works by click, and times out.
import { CUE_TOKENS } from './tokens'

export interface ShortcutApi {
  register(accelerator: string, callback: () => void): boolean
  unregister(accelerator: string): void
  isRegistered(accelerator: string): boolean
}

export interface KeyHandlers {
  /** 1-based option number. */
  answer(n: number): void
  other(): void
  dismiss(): void
}

export interface CueKeys {
  /** The keys needed now. Anything registered before is released first; asking for the same again is cheap. */
  set(o: { answers: number; dismiss: boolean }): void
  off(): void
  registered(): string[]
}

export function createKeys(api: ShortcutApi, h: KeyHandlers, log: (scope: string, ...args: unknown[]) => void = () => undefined): CueKeys {
  let mine: string[] = []
  const off = (): void => {
    for (const a of mine) {
      try {
        api.unregister(a)
      } catch {
        // already gone
      }
    }
    mine = []
  }
  return {
    set({ answers, dismiss }) {
      off()
      const wanted: Array<[string, () => void]> = []
      const n = Math.min(Math.max(0, answers), CUE_TOKENS.keys.answer.length)
      for (let i = 0; i < n; i++) wanted.push([CUE_TOKENS.keys.answer[i], () => h.answer(i + 1)])
      if (n > 0) wanted.push([CUE_TOKENS.keys.other, () => h.other()])
      if (dismiss) wanted.push([CUE_TOKENS.keys.dismiss, () => h.dismiss()])
      for (const [accelerator, cb] of wanted) {
        try {
          // Something else owns it already: not ours to take, not ours to release.
          if (api.isRegistered(accelerator)) continue
          if (api.register(accelerator, cb)) mine.push(accelerator)
        } catch (err) {
          log('cue', `key ${accelerator} rejected: ${err instanceof Error ? err.message : 'error'}`)
        }
      }
    },
    off,
    registered: () => [...mine],
  }
}
