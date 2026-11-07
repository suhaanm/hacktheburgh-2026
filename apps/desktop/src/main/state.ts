import type { AgentChip, CaptionLine, CaptionSpeaker, CompanionState } from '../shared/protocol'
import type { Settings } from '../shared/settings'

type Listener = (state: CompanionState) => void

const MAX_CAPTIONS = 6

export function initialState(settings: Settings): CompanionState {
  return {
    persona: settings.persona,
    phase: 'asleep',
    micMuted: false,
    level: settings.helpLevelMode === 'locked' ? settings.lockedLevel : 2,
    levelLocked: settings.helpLevelMode === 'locked',
    captions: [],
    agents: [],
    settings,
  }
}

export class StateStore {
  private current: CompanionState
  private readonly listeners = new Set<Listener>()
  private captionSeq = 0

  constructor(settings: Settings) {
    this.current = initialState(settings)
  }

  get(): CompanionState {
    return this.current
  }

  // Replaces top-level keys; an explicit undefined removes an optional key (skill, lastError, pendingConfirm).
  patch(partial: Partial<CompanionState>): CompanionState {
    this.current = { ...this.current, ...partial }
    this.emit()
    return this.current
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  // A non-final line from the same speaker is replaced in place so captions do not stutter.
  addCaption(speaker: CaptionSpeaker, text: string, final: boolean): void {
    const captions = [...this.current.captions]
    const last = captions[captions.length - 1]
    if (last && !last.final && last.speaker === speaker) {
      captions[captions.length - 1] = { ...last, text, final, at: Date.now() }
    } else {
      const line: CaptionLine = { id: `cap-${++this.captionSeq}`, speaker, text, final, at: Date.now() }
      captions.push(line)
    }
    this.patch({ captions: captions.slice(-MAX_CAPTIONS) })
  }

  upsertAgent(chip: AgentChip): void {
    const agents = this.current.agents.some((a) => a.id === chip.id)
      ? this.current.agents.map((a) => (a.id === chip.id ? chip : a))
      : [...this.current.agents, chip]
    this.patch({ agents })
  }

  private emit(): void {
    for (const listener of this.listeners) listener(this.current)
  }
}
