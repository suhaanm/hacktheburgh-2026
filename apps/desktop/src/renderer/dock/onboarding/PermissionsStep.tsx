import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactElement } from 'react'
import { Icon } from '../../design'
import { describeRow, getPermissionsApi, screenNeedsRestart, startMicMeter, type MicMeter, type PermKind, type PermState, type PermissionStatus, type PermissionsApi, type RowView } from './permissions'

const KINDS: readonly PermKind[] = ['microphone', 'screen', 'accessibility']
const METER_SECONDS = 8

export interface PermissionsStepProps {
  /** Injected in tests and the gallery; defaults to window.alongside.permissions. */
  api?: PermissionsApi
}

function MicTest(): ReactElement {
  const [level, setLevel] = useState(0)
  const [on, setOn] = useState(false)
  const [error, setError] = useState(false)
  const meter = useRef<MicMeter | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  const stop = useCallback(() => {
    clearTimeout(timer.current)
    meter.current?.stop()
    meter.current = null
    setOn(false)
    setLevel(0)
  }, [])
  useEffect(() => stop, [stop])

  const start = async (): Promise<void> => {
    setError(false)
    try {
      meter.current = await startMicMeter(setLevel)
      setOn(true)
      timer.current = setTimeout(stop, METER_SECONDS * 1000)
    } catch {
      setError(true)
    }
  }

  return (
    <div className="ob-test">
      <button type="button" className="al-btn" onClick={() => (on ? stop() : void start())}>
        {on ? 'Stop the test' : 'Test it'}
      </button>
      <div className="ob-meter" role="meter" aria-label="Microphone level" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(level * 100)} style={{ '--lvl': level } as CSSProperties}>
        <span />
      </div>
      <p className="ob-hint" role="status">
        {error ? 'I could not open the microphone.' : on ? 'Say something. The bar should move.' : 'Nothing is recorded.'}
      </p>
    </div>
  )
}

export function PermissionsStep({ api: injected }: PermissionsStepProps): ReactElement {
  const api = useMemo(() => injected ?? getPermissionsApi(), [injected])
  const [status, setStatus] = useState<PermissionStatus | null>(null)
  const [busy, setBusy] = useState<PermKind | null>(null)
  const screenAtStart = useRef<PermState | null>(null)
  const alive = useRef(true)

  const refresh = useCallback(async (): Promise<void> => {
    try {
      const next = await api.status()
      if (!alive.current) return
      if (screenAtStart.current === null) screenAtStart.current = next.screen
      setStatus(next)
    } catch {
      // Status is a nicety: the rows still offer their actions.
    }
  }, [api])

  useEffect(() => {
    alive.current = true
    void refresh()
    const off = api.onChange((next) => alive.current && setStatus(next))
    return () => {
      alive.current = false
      off()
    }
  }, [api, refresh])

  const act = async (row: RowView): Promise<void> => {
    setBusy(row.kind)
    try {
      if (row.action === 'restart') api.relaunch()
      else if (row.action === 'open') api.openSettings(row.kind)
      else if (row.kind === 'microphone') await api.requestMicrophone()
      else if (row.kind === 'screen') setStatus(await api.requestScreen())
      else await Promise.resolve(api.requestAccessibility())
    } finally {
      setBusy(null)
      void refresh()
    }
  }

  const restart = screenNeedsRestart(screenAtStart.current, status)
  const rows = KINDS.map((kind) => describeRow(kind, status, { restart }))

  return (
    <div className="ob-perms">
      {restart ? (
        <p className="al-note ob-restart" role="status">
          macOS needs me to restart before I can see your screen. Your answers so far are kept.
        </p>
      ) : null}
      {rows.map((row) => (
        <section key={row.kind} className="ob-perm" data-granted={row.granted ? 'true' : 'false'} aria-labelledby={`ob-perm-${row.kind}`}>
          <div className="ob-perm__head">
            <h3 className="ob-perm__title" id={`ob-perm-${row.kind}`}>
              {row.title}
              {row.optional ? <span className="ob-perm__opt"> (optional)</span> : null}
            </h3>
            <span className="ob-status" data-ok={row.granted ? 'true' : 'false'} role="status">
              {row.granted ? <Icon name="check" /> : null}
              <span>{row.chip}</span>
            </span>
          </div>
          <p className="ob-perm__line">{row.line}</p>
          {row.action !== 'none' ? (
            <button type="button" className={`al-btn al-btn--block${row.optional ? '' : ' al-btn--primary'}`} disabled={busy === row.kind} onClick={() => void act(row)}>
              {row.actionLabel}
            </button>
          ) : null}
          {row.kind === 'microphone' && row.granted ? <MicTest /> : null}
        </section>
      ))}

      {status?.hint ? <p className="ob-hint ob-perms__hint">{status.hint}</p> : null}
      <button type="button" className="al-btn al-btn--quiet ob-perms__again" onClick={() => void refresh()}>
        Check again
      </button>
      <p className="ob-hint">You can carry on without any of these. I will ask again when it matters.</p>
    </div>
  )
}
