import type { CSSProperties, ReactElement } from 'react'
import type { Phase } from '../../shared/protocol'
import { PHASE_LABELS } from './labels'
import type { LightState } from './ListeningLight'

export interface PresenceOrbProps {
  phase: Phase
  /** Pixel size; default 56. */
  size?: number
  /** Persona display name for the accessible name. */
  personaName?: string
  /** When set, a small listening dot sits on the orb (used in the collapsed pill). */
  light?: LightState
}

/** A soft orb, never a face. Breathes while listening, ripples while speaking, dims while thinking. */
export function PresenceOrb({ phase, size = 56, personaName, light }: PresenceOrbProps): ReactElement {
  const orb = (
    <div className="al-orb" data-phase={phase} role="img" aria-label={`${personaName ? `${personaName}: ` : ''}${PHASE_LABELS[phase]}`} style={{ '--orb-size': `${size}px` } as CSSProperties}>
      <span className="al-orb__halo" />
      <span className="al-orb__ring" />
      <span className="al-orb__core">{phase === 'error' ? '!' : null}</span>
    </div>
  )
  if (!light) return orb
  return (
    <span className="al-orbwrap" data-light={light}>
      {orb}
      <span className="al-orbwrap__light" aria-hidden="true" />
    </span>
  )
}
