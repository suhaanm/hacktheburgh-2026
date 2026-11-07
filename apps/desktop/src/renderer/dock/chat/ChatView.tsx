import { useEffect, useRef, useState, type FormEvent, type ReactElement, type ReactNode } from 'react'
import { Segmented } from '../../design'
import type { ChatMessage, ChatMode } from './bus'

export interface ChatViewProps {
  messages: readonly ChatMessage[]
  mode: ChatMode
  onMode: (mode: ChatMode) => void
  onSend: (text: string) => void
  /** Small chip shown at the right of the top bar (the help level). */
  topRight?: ReactNode
  /** Pinned under the top bar (the lesson step). */
  pinned?: ReactNode
  /** Scrolls with the conversation, above the first bubble (helpers, errors). */
  above?: ReactNode
  /** Shown when there is nothing to read yet. */
  empty: ReactNode
  /** Notes that are not part of the conversation (for example "Voice is off"), shown as small centred lines. */
  asides?: readonly string[]
}

// Survives the panel collapsing and re-opening, so a half-typed message is not lost.
let keptDraft = ''

/** Conversation view: assistant bubbles on the left, the user's on the right, a text box and Send at the bottom. */
export function ChatView({ messages, mode, onMode, onSend, topRight, pinned, above, empty, asides = [] }: ChatViewProps): ReactElement {
  const [draft, setDraft] = useState(keptDraft)
  const end = useRef<HTMLDivElement>(null)
  const last = messages[messages.length - 1]

  useEffect(() => {
    keptDraft = draft
  }, [draft])

  useEffect(() => {
    end.current?.scrollIntoView({ block: 'end' })
  }, [messages.length, last?.text])

  const submit = (e: FormEvent): void => {
    e.preventDefault()
    const text = draft.trim()
    if (!text) return
    onSend(text)
    setDraft('')
  }

  return (
    <div className="al-chat">
      <div className="al-chat__top">
        <Segmented
          label="How we talk"
          value={mode}
          onChange={onMode}
          options={[
            { value: 'voice', label: 'Talk' },
            { value: 'text', label: 'Type' },
          ]}
        />
        {topRight}
      </div>
      {pinned}
      {messages.length === 0 ? (
        <div className="al-thread">
          {above}
          <div className="al-empty">{empty}</div>
        </div>
      ) : (
        <div className="al-thread" role="log" aria-live="polite" aria-label="Conversation">
          {above}
          {asides.map((a) => (
            <p key={a} className="al-aside">
              {a}
            </p>
          ))}
          {messages.map((m) => (
            <div key={m.id} className="al-bubble" data-role={m.role} data-final={m.final}>
              {m.text}
            </div>
          ))}
          <div ref={end} />
        </div>
      )}
      <form className="al-composer" onSubmit={submit}>
        <label className="al-sr" htmlFor="al-chat-input">
          Type a message
        </label>
        <input id="al-chat-input" className="al-input" type="text" autoComplete="off" placeholder={mode === 'text' ? 'Type your question' : 'Or type here'} value={draft} onChange={(e) => setDraft(e.target.value)} />
        <button type="submit" className="al-btn al-btn--primary" disabled={draft.trim() === ''}>
          Send
        </button>
      </form>
    </div>
  )
}
