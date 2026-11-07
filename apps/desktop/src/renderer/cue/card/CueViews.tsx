// The three things the Cue panel can show, as pure views of a CueView: no hooks and no clocks here, so a test can call them and read what
// they render. The panel (CuePanel.tsx) stacks them, cross-fades them and reports their size.
import type { ReactElement } from 'react'
import type { CueCardAction, CueChipView, CueOfferView, CueQuestionView, CueWhyView } from '../../../main/cue/ipc'

export interface ViewProps<V> {
  view: V
  onAction: (a: CueCardAction) => void
}

const Caret = (): ReactElement => (
  <svg className="caret" viewBox="0 0 8 5" aria-hidden="true">
    <path d="M0.8 0.8 L4 4 L7.2 0.8" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)
const Cross = (): ReactElement => (
  <svg viewBox="0 0 8 8" aria-hidden="true">
    <path d="M1 1 L7 7 M7 1 L1 7" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
  </svg>
)

/** "most experts do this next" -> "Most experts do this next." */
export const sentence = (s: string): string => `${s.charAt(0).toUpperCase()}${s.slice(1)}${/[.!?]$/.test(s) ? '' : '.'}`

export function WhyPopover({ why, canShowMe, onAction }: { why: CueWhyView | null; canShowMe: boolean; onAction: (a: CueCardAction) => void }): ReactElement {
  return (
    <div className="pop" role="group" aria-label="Why this step">
      {why?.reason ? <p className="reason">{why.reason}</p> : null}
      {why?.phrase ? (
        <p className="phrase">
          <span>{sentence(why.phrase)}</span>
          {why.simulated ? (
            <span className="tag" role="note" aria-label="Simulated experts, not recorded people">
              Simulated
            </span>
          ) : null}
        </p>
      ) : null}
      <div className="actions">
        {canShowMe ? (
          <button type="button" className="btn" onClick={() => onAction({ type: 'show_me' })}>
            Show me
          </button>
        ) : null}
        <button type="button" className="btn" onClick={() => onAction({ type: 'know_this' })}>
          I know this
        </button>
      </div>
    </div>
  )
}

export function ChipView({ view, onAction }: ViewProps<CueChipView>): ReactElement {
  // A chip that is only the collapsed answer of the question has no reason to give yet: it is plain.
  const plain = view.pending
  return (
    <div className="chip-wrap">
      <div className="chip" data-open={view.open} data-plain={plain}>
        {plain ? (
          <span className="chip-main" data-plain="true">
            <span className="chip-text">{view.text}</span>
          </span>
        ) : (
          <button type="button" className="chip-main" aria-expanded={view.open} aria-label={`${view.text}. Why this?`} onClick={() => onAction({ type: 'why', open: !view.open })}>
            {view.stepN !== null ? (
              <span className="pill" aria-label={`Step ${view.stepN}`}>
                {view.stepN}
              </span>
            ) : null}
            <span className="chip-text">{view.text}</span>
            <Caret />
          </button>
        )}
        {plain ? null : (
          <button type="button" className="chip-x" aria-label="Dismiss, Escape" onClick={() => onAction({ type: 'dismiss' })}>
            <Cross />
            <span className="chip-esc">esc</span>
          </button>
        )}
      </div>
      {plain ? null : (
        <div className="pop-wrap" data-open={view.open}>
          <div className="pop-clip" {...(view.open ? {} : ({ inert: '' } as Record<string, string>))}>
            <div className="pop-pad">
              <WhyPopover why={view.why} canShowMe={view.canShowMe} onAction={onAction} />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export function QuestionView({ view, onAction }: ViewProps<CueQuestionView>): ReactElement {
  return (
    <div className="card" role="dialog" aria-label={view.question}>
      <div className="card-head">
        <p className="question">{view.question}</p>
        <button type="button" className="esc" aria-label="Dismiss, Escape" onClick={() => onAction({ type: 'dismiss' })}>
          esc
        </button>
      </div>
      <div className="rows" role="group" aria-label="Options">
        {view.options.map((o) => (
          <button key={o.id} type="button" className="row" onClick={() => onAction({ type: 'answer', id: o.id })} aria-keyshortcuts={`Alt+${o.key}`}>
            <span className="cap">{`${view.chord}${o.key}`}</span>
            <span className="row-label">{o.label}</span>
          </button>
        ))}
        <button type="button" className="row else" onClick={() => onAction({ type: 'other' })}>
          <span className="cap">{`${view.chord}${view.other.key}`}</span>
          <span className="row-label">{view.other.label}</span>
        </button>
      </div>
    </div>
  )
}

export function OfferView({ view, onAction }: ViewProps<CueOfferView>): ReactElement {
  return (
    <div className="offer" role="dialog" aria-label={view.text}>
      <p>{view.text}</p>
      <div className="actions">
        <button type="button" className="btn" onClick={() => onAction({ type: 'offer', yes: true })}>
          Show me
        </button>
        <button type="button" className="btn" onClick={() => onAction({ type: 'offer', yes: false })}>
          Not now
        </button>
      </div>
    </div>
  )
}
