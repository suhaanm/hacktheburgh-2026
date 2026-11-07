// The corner pill, presentational. One short sentence from a closed list, the brand mark (a disc and an offset ring) as the only decoration, and at most
// two things to press: the label (opens Knack) and, while something works, Stop. Everything else lets clicks through to the app underneath.
import type { ReactElement } from 'react'
import { APP_NAME } from '../../shared/brand'
import type { PillActionDto, PillViewDto } from '../../shared/knack'

export interface PillViewProps {
  view: PillViewDto
  onAction(a: PillActionDto): void
  /** The pointer entered (true) or left (false) a part that takes clicks. */
  onInteractive(on: boolean): void
}

/** The label's accessible name: what it says, and what pressing it does. */
export const labelName = (text: string): string => `${text}. Open ${APP_NAME}.`

export function PillView({ view, onAction, onInteractive }: PillViewProps): ReactElement | null {
  if (view.kind === 'idle') return null
  return (
    <div className="pill" data-kind={view.kind} data-pill role="status" aria-live={view.kind === 'error' || view.kind === 'needs-you' ? 'assertive' : 'polite'}>
      <span className="mark" aria-hidden="true">
        <span className="ring" />
        <span className="disc" />
      </span>
      {view.open ? (
        <button type="button" className="label" aria-label={labelName(view.text)} onClick={() => onAction({ type: 'open' })} onMouseEnter={() => onInteractive(true)} onMouseLeave={() => onInteractive(false)}>
          {view.text}
        </button>
      ) : (
        <span className="label">{view.text}</span>
      )}
      {view.stop ? (
        <button type="button" className="stop" aria-label={`Stop everything. This is the kill switch.`} onClick={() => onAction({ type: 'stop' })} onMouseEnter={() => onInteractive(true)} onMouseLeave={() => onInteractive(false)}>
          <span className="square" aria-hidden="true" />
          Stop
        </button>
      ) : null}
    </div>
  )
}
