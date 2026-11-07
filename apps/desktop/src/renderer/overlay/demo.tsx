// Headless render harness page: demo.html?fixture=<name>&backdrop=light|dark|stage|<image url>[&big=0|1][&hc=1]
// Renders the real <OverlayScene> over a backdrop. harness/electron-main.cjs screenshots it with capturePage().
import { useEffect, useMemo, useState, type ReactElement } from 'react'
import { createRoot } from 'react-dom/client'
import '../design/fonts'
import { annotationStyle } from '../design/annotation-style'
import { Backdrop } from './backdrop'
import { FIXTURES } from './fixtures'
import { planFlight } from './flight'
import { normToPx } from './geometry'
import { OverlayScene } from './OverlayScene'
import { EMPTY_OVERLAY_STATE, reduceOverlay } from './store'

declare global {
  interface Window {
    __overlayReady?: boolean
    __fixtures?: string[]
  }
}
window.__fixtures = Object.keys(FIXTURES)

// Hidden windows do not advance CSS animations reliably, so stills skip entrances and freeze the pulse echo mid-way.
const STILL_CSS = `
.ov-enter,.ov-fade-enter,.ov-check{animation:none !important}
.ov-pulse{animation-delay:-0.45s !important;animation-play-state:paused !important;animation-iteration-count:1 !important}
`

function Demo(): ReactElement {
  const q = new URLSearchParams(location.search)
  const name = q.get('fixture') ?? 'ring-badge'
  const fixture = FIXTURES[name] ?? FIXTURES['ring-badge']
  const backdrop = q.get('backdrop') ?? 'light'
  const viewport = { width: window.innerWidth, height: window.innerHeight }
  const bigParam = q.get('big')
  const settings = {
    bigAnnotations: bigParam !== null ? bigParam === '1' : fixture.settings?.bigAnnotations ?? true,
    highContrast: q.get('hc') === '1' || fixture.settings?.highContrast === true,
    dyslexiaFont: fixture.settings?.dyslexiaFont === true,
  }
  const reducedMotion = q.get('reduced') === '1'
  const still = q.get('still') !== '0'
  const style = useMemo(() => annotationStyle(settings, { reducedMotion }), [settings.bigAnnotations, settings.highContrast, settings.dyslexiaFont, reducedMotion])
  const [state] = useState(() => fixture.commands.reduce((s, cmd) => reduceOverlay(s, cmd, { now: 0, viewport, style }), EMPTY_OVERLAY_STATE))

  const freeze = useMemo(() => {
    if (fixture.ghost === undefined) return null
    if (typeof fixture.ghost === 'number') return fixture.ghost
    const g = state.annotations.find((a) => a.annotation.kind === 'ghostCursor')?.annotation
    if (!g || g.kind !== 'ghostCursor') return null
    const plan = planFlight(g.path.map((p) => normToPx(p, viewport)), style.ghostCursor.flight, { viewport })
    if (fixture.ghost === 'flight') return plan.segments[0].durationMs * 0.62
    const last = plan.segments[plan.segments.length - 1]
    return plan.totalMs - last.holdMs + 120 + style.ghostCursor.press.durationMs * 0.35
  }, [fixture, state, style, viewport])

  useEffect(() => {
    const t = setTimeout(() => {
      window.__overlayReady = true
    }, 1000)
    return () => clearTimeout(t)
  }, [])

  const bg =
    backdrop === 'light' || backdrop === 'dark' ? (
      <Backdrop mode={backdrop} />
    ) : backdrop === 'stage' ? (
      <iframe src="../../../apps/demo-stage/index.html" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', border: 0 }} />
    ) : (
      <img src={backdrop} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
    )
  return (
    <div style={{ position: 'absolute', inset: 0 }}>
      {bg}
      {still ? <style>{STILL_CSS}</style> : null}
      <OverlayScene
        state={state}
        viewport={viewport}
        style={style}
        captionsEnabled={fixture.settings?.captions !== false}
        speakerNames={{ user: 'You', assistant: 'Marcus' }}
        freezeGhostMs={freeze}
        typeBubbles={!still}
        chipProgress={fixture.chip}
      />
    </div>
  )
}

createRoot(document.getElementById('root') as HTMLElement).render(<Demo />)
