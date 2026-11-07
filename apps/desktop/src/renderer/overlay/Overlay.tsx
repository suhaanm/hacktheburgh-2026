// The overlay window's renderer: listens for OverlayCommands over IPC and draws them with <OverlayScene>.
// Everything here is a picture; the window is click-through and has no controls.
import { useCallback, useEffect, useMemo, useRef, useState, type ReactElement } from 'react'
import { PERSONAS } from '../../shared/personas'
import type { OverlayCommand } from '../../shared/protocol'
import { DEFAULT_SETTINGS, type Settings } from '../../shared/settings'
import { annotationStyle } from '../design/annotation-style'
import { Roadmap } from './annotations/Roadmap'
import { OverlayScene } from './OverlayScene'
import { advance, EMPTY_OVERLAY_STATE, nextDeadline, reduceOverlay, type OverlayState } from './store'

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  useEffect(() => {
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
    const on = (): void => setReduced(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  return reduced
}

export function Overlay(): ReactElement {
  const [viewport, setViewport] = useState({ width: window.innerWidth, height: window.innerHeight })
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS)
  const [state, setState] = useState<OverlayState>(EMPTY_OVERLAY_STATE)
  const reducedMotion = useReducedMotion()
  const style = useMemo(
    () => annotationStyle({ bigAnnotations: settings.bigAnnotations, highContrast: settings.highContrast, dyslexiaFont: settings.dyslexiaFont }, { reducedMotion }),
    [settings.bigAnnotations, settings.highContrast, settings.dyslexiaFont, reducedMotion],
  )
  const live = useRef({ viewport, style })
  live.current = { viewport, style }

  useEffect(() => {
    const onResize = (): void => {
      const size = { width: window.innerWidth, height: window.innerHeight }
      setViewport(size)
      window.alongside.overlayReady(size)
    }
    window.addEventListener('resize', onResize)
    const offState = window.alongside.onState((s) => setSettings(s.settings))
    void window.alongside.getState().then((s) => setSettings(s.settings))
    const offCmd = window.alongside.onOverlayCommand((cmd: OverlayCommand) =>
      setState((prev) => reduceOverlay(prev, cmd, { now: Date.now(), ...live.current })),
    )
    window.alongside.overlayReady({ width: window.innerWidth, height: window.innerHeight })
    return () => {
      window.removeEventListener('resize', onResize)
      offState()
      offCmd()
    }
  }, [])

  const tick = useCallback(() => setState((prev) => advance(prev, { now: Date.now(), ...live.current })), [])
  useEffect(() => {
    const deadline = nextDeadline(state, style.transition.exitMs)
    if (deadline === null) return
    const timer = setTimeout(tick, Math.max(0, deadline - Date.now()) + 5)
    return () => clearTimeout(timer)
  }, [state, style.transition.exitMs, tick])

  const persona = settings.persona ? PERSONAS[settings.persona] : null
  return (
    <>
      <OverlayScene
        state={state}
        viewport={viewport}
        style={style}
        captionsEnabled={settings.captions}
        speakerNames={{ user: 'You', assistant: persona?.displayName ?? 'Assistant' }}
      />
      <Roadmap reducedMotion={reducedMotion} />
    </>
  )
}
