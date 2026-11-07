import { EventEmitter } from 'node:events'
import type { AgentChip, LessonStepEvent, LevelChangedEvent, PersonaId, SessionEndReason, SessionRequest, SessionSource } from '../shared/protocol'

export interface BusEvents {
  wake: { personaId: PersonaId; source: SessionSource }
  'session:request': SessionRequest
  'session:ended': { reason: SessionEndReason }
  'tool:called': { name: string; args: unknown; ms: number; ok: boolean }
  'screen:changed': { score: number }
  'lesson:step': LessonStepEvent
  'level:changed': LevelChangedEvent
  'agent:update': { chip: AgentChip }
  // DEMO owns the handler; SHELL (tray) emits it.
  'showtime:request': { source: 'tray' | 'dock' | 'hotkey' | 'cli'; full?: boolean; stop?: boolean }
}

export type BusEventName = keyof BusEvents

export class Bus {
  private readonly emitter = new EventEmitter()

  constructor() {
    this.emitter.setMaxListeners(50)
  }

  on<K extends BusEventName>(event: K, listener: (payload: BusEvents[K]) => void): () => void {
    this.emitter.on(event, listener)
    return () => this.emitter.off(event, listener)
  }

  once<K extends BusEventName>(event: K, listener: (payload: BusEvents[K]) => void): void {
    this.emitter.once(event, listener)
  }

  emit<K extends BusEventName>(event: K, payload: BusEvents[K]): void {
    for (const listener of this.emitter.listeners(event) as ((p: BusEvents[K]) => void)[]) {
      try {
        listener(payload)
      } catch (err) {
        console.error(`[bus] listener for ${event} threw:`, err)
      }
    }
  }
}
