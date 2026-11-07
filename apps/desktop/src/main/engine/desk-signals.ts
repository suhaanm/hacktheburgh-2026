// Desk signals for the presence model (CAP-5): lock, unlock, sleep, resume and idle spells, from Electron's powerMonitor.
// API names verified against the installed typings (Electron 45): events 'lock-screen', 'unlock-screen', 'suspend', 'resume';
// powerMonitor.getSystemIdleTime() returns seconds (synchronous). Only times and counts leave this module: no window titles,
// no app names, no input content.
//   idle    meta { state: 'start' | 'end', idle_s }   start fires once when idle time first passes the threshold; end fires
//                                                      when input returns, with the length of the spell in seconds.
//   lock / unlock / sleep / resume                     no meta
import type { EventInput } from './event'

export interface PowerMonitorLike {
  on(event: 'lock-screen' | 'unlock-screen' | 'suspend' | 'resume', listener: () => void): unknown
  removeListener(event: 'lock-screen' | 'unlock-screen' | 'suspend' | 'resume', listener: () => void): unknown
  getSystemIdleTime(): number
}

export interface DeskSignalOptions {
  powerMonitor: PowerMonitorLike
  emit: (input: EventInput) => unknown
  // Idle time at or above this starts an idle spell. 60 s matches the presence model's smallest meaningful gap.
  idleThresholdS?: number
  pollMs?: number
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (handle: unknown) => void
}

export interface DeskSignals {
  state(): { locked: boolean; asleep: boolean; idleSeconds: number; inIdleSpell: boolean }
  // Run one idle check now (the interval calls this; tests call it directly).
  poll(): void
  dispose(): void
}

export function installDeskSignals(opts: DeskSignalOptions): DeskSignals {
  const pm = opts.powerMonitor
  const threshold = opts.idleThresholdS ?? 60
  const pollMs = opts.pollMs ?? 5000
  const setT = opts.setTimer ?? ((fn, ms) => setInterval(fn, ms))
  const clearT = opts.clearTimer ?? ((h) => clearInterval(h as ReturnType<typeof setInterval>))

  let locked = false
  let asleep = false
  let inSpell = false
  let lastIdle = 0

  const emit = (type: EventInput['type'], meta?: EventInput['meta']): void => {
    opts.emit({ source: 'desk', type, actor: 'human', ...(meta ? { meta } : {}) })
  }

  const endSpell = (idleS: number): void => {
    if (!inSpell) return
    inSpell = false
    emit('idle', { state: 'end', idle_s: Math.max(0, Math.round(idleS)) })
  }

  const poll = (): void => {
    if (locked || asleep) return // the lock and sleep events already say it; an idle spell on top would double count the absence
    let idle = 0
    try {
      idle = pm.getSystemIdleTime()
    } catch {
      return
    }
    if (!Number.isFinite(idle) || idle < 0) return
    if (!inSpell && idle >= threshold) {
      inSpell = true
      emit('idle', { state: 'start', idle_s: Math.round(idle) })
    } else if (inSpell && idle < lastIdle) {
      // Idle time went down: input came back. The spell lasted about the last idle reading.
      endSpell(lastIdle)
    }
    lastIdle = idle
  }

  const onLock = (): void => {
    if (locked) return
    endSpell(lastIdle)
    locked = true
    emit('lock')
  }
  const onUnlock = (): void => {
    if (!locked) return
    locked = false
    lastIdle = 0
    emit('unlock')
  }
  const onSuspend = (): void => {
    if (asleep) return
    endSpell(lastIdle)
    asleep = true
    emit('sleep')
  }
  const onResume = (): void => {
    if (!asleep) return
    asleep = false
    lastIdle = 0
    emit('resume')
  }

  pm.on('lock-screen', onLock)
  pm.on('unlock-screen', onUnlock)
  pm.on('suspend', onSuspend)
  pm.on('resume', onResume)
  const handle = setT(poll, pollMs)

  return {
    state: () => ({ locked, asleep, idleSeconds: lastIdle, inIdleSpell: inSpell }),
    poll,
    dispose() {
      clearT(handle)
      pm.removeListener('lock-screen', onLock)
      pm.removeListener('unlock-screen', onUnlock)
      pm.removeListener('suspend', onSuspend)
      pm.removeListener('resume', onResume)
    },
  }
}
