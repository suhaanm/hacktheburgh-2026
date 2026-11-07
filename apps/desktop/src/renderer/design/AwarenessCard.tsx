import { useEffect, useState, type ReactElement } from 'react'
import type { AwarenessCardState, AwarenessChoice } from '../../shared/awareness'
import { Switch } from './Switch'

export interface AwarenessCardProps {
  state: AwarenessCardState
  busy?: boolean
  onChoose: (choice: AwarenessChoice) => void
}

/**
 * The one place the worker agrees to Understudy looking at the screen. One short paragraph first; the full text one tap away (it is the
 * text that is recorded, so it is shown in full before "Allow"). Everything starts off. Withdrawing is one button and always works.
 */
export function AwarenessCard({ state, busy, onChoose }: AwarenessCardProps): ReactElement | null {
  const [periodic, setPeriodic] = useState(state.periodic)
  const [strict, setStrict] = useState(state.strict)
  useEffect(() => {
    setPeriodic(state.periodic)
    setStrict(state.strict)
  }, [state.periodic, state.strict])
  if (!state.available) return null
  const on = state.agreed && state.trigger
  return (
    <section className="al-group al-consent" aria-label="Looking at your screen">
      <h3 className="al-eyebrow">Looking at your screen</h3>
      <p className="al-consent__lead">{state.consentShort}</p>
      <details className="al-consent__more">
        <summary>What exactly happens</summary>
        <p className="al-small">{state.consentText}</p>
      </details>
      <Switch label="Look now and then" hint={`About every ${state.intervalSec} seconds while you are working on a task`} checked={periodic} onChange={setPeriodic} />
      <Switch label="Skip messages and mail apps" hint="Recommended" checked={strict} onChange={setStrict} />
      <div className="al-setrow al-consent__actions">
        <button type="button" className="al-btn al-btn--primary" disabled={busy} onClick={() => onChoose({ trigger: true, periodic, strict })}>
          {on ? 'Save' : 'Allow'}
        </button>
        {on ? (
          <button type="button" className="al-btn al-btn--quiet" disabled={busy} onClick={() => onChoose({ trigger: false })}>
            Turn off
          </button>
        ) : null}
      </div>
      <p className="al-small" role="status">
        {on ? `On. ${state.callsToday === 0 ? 'No looks yet today.' : `${state.callsToday} ${state.callsToday === 1 ? 'look' : 'looks'} today.`}` : 'Off. Nothing is looked at.'}
      </p>
    </section>
  )
}
