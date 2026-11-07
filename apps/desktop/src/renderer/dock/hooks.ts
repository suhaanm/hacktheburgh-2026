import { useCallback, useEffect, useState, useSyncExternalStore } from 'react'
import { buildProgress, type ProgressData } from '../../main/teaching/progress'
import type { CompanionState } from '../../shared/protocol'
import type { Settings, SettingsPatch } from '../../shared/settings'

let current: CompanionState | null = null
const subscribers = new Set<() => void>()
let started = false

function publish(next: CompanionState): void {
  current = next
  subscribers.forEach((notify) => notify())
}

function start(): void {
  if (started) return
  started = true
  void window.alongside.getState().then(publish)
  window.alongside.onState(publish)
}

function subscribe(notify: () => void): () => void {
  start()
  subscribers.add(notify)
  return () => subscribers.delete(notify)
}

/** The one shared view of main's CompanionState. null until the first snapshot arrives. */
export function useCompanionState(): CompanionState | null {
  return useSyncExternalStore(subscribe, () => current)
}

/** Settings live inside CompanionState. Patching is optimistic; main's next state:update is the truth. */
export function useSettings(): readonly [Settings | null, (patch: SettingsPatch) => void] {
  const state = useCompanionState()
  const patch = useCallback((p: SettingsPatch) => {
    if (current) publish({ ...current, settings: { ...current.settings, ...p } })
    void window.alongside.patchSettings(p)
  }, [])
  return [state?.settings ?? null, patch] as const
}

/** Loads the learner snapshot while `active` and turns it into display data; refreshes so a finished lesson shows up. */
export function useProgressData(active: boolean, demoMode: boolean): ProgressData | null {
  const [data, setData] = useState<ProgressData | null>(null)
  useEffect(() => {
    if (!active) return
    let alive = true
    const load = (): void => {
      void window.alongside.learnerSnapshot().then((s) => alive && setData(buildProgress(s, { now: Date.now(), demoMode })))
    }
    load()
    const timer = setInterval(load, 4000)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [active, demoMode])
  return data
}

/** True once main says Screen Recording is not allowed (or the capture probe came back empty). false until the first answer. */
export function useScreenBlocked(): boolean {
  const [blocked, setBlocked] = useState(false)
  useEffect(() => {
    const perms = window.alongside.permissions
    if (!perms) return
    let alive = true
    void perms.status().then((s) => alive && setBlocked(s.screen !== 'granted'))
    const off = perms.onChange((s) => setBlocked(s.screen !== 'granted'))
    return () => {
      alive = false
      off()
    }
  }, [])
  return blocked
}

interface ShowtimeLike {
  state(): Promise<{ running: boolean }>
  onState(cb: (s: { running: boolean }) => void): () => void
}

/** True while the Showtime walkthrough is running. */
export function useShowtimeActive(): boolean {
  const [active, setActive] = useState(false)
  useEffect(() => {
    const api = (window.alongside as unknown as { showtime?: ShowtimeLike }).showtime
    if (!api) return
    let alive = true
    void api.state().then((s) => alive && setActive(s.running))
    const off = api.onState((s) => setActive(s.running))
    return () => {
      alive = false
      off()
    }
  }, [])
  return active
}

/** A live session is something Stop can end: connecting, talking, thinking or speaking. */
export function sessionActive(phase: CompanionState['phase']): boolean {
  return phase === 'connecting' || phase === 'live' || phase === 'thinking' || phase === 'speaking'
}
