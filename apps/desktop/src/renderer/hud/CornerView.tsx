// The Knack corner column, presentational: at most one card above at most one pill, bottom-right of the work area (docs/KNACK_UX.md section 7, 06-corner-states.svg).
//   the pill   a status, not an interruption: the brand mark (its ring is the state), at most five words, "n of m" when known, and Stop (End while talking, Open on an error)
//   the card   the one interrupting thing: Stopped, a safety item, an approval that blocks a run (Review / Later), a time-sensitive notice, or a digest or proposal
// Every word comes from a fixed list or from the engine's own fixed templates; nothing here shows model text. A card ignores clicks for its first 600 ms (`armed` false).
import type { ReactElement } from 'react'
import { APP_NAME } from '../../shared/brand'
import { pickCard, type HudAction, type HudActivity, type HudApproval, type HudCard, type HudState } from '../../shared/hud'
import { KILL_HINT, NoticeCard, ProposalCard, killDetail } from './HudView'

export interface CornerViewProps {
  state: HudState
  onAction(action: HudAction): void
  /** False for the first 600 ms after a card appears: its buttons ignore clicks (a mis-click guard). */
  armed?: boolean
  /** The pill has had no change for a while (8 s): it settles to 85% opacity. */
  settled?: boolean
}

/** At most five words, whatever it is given. */
export const limitWords = (s: string, max = 5): string => s.trim().split(/\s+/).slice(0, max).join(' ')

export function StoppedCornerCard({ kill, onAction, armed }: { kill: HudState['kill']; onAction(a: HudAction): void; armed: boolean }): ReactElement {
  return (
    <section className="card stopped" role="alert" aria-live="assertive" data-armed={armed}>
      <h2>
        <span className="glyph" aria-hidden="true" />
        Stopped
      </h2>
      <p className="what">Everything is paused. Nothing runs until you resume.</p>
      <p className="note">{killDetail(kill)}</p>
      <div className="row">
        <button type="button" className="btn look" disabled={!armed} onClick={() => onAction({ type: 'resume' })}>
          Resume
        </button>
      </div>
    </section>
  )
}

export function ApprovalCard({ approval, onAction, armed }: { approval: HudApproval; onAction(a: HudAction): void; armed: boolean }): ReactElement {
  return (
    <section className="card approval" role="status" aria-labelledby="approval-title" data-card-id={approval.id} data-armed={armed}>
      <p className="eyebrow">{`${APP_NAME} · ${approval.source}`}</p>
      <h2 id="approval-title">{approval.title}</h2>
      <p className="what">{approval.body}</p>
      <div className="row">
        <button type="button" className="btn look" disabled={!armed} onClick={() => onAction({ type: 'review', id: approval.id })}>
          Review
        </button>
        <button type="button" className="btn" disabled={!armed} onClick={() => onAction({ type: 'later', id: approval.id })}>
          Later
        </button>
      </div>
    </section>
  )
}

/** The pill: the mark, the words, n of m, and the one button for this phase. */
export function CornerPill({ activity, onAction, settled }: { activity: HudActivity; onAction(a: HudAction): void; settled: boolean }): ReactElement {
  const live = activity.phase === 'error' ? 'assertive' : 'polite'
  const count = activity.step !== null && activity.of !== null ? `${activity.step} of ${activity.of}` : null
  return (
    <div className="cpill" data-phase={activity.phase} data-leaving={activity.leaving} data-settled={settled} role="status" aria-live={live}>
      {activity.phase === 'done' ? (
        <span className="mark check" aria-hidden="true" />
      ) : (
        <span className="mark" aria-hidden="true">
          <span className="ring" />
          <span className="disc" />
        </span>
      )}
      <span className="clabel">{limitWords(activity.label)}</span>
      {count ? <span className="cn">{count}</span> : null}
      {activity.phase === 'working' ? (
        <>
          <span className="cdiv" aria-hidden="true" />
          <button type="button" className="cbtn stop" data-hint={KILL_HINT} onClick={() => onAction({ type: 'kill' })} aria-label="Stop everything. This is the kill switch.">
            <span className="square" aria-hidden="true" />
            Stop
          </button>
        </>
      ) : null}
      {activity.phase === 'voice' ? (
        <>
          <span className="cdiv" aria-hidden="true" />
          <button type="button" className="cbtn" onClick={() => onAction({ type: 'voice_end' })}>
            End
          </button>
        </>
      ) : null}
      {activity.phase === 'error' ? (
        <>
          <span className="cdiv" aria-hidden="true" />
          <button type="button" className="cbtn" onClick={() => onAction({ type: 'pill_open' })}>
            Open
          </button>
        </>
      ) : null}
    </div>
  )
}

function cardView(card: HudCard, state: HudState, onAction: (a: HudAction) => void, armed: boolean): ReactElement {
  switch (card.kind) {
    case 'stopped':
      return <StoppedCornerCard kill={state.kill} onAction={onAction} armed={armed} />
    case 'approval':
      return <ApprovalCard approval={card.approval} onAction={onAction} armed={armed} />
    case 'safety':
    case 'time':
      return <NoticeCard notice={card.notice} onAction={onAction} />
    case 'digest':
      return <ProposalCard proposal={card.proposal} onAction={onAction} />
  }
}

/** Whether the corner column has anything to draw: a card, or a pill. */
export const cornerHasContent = (state: HudState): boolean => pickCard(state) !== null || state.activity !== null

/** What identifies the card on screen, so a new card (not the same one again) re-arms the mis-click guard. */
export function cardKey(state: HudState): string | null {
  const card = pickCard(state)
  if (!card) return null
  return card.kind === 'stopped' ? 'stopped' : card.kind === 'approval' ? `approval:${card.approval.id}` : card.kind === 'digest' ? `digest:${card.proposal.id}` : `${card.kind}:${card.notice.id}`
}

export function CornerView({ state, onAction, armed = true, settled = false }: CornerViewProps): ReactElement | null {
  const card = pickCard(state)
  if (!card && !state.activity) return null
  return (
    <div className="stack corner" data-hud-card>
      {card ? cardView(card, state, onAction, armed) : null}
      {/* While everything is stopped the Stopped card replaces the pill. */}
      {state.activity && !state.kill.killed ? <CornerPill activity={state.activity} onAction={onAction} settled={settled} /> : null}
    </div>
  )
}
