import { useCallback, useEffect, useState, type ReactElement } from 'react'
import type { AwarenessCardState, AwarenessChoice } from '../../shared/awareness'
import { AwarenessCard } from '../design'

// The card, hosted in the dock: state and the one write come from main through window.alongside.awareness.
export function AwarenessSection(): ReactElement | null {
  const api = (window.alongside as { awareness?: { state(): Promise<AwarenessCardState>; setConsent(c: AwarenessChoice): Promise<AwarenessCardState> } }).awareness
  const [state, setState] = useState<AwarenessCardState | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (!api) return
    let alive = true
    void api.state().then((s) => alive && setState(s)).catch(() => undefined)
    return () => {
      alive = false
    }
  }, [api])
  const choose = useCallback(
    (choice: AwarenessChoice) => {
      if (!api) return
      setBusy(true)
      void api
        .setConsent(choice)
        .then(setState)
        .catch(() => undefined)
        .finally(() => setBusy(false))
    },
    [api],
  )
  return state ? <AwarenessCard state={state} busy={busy} onChoose={choose} /> : null
}
