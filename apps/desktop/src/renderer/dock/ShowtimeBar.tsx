import { useEffect, useState, type CSSProperties, type ReactElement } from 'react'
import { IDLE_SHOWTIME_STATE, type ShowtimeApi, type ShowtimeState } from '../../shared/showtime'

const api = (): ShowtimeApi | undefined => (window.alongside as unknown as { showtime?: ShowtimeApi }).showtime

// Its own strip at the top of the dock (not floating over it), so the persona name and header buttons stay visible.
const bar: CSSProperties = {
  flex: 'none',
  display: 'flex',
  flexWrap: 'wrap',
  alignItems: 'center',
  gap: 6,
  padding: '8px 12px',
  background: 'var(--surface-sunken, #eee7da)',
  color: 'var(--ink, #1c1917)',
  borderBottom: '1px solid var(--line, #d9d0c2)',
  font: '600 14px/1.25 var(--font-ui, system-ui, sans-serif)',
}
const label: CSSProperties = { flex: '1 1 100%', minWidth: 0, overflowWrap: 'anywhere' }
const btn: CSSProperties = {
  font: 'inherit',
  minHeight: 44,
  padding: '0 12px',
  borderRadius: 10,
  border: '1px solid var(--line-strong, #8c8376)',
  background: 'var(--surface-raised, #fff)',
  color: 'inherit',
  cursor: 'pointer',
}

/** Presenter controls while the walkthrough runs: Previous, Pause, Next, Stop. Renders nothing otherwise. */
export function ShowtimeBar(): ReactElement | null {
  const [s, setS] = useState<ShowtimeState>(IDLE_SHOWTIME_STATE)
  useEffect(() => {
    const a = api()
    if (!a) return
    void a.state().then(setS)
    return a.onState(setS)
  }, [])
  const a = api()
  if (!a || (!s.running && !s.handover)) return null
  const chapter = s.chapters[s.chapterIndex]
  return (
    <div style={bar} className="al-drag" role="group" aria-label="Walkthrough controls">
      <span style={label}>{s.handover ? 'Walkthrough finished. Ask me anything.' : `${chapter ? chapter.n : ''} of ${s.chapters.length}  ${chapter?.title ?? ''}`}</span>
      {s.running ? (
        <>
          <button type="button" style={btn} onClick={() => void a.prev()} aria-label="Previous chapter">
            Back
          </button>
          <button type="button" style={btn} onClick={() => void a.pause()}>
            {s.paused ? 'Resume' : 'Pause'}
          </button>
          <button type="button" style={btn} onClick={() => void a.next()} aria-label="Next chapter">
            Next
          </button>
        </>
      ) : null}
      <button type="button" style={btn} onClick={() => void a.stop()}>
        {s.handover ? 'Close' : 'Stop demo'}
      </button>
    </div>
  )
}
