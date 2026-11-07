import { useEffect, useRef, useState, type ReactElement } from 'react'
import type { CompanionState } from '../../shared/protocol'
import { applyDesignSettings } from '../design'
import { ToastCard, countdownRemaining } from './ToastCard'

const ARM_MS = 500

function useToastState(): CompanionState | null {
  const [state, setState] = useState<CompanionState | null>(null)
  useEffect(() => {
    let alive = true
    const off = window.alongside.onState((s) => alive && setState(s))
    void window.alongside
      .getState()
      .then((s) => alive && setState((prev) => prev ?? s))
      .catch(() => undefined) // main pushes the state too
    return () => {
      alive = false
      off()
    }
  }, [])
  return state
}

export function ToastApp(): ReactElement | null {
  const state = useToastState()
  const request = state?.pendingConfirm
  const expiresAt = state?.toastConfirm?.id === request?.id ? (state?.toastConfirm?.expiresAt ?? null) : null
  const [now, setNow] = useState(() => Date.now())
  const [armed, setArmed] = useState(false)
  // The countdown starts when this request first reached the page (main set the same timer a few ms earlier).
  const seen = useRef<{ id: string; at: number } | null>(null)
  if (request && seen.current?.id !== request.id) seen.current = { id: request.id, at: Date.now() }

  useEffect(() => {
    if (state) applyDesignSettings(state.settings, state.persona)
  }, [state?.settings, state?.persona]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setArmed(false)
    const t = setTimeout(() => setArmed(true), ARM_MS)
    return () => clearTimeout(t)
  }, [request?.id])

  useEffect(() => {
    if (expiresAt === null) return
    const t = setInterval(() => setNow(Date.now()), 250)
    return () => clearInterval(t)
  }, [expiresAt])

  if (!request) return null
  const remaining = expiresAt === null || !seen.current ? null : countdownRemaining(seen.current.at, expiresAt, now)
  return <ToastCard request={request} remaining={remaining} armed={armed} onAnswer={(choice) => window.alongside.answerConfirm({ id: request.id, choice })} />
}
