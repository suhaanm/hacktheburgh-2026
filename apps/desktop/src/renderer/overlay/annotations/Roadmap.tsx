// The Showtime roadmap: a quiet strip at the top-left (chapter dots, the current chapter and its one-line caption)
// and the discreet "Scripted walkthrough" badge at the top-right. A picture only: the overlay is click-through, the
// presenter controls live in the dock.
import { useEffect, useState, type CSSProperties, type ReactElement } from 'react'
import { IDLE_SHOWTIME_STATE, type ShowtimeApi, type ShowtimeState } from '../../../shared/showtime'
import { EMPTY_ROADMAP, roadmapModel } from './roadmap-model'

const card: CSSProperties = {
  position: 'fixed',
  top: 14,
  left: 16,
  width: 360,
  padding: '10px 14px 12px',
  borderRadius: 14,
  background: 'rgba(10, 14, 24, 0.88)',
  color: '#fff',
  fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif',
  boxShadow: '0 8px 28px rgba(5, 7, 13, 0.4)',
  pointerEvents: 'none',
  zIndex: 5,
}
const badgeStyle: CSSProperties = {
  position: 'fixed',
  top: 14,
  right: 16,
  padding: '5px 12px',
  borderRadius: 999,
  background: 'rgba(10, 14, 24, 0.78)',
  color: 'rgba(255,255,255,0.92)',
  fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif',
  fontSize: 13,
  fontWeight: 600,
  letterSpacing: 0.2,
  pointerEvents: 'none',
  zIndex: 5,
}

const dotColor = (status: string): string =>
  status === 'current' ? '#fff' : status === 'done' ? 'rgba(255,255,255,0.6)' : status === 'unavailable' ? 'rgba(255,255,255,0.12)' : 'rgba(255,255,255,0.28)'

export function Roadmap({ reducedMotion = false }: { reducedMotion?: boolean }): ReactElement | null {
  const [s, setS] = useState<ShowtimeState>(IDLE_SHOWTIME_STATE)
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const api = (window.alongside as unknown as { showtime?: ShowtimeApi }).showtime
    if (!api) return
    void api.state().then(setS)
    return api.onState(setS)
  }, [])
  useEffect(() => {
    if (!s.running || s.paused) return
    const t = setInterval(() => setNow(Date.now()), 250)
    return () => clearInterval(t)
  }, [s.running, s.paused])

  const m = s.running ? roadmapModel(s, now) : EMPTY_ROADMAP
  if (!m.visible) return null
  return (
    <>
      <div style={card} role="status" aria-label="Walkthrough progress">
        <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 8 }} aria-hidden>
          {m.items.map((it) => (
            <span key={it.id} title={it.title} style={{ width: it.status === 'current' ? 22 : 10, height: 10, borderRadius: 5, background: dotColor(it.status), transition: reducedMotion ? 'none' : 'width 200ms, background 200ms' }} />
          ))}
        </div>
        {m.current ? (
          <>
            <div style={{ fontSize: 15, fontWeight: 700 }}>
              {m.current.n}. {m.current.title}
              {m.paused ? ' (paused)' : ''}
            </div>
            <div style={{ fontSize: 13, lineHeight: 1.35, color: 'rgba(255,255,255,0.8)', marginTop: 3 }}>{m.current.caption}</div>
          </>
        ) : null}
        <div style={{ height: 3, borderRadius: 2, background: 'rgba(255,255,255,0.18)', marginTop: 9, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${Math.round(m.progress * 100)}%`, background: '#fff', transition: reducedMotion ? 'none' : 'width 250ms linear' }} />
        </div>
      </div>
      {m.badge ? <div style={badgeStyle}>{m.badge}</div> : null}
    </>
  )
}
