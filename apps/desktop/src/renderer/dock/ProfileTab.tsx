import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactElement } from 'react'
import { ConfirmModal, Icon, Switch } from '../design'
import { EDITABLE_KEYS, SECTION_COPY, addLine, blankProfile, cleanNote, parseProfile, removeLines, type ListKey, type ProfileSection } from './profile'

interface Doc {
  content: string
  revision: string
}
type WriteResult = 'ok' | 'conflict' | 'rejected' | 'error'

const DELETE_YES = 'Yes, delete everything'
const DELETE_NO = 'No, keep it'
const STALE = 'This changed while you were looking, so I have loaded the latest. '

export interface ProfileTabProps {
  carerSharing: boolean
  onCarerSharing: (on: boolean) => void
}

/** "What I know about you": the learner's own profile file, readable, editable and deletable. */
export function ProfileTab({ carerSharing, onCarerSharing }: ProfileTabProps): ReactElement {
  const [doc, setDoc] = useState<Doc | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [adds, setAdds] = useState<Partial<Record<ListKey, string>>>({})
  const [forgetting, setForgetting] = useState<number | null>(null)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const [latestOnConflict, setLatestOnConflict] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [adding, setAdding] = useState<ListKey | null>(null)
  const [showMore, setShowMore] = useState(false)

  const docRef = useRef<Doc | null>(null)
  const quiet = useRef(true)
  docRef.current = doc
  quiet.current = !editing && !busy && Object.values(adds).every((v) => !v)

  const read = useCallback(async (): Promise<void> => {
    try {
      const r = await window.alongside.learnerMarkdown({ op: 'read' })
      setDoc({ content: r.content, revision: r.revision })
      setProblem(null)
    } catch {
      setProblem('I could not read your profile just now.')
    }
  }, [])

  useEffect(() => {
    void read()
    const timer = setInterval(() => quiet.current && void read(), 5000)
    const reread = (): void => void read()
    window.addEventListener('alongside:showtime-profile', reread)
    return () => {
      clearInterval(timer)
      window.removeEventListener('alongside:showtime-profile', reread)
    }
  }, [read])

  // Every change is one write with the revision we last read; a stale revision never overwrites anything.
  const write = useCallback(async (content: string, revision?: string): Promise<WriteResult> => {
    const base = revision ?? docRef.current?.revision
    if (base === undefined) return 'error'
    setBusy(true)
    try {
      const r = await window.alongside.learnerMarkdown({ op: 'write', content, revision: base })
      setDoc({ content: r.content, revision: r.revision })
      setProblem(null)
      return r.ok ? 'ok' : r.conflict ? 'conflict' : 'rejected'
    } catch {
      setProblem('I could not save that. Nothing was lost.')
      return 'error'
    } finally {
      setBusy(false)
    }
  }, [])

  const forgetLines = async (indices: number[]): Promise<void> => {
    if (!doc) return
    setForgetting(null)
    const r = await write(removeLines(doc.content, indices))
    setNotice(r === 'ok' ? 'Forgotten.' : r === 'conflict' ? `${STALE}Nothing was removed. Please try again.` : null)
  }

  const submitAdd = async (key: ListKey, e: FormEvent): Promise<void> => {
    e.preventDefault()
    const text = cleanNote(adds[key] ?? '')
    if (!doc || !text) return
    const r = await write(addLine(doc.content, key, text))
    if (r === 'ok') {
      setAdds((a) => ({ ...a, [key]: '' }))
      setAdding(null)
      setNotice('Written down.')
    } else if (r === 'conflict') {
      setNotice(`${STALE}Your words are still in the box. Press Add again.`)
    }
  }

  const saveDraft = async (): Promise<void> => {
    const r = await write(draft)
    if (r === 'ok') {
      setEditing(false)
      setLatestOnConflict(null)
      setNotice('Saved.')
    } else if (r === 'conflict') {
      setLatestOnConflict(docRef.current?.content ?? '')
    } else if (r === 'rejected') {
      setNotice('That file is too large to save. Your text is still here.')
    }
  }

  const deleteAll = async (choice: string): Promise<void> => {
    setConfirmDelete(false)
    if (choice !== DELETE_YES) return
    let r = await write(blankProfile())
    if (r === 'conflict') r = await write(blankProfile(), docRef.current?.revision)
    setNotice(r === 'ok' ? 'Everything is deleted. I start again from nothing.' : 'I could not delete it. Please try again.')
  }

  if (!doc) return <p className="al-muted">{problem ?? 'Loading what I have written down.'}</p>

  const sections = parseProfile(doc.content)
  const byKey = (key: ListKey): ProfileSection[] => sections.filter((s) => s.key === key)
  const others = sections.filter((s) => s.key === 'other' && s.lines.length > 0)
  const last = sections.find((s) => s.key === 'lastSession')?.lines[0]
  const sharingLines = byKey('sharing').flatMap((s) => s.lines)

  const Lines = ({ section }: { section: ProfileSection }): ReactElement => (
    <>
      {section.lines.length === 0 ? (
        <p className="al-small">Nothing written down yet.</p>
      ) : (
        <ul className="al-lines">
          {section.lines.map((l) => (
            <li key={l.index} className="al-line">
              <span className="al-line__text">{l.text}</span>
              <button type="button" className="al-btn al-btn--quiet al-line__forget" aria-label={`Forget: ${l.text}`} disabled={busy} onClick={() => void forgetLines([l.index])}>
                Forget
              </button>
            </li>
          ))}
        </ul>
      )}
      {section.lines.length > 1 ? (
        forgetting === section.headingIndex ? (
          <div className="al-forgetrow" role="group" aria-label="Forget all of these?">
            <span>Forget all {section.lines.length}?</span>
            <button type="button" className="al-btn" disabled={busy} onClick={() => void forgetLines(section.lines.map((l) => l.index))}>
              Yes, forget them
            </button>
            <button type="button" className="al-btn al-btn--quiet" onClick={() => setForgetting(null)}>
              Keep them
            </button>
          </div>
        ) : (
          <button type="button" className="al-btn al-btn--quiet al-forgetall" onClick={() => setForgetting(section.headingIndex)}>
            Forget all of these
          </button>
        )
      ) : null}
    </>
  )

  return (
    <div className="al-profile">
      {problem ? (
        <div className="al-banner" role="alert">
          <span className="al-banner__icon">
            <Icon name="alert" />
          </span>
          <div className="al-banner__text">{problem}</div>
        </div>
      ) : null}
      {notice ? (
        <p className="al-note" role="status">
          {notice}
        </p>
      ) : null}

      {EDITABLE_KEYS.map((key) => {
        const section = byKey(key)[0]
        const copy = SECTION_COPY[key]!
        const inputId = `al-add-${key}`
        return (
          <section key={key} className="al-group" aria-label={copy.title}>
            <h3 className="al-eyebrow">{copy.title}</h3>
            {section ? <Lines section={section} /> : <p className="al-small">Nothing yet.</p>}
            {adding === key ? (
              <form className="al-addrow" onSubmit={(e) => void submitAdd(key, e)}>
                <label className="al-sr" htmlFor={inputId}>{`Add to ${copy.title}`}</label>
                <input id={inputId} className="al-input" type="text" maxLength={160} autoFocus value={adds[key] ?? ''} onChange={(e) => setAdds((a) => ({ ...a, [key]: e.target.value }))} />
                <button type="submit" className="al-btn al-btn--primary" disabled={busy || !cleanNote(adds[key] ?? '')}>
                  Add
                </button>
              </form>
            ) : (
              <button type="button" className="al-btn al-btn--quiet al-forgetall al-addbtn" onClick={() => setAdding(key)}>
                Add a line
              </button>
            )}
          </section>
        )
      })}

      {others.map((s) => (
        <section key={s.headingIndex} className="al-group" aria-label={s.heading}>
          <h3 className="al-eyebrow">{s.heading}</h3>
          <Lines section={s} />
        </section>
      ))}

      <section className="al-group" aria-label="Who can see what">
        <h3 className="al-eyebrow">Who can see what</h3>
        <p role="status">{carerSharing ? 'Someone you trust sees a short summary. Never your screen.' : 'Nobody else. Sharing is off.'}</p>
        <Switch label="Share my progress" checked={carerSharing} onChange={onCarerSharing} />
      </section>

      {last ? (
        <section className="al-group" aria-label="Last session">
          <h3 className="al-eyebrow">Last time</h3>
          <p>{last.text}</p>
        </section>
      ) : null}

      <button type="button" className="al-btn al-more" aria-expanded={showMore} aria-controls="al-profile-more" onClick={() => setShowMore((v) => !v)}>
        {showMore ? 'Less' : 'More'}
        <Icon name="down" />
      </button>

      {showMore ? (
        <div id="al-profile-more" className="al-profile">
          <section className="al-group" aria-label="Edit the whole file">
            <h3 className="al-eyebrow">The whole file</h3>
            {editing ? (
              <>
                <label className="al-sr" htmlFor="al-profile-draft">
                  Your profile, as text
                </label>
                <textarea id="al-profile-draft" className="al-textarea" value={draft} onChange={(e) => setDraft(e.target.value)} spellCheck />
                {latestOnConflict !== null ? (
                  <div className="al-conflict" role="alert">
                    <strong>It changed while you were editing.</strong>
                    <span>Your text is kept above. Here is the latest.</span>
                    <pre className="al-latest">{latestOnConflict}</pre>
                    <div className="al-actions">
                      <button type="button" className="al-btn" onClick={() => { setDraft(latestOnConflict); setLatestOnConflict(null) }}>
                        Use the latest
                      </button>
                      <button type="button" className="al-btn al-btn--primary" disabled={busy} onClick={() => void saveDraft()}>
                        Save mine over it
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="al-actions">
                    <button type="button" className="al-btn al-btn--primary" disabled={busy} onClick={() => void saveDraft()}>
                      Save
                    </button>
                    <button type="button" className="al-btn" onClick={() => { setEditing(false); setLatestOnConflict(null) }}>
                      Discard changes
                    </button>
                  </div>
                )}
              </>
            ) : (
              <button type="button" className="al-btn" onClick={() => { setDraft(doc.content); setLatestOnConflict(null); setEditing(true) }}>
                Edit the whole file
              </button>
            )}
          </section>

          <section className="al-group al-danger" aria-label="Delete everything">
            <h3 className="al-eyebrow">Start again</h3>
            <button type="button" className="al-btn al-btn--danger" disabled={busy} onClick={() => setConfirmDelete(true)}>
              Delete everything I know about you
            </button>
          </section>
        </div>
      ) : null}

      {confirmDelete ? (
        <ConfirmModal
          personaName=""
          eyebrow="Please check"
          destructive
          request={{ id: 'delete-profile', question: 'Delete everything I know about you? This cannot be undone.', options: [DELETE_YES, DELETE_NO] }}
          onAnswer={(c) => void deleteAll(c)}
        />
      ) : null}
    </div>
  )
}
