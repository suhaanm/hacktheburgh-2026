import type { ReactElement } from 'react'
import type { CompanionState } from '../../shared/protocol'
import { sessionActive, useScreenBlocked, useShowtimeActive } from './hooks'
import { LevelChip, PresenceOrb, StopButton, listeningLightState } from '../design'

export interface PillProps {
  state: CompanionState
  personaName: string
  onExpand: () => void
  onStop: () => void
}

const WORDS: Record<CompanionState['phase'], string> = {
  asleep: 'Resting',
  listening_for_name: 'Ready',
  connecting: 'Starting',
  live: 'Listening',
  speaking: 'Speaking',
  thinking: 'Thinking',
  error: 'Tap for details',
}

/** One short word for the pill. Honest about the mic and about Screen Recording. */
export function pillWord(phase: CompanionState['phase'], muted: boolean, screenBlocked: boolean): string {
  if (muted) return 'Muted'
  if (screenBlocked && sessionActive(phase)) return 'Screen access needed'
  return WORDS[phase]
}

/** Collapsed dock: the orb, one state word, four quiet dots for the help level, and Stop only while something is running. */
export function Pill({ state, personaName, onExpand, onStop }: PillProps): ReactElement {
  const screenBlocked = useScreenBlocked()
  const demoActive = useShowtimeActive()
  const stoppable = sessionActive(state.phase) || demoActive
  const light = state.settings.listeningLight ? listeningLightState(state.phase, state.micMuted, screenBlocked) : undefined
  return (
    <div className="al-pill al-drag" role="region" aria-label={`${personaName}, collapsed`}>
      <button type="button" className="al-pill__main" aria-label={`Open the ${personaName} panel`} onClick={onExpand}>
        <PresenceOrb phase={state.phase} size={36} personaName={personaName} light={light} />
        <span className="al-pill__who">
          <span className="al-pill__phase">{pillWord(state.phase, state.micMuted, screenBlocked)}</span>
        </span>
        {state.phase === 'error' ? null : <LevelChip level={state.level} locked={state.levelLocked} variant="dots" />}
      </button>
      {stoppable ? <StopButton compact onStop={onStop} /> : null}
    </div>
  )
}
