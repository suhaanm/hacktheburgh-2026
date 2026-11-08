// Keep the Mac awake while an agent run is active, and only then (owner request of 8 Nov 2026, "keep-awake while an agent run is active"). A run that is minimised behind the
// worker's other windows still needs the machine to stay up; one that drives the real screen also needs the display on. The blocker is taken when the run starts and given back when
// it ends, when the setting is switched off, and when the app quits: nothing is held between runs. Pure around a small port (Electron's powerSaveBlocker in the app).
export type BlockerType = 'prevent-app-suspension' | 'prevent-display-sleep'

export interface BlockerPort {
  start(type: BlockerType): number
  stop(id: number): void
  isStarted(id: number): boolean
}

export interface KeepAwakeInput {
  /** An agent run is working now (the shell machine's activity is `working`). */
  working: boolean
  /** The run uses the real screen (it clicks and types there), so the display must stay on too. */
  realScreen: boolean
  /** The worker's setting "Keep the Mac awake while Knack works". */
  enabled: boolean
}

/** What to hold for this state: nothing, the app alone, or the display as well. */
export function desiredBlocker(i: KeepAwakeInput): BlockerType | null {
  if (!i.enabled || !i.working) return null
  return i.realScreen ? 'prevent-display-sleep' : 'prevent-app-suspension'
}

export interface KeepAwake {
  update(i: KeepAwakeInput): void
  /** What is held right now. */
  held(): BlockerType | null
  dispose(): void
}

export function createKeepAwake(port: BlockerPort, log: (...a: unknown[]) => void = () => undefined): KeepAwake {
  let current: { type: BlockerType; id: number } | null = null
  const release = (): void => {
    if (!current) return
    const { id, type } = current
    current = null
    try {
      if (port.isStarted(id)) port.stop(id)
    } catch {
      /* already gone */
    }
    log('keep-awake', `released ${type}`)
  }
  return {
    update(i) {
      const want = desiredBlocker(i)
      if (want === (current?.type ?? null)) return
      release()
      if (want === null) return
      try {
        current = { type: want, id: port.start(want) }
        log('keep-awake', `holding ${want}`)
      } catch (err) {
        current = null // a blocker that cannot be taken is not worth stopping a run for
        log('keep-awake', `could not hold ${want}: ${err instanceof Error ? err.message : String(err)}`)
      }
    },
    held: () => current?.type ?? null,
    dispose: release,
  }
}
