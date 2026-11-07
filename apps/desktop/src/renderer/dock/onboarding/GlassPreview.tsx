// A picture of the helper window over a sample app window, so the glass effect and its transparency can be judged
// instantly. Self-contained (own CSS), so it works whichever theme or glass CSS the dock itself has applied.
import type { CSSProperties, ReactElement } from 'react'
import { glassAlphas } from '../../design/apply-settings'

export interface GlassPreviewProps {
  glass: boolean
  /** 0.35..1: how solid the window is. */
  opacity: number
  personaName: string
}

export function glassDescription(glass: boolean, opacity: number): string {
  if (!glass) return 'Solid window'
  if (opacity >= 0.9) return 'Almost solid'
  if (opacity >= 0.7) return 'Slightly see-through'
  if (opacity >= 0.5) return 'See-through'
  return 'Very see-through'
}

export function GlassPreview({ glass, opacity, personaName }: GlassPreviewProps): ReactElement {
  // The real dock keeps its text areas fairly solid (glassAlphas), so the preview shows exactly that.
  const alpha = glassAlphas(opacity).shell
  return (
    <div className="ob-glass" data-glass={glass ? 'on' : 'off'} style={{ '--ob-glass': String(alpha) } as CSSProperties} role="img" aria-label={`Preview: ${personaName}'s window over a sample page. ${glassDescription(glass, opacity)}.`}>
      <div className="ob-glass__wall" aria-hidden="true" />
      <div className="ob-glass__win" aria-hidden="true">
        <span className="ob-glass__bar" />
        <span className="ob-glass__line" style={{ width: '86%' }} />
        <span className="ob-glass__line" style={{ width: '94%' }} />
        <span className="ob-glass__line" style={{ width: '70%' }} />
        <span className="ob-glass__line" style={{ width: '90%' }} />
        <span className="ob-glass__line" style={{ width: '78%' }} />
        <span className="ob-glass__line" style={{ width: '88%' }} />
      </div>
      <div className="ob-glass__dock" aria-hidden="true">
        <span className="ob-glass__orb" />
        <span className="ob-glass__who">
          <strong>{personaName}</strong>
          <span>Here to help</span>
        </span>
        <span className="ob-glass__stop">Stop</span>
      </div>
    </div>
  )
}
