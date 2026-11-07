import { useEffect, useState, type ReactElement } from 'react'

// DEMO adds window.alongside.showtime; typed locally so this compiles whether or not it has landed.
interface ShowtimeApi {
  start(opts?: { full?: boolean }): Promise<void>
  stop(): void | Promise<void>
  state(): Promise<{ running: boolean }>
  onState(cb: (s: { running: boolean }) => void): () => void
}
const showtime = (): ShowtimeApi | undefined => (window.alongside as unknown as { showtime?: ShowtimeApi }).showtime

/** Quiet rows at the end of "More settings": the scripted demo, and the get-to-know-you flow. */
export function MoreExtras({ onSetUpAgain, files }: { onSetUpAgain: () => void; files?: ReactElement }): ReactElement {
  const api = showtime()
  const [running, setRunning] = useState(false)
  useEffect(() => {
    if (!api) return
    void api.state().then((s) => setRunning(s.running))
    return api.onState((s) => setRunning(s.running))
  }, [api])

  return (
    <section className="al-group" aria-label="Other">
      <h3 className="al-eyebrow">Other</h3>
      {files}
      {api ? (
        <div className="al-setrow">
          <button type="button" className="al-btn" onClick={() => (running ? void api.stop() : void api.start({}))}>
            {running ? 'Stop demo' : 'Run demo'}
          </button>
        </div>
      ) : null}
      <div className="al-setrow">
        <button type="button" className="al-btn" onClick={onSetUpAgain}>
          Set up again
        </button>
      </div>
    </section>
  )
}
