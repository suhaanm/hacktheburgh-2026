// "Files I can look at": off by default, one switch plus a list of folders the person chose in a native dialog.
// Read-only and local: the index lives on this computer, and "Forget my files" deletes it.
import { useCallback, useEffect, useState, type ReactElement } from 'react'
import type { FilesStatus } from '../../../shared/files'
import { Switch } from '../../design'
import { describeStatus } from './describe'

export interface FilesSectionProps {
  enabled: boolean
  onEnabled: (enabled: boolean) => void
}

export function FilesSection({ enabled, onEnabled }: FilesSectionProps): ReactElement {
  const [status, setStatus] = useState<FilesStatus | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const api = window.alongside.files

  useEffect(() => {
    let alive = true
    void api.status().then((s) => alive && setStatus(s))
    const off = api.onStatus((s) => alive && setStatus(s))
    return () => {
      alive = false
      off()
    }
  }, [api])

  const add = useCallback(async () => {
    setBusy(true)
    setMessage('')
    try {
      const r = await api.addFolder()
      if (!r.ok && !r.canceled) setMessage(r.error ?? 'I could not add that folder.')
      setStatus(await api.status())
    } finally {
      setBusy(false)
    }
  }, [api])

  const folders = status?.folders ?? []
  return (
    <div className="al-setrow al-files" aria-label="Files I can look at">
      <Switch label="Let me look at some of your files" hint="Off until you turn it on. I only read the folders you choose, I never change anything, and my notes stay on this computer." checked={enabled} onChange={onEnabled} />
      {enabled ? (
        <>
          {folders.length > 0 ? (
            <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)' }}>
              {folders.map((f) => (
                <li key={f.path} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 'var(--sp-2)' }}>
                  <span title={f.path}>
                    {f.name} <span className="al-small">({f.fileCount})</span>
                  </span>
                  <button type="button" className="al-btn al-btn--quiet" aria-label={`Stop looking at ${f.name}`} onClick={() => void api.removeFolder(f.path).then(setStatus)}>
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--sp-2)' }}>
            <button type="button" className="al-btn" disabled={busy} onClick={() => void add()}>
              Add a folder
            </button>
            {folders.length > 0 ? (
              <button type="button" className="al-btn al-btn--quiet" disabled={status?.indexing} onClick={() => void api.reindex().then(setStatus)}>
                Refresh
              </button>
            ) : null}
            {status && (status.indexedFiles > 0 || folders.length > 0) ? (
              <button type="button" className="al-btn al-btn--quiet" onClick={() => void api.deleteIndex().then(setStatus)}>
                Forget my files
              </button>
            ) : null}
          </div>
          <span className="al-small" role="status" aria-live="polite">
            {message || (status ? describeStatus(status) : '')}
          </span>
        </>
      ) : null}
    </div>
  )
}
