// The HUD, presentational: one kill switch pill that is always there, a card that replaces it while stopped, and a calm
// proposal toast above it at natural breaks. All copy is plain; "Not now" and "Never for this" weigh the same as "Look at it".
import type { ReactElement } from 'react'
import type { HudAction, HudNotice, HudProposal, HudState } from '../../shared/hud'

export interface HudViewProps {
  state: HudState
  onAction(action: HudAction): void
}

// The hours are over the engine's horizon (for example 4 weeks), not per week: say the period or say nothing about it.
export function hoursText(range: [number, number] | null, horizonWeeks: number | null = null): string | null {
  if (!range) return null
  const [lo, hi] = range
  const f = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1))
  const period = horizonWeeks !== null && horizonWeeks > 0 ? ` over ${horizonWeeks === 1 ? 'a week' : `${Number.isInteger(horizonWeeks) ? horizonWeeks : horizonWeeks.toFixed(1)} weeks`}` : ''
  return `about ${f(lo)} to ${f(hi)} hours${period}`
}

// The kill switch's keyboard shortcut (src/main/hotkey.ts KILL_ACCELERATORS), as it is written on this platform.
// Shown on hover only, through a data attribute so the pill's accessible name stays "Stop all".
export const KILL_HINT = typeof navigator !== 'undefined' && !/Mac/i.test(navigator.platform || navigator.userAgent) ? 'Ctrl+Alt+Shift+K' : '⌥⇧⌘K'

export function killDetail(kill: HudState['kill']): string {
  if (kill.engine === null && kill.agent === null) return 'Telling the engine and the agent to stop…'
  if (kill.engine && kill.agent) return 'The engine and the agent were told to stop.'
  if (!kill.engine && !kill.agent) return 'I could not reach the engine or the agent. They may not be running.'
  return kill.engine ? 'The engine was told to stop. The agent could not be reached.' : 'The agent was told to stop. The engine could not be reached.'
}

export function ProposalCard({ proposal, onAction }: { proposal: HudProposal; onAction(a: HudAction): void }): ReactElement {
  const hours = hoursText(proposal.hoursSaved, proposal.horizonWeeks)
  const choose = (choice: 'not_now' | 'never' | 'look') => () => onAction({ type: 'proposal', id: proposal.id, choice })
  return (
    <section className="card proposal" aria-labelledby="proposal-title">
      <p className="eyebrow">I noticed something</p>
      <h2 id="proposal-title">{proposal.title}</h2>
      {proposal.what ? <p className="what">{proposal.what}</p> : null}
      <dl className="facts">
        {proposal.howOften ? (
          <div>
            <dt>How often</dt>
            <dd>{proposal.howOften}</dd>
          </div>
        ) : null}
        {hours ? (
          <div>
            <dt>Could save</dt>
            <dd>{hours}</dd>
          </div>
        ) : null}
        {proposal.touches.length ? (
          <div>
            <dt>Touches</dt>
            <dd>{proposal.touches.join(', ')}</dd>
          </div>
        ) : null}
        {proposal.never.length ? (
          <div>
            <dt>Never does</dt>
            <dd>{proposal.never.join(', ')}</dd>
          </div>
        ) : null}
      </dl>
      <p className="note">Nothing runs unless you say so.</p>
      <div className="row three">
        <button type="button" className="btn look" onClick={choose('look')}>
          Look at it
        </button>
        <button type="button" className="btn" onClick={choose('not_now')}>
          Not now
        </button>
        <button type="button" className="btn" onClick={choose('never')}>
          Never for this
        </button>
      </div>
    </section>
  )
}

export function StoppedCard({ kill, onAction }: { kill: HudState['kill']; onAction(a: HudAction): void }): ReactElement {
  return (
    <section className="card stopped" role="alert" aria-live="assertive">
      <h2>
        <span className="glyph" aria-hidden="true" />
        Stopped
      </h2>
      <p className="what">Everything is paused. Nothing will run until you resume.</p>
      <p className="note">{killDetail(kill)}</p>
      <div className="row">
        <button type="button" className="btn look" onClick={() => onAction({ type: 'resume' })}>
          Resume
        </button>
        <button type="button" className="btn" onClick={() => onAction({ type: 'open_queue' })}>
          Open morning queue
        </button>
      </div>
    </section>
  )
}

// A notice from the attention layer: the engine's own words, one source line, and the buttons it offers, labelled as given. Nothing else.
// A notice with no way to say "not now" or "close" gets a plain Close, so no surface is ever stuck on the screen. Escape also closes it.
const CLOSING_ACTIONS = new Set(['dismiss', 'not_now', 'never'])

export function noticeButtons(notice: HudNotice): { key: string; label: string; send: HudAction; lead: boolean }[] {
  const buttons = notice.actions.map((a) => ({ key: a.id, label: a.label, send: { type: 'notice', id: notice.id, action: a.id } as HudAction, lead: a.id.startsWith('open_') }))
  if (!notice.actions.some((a) => CLOSING_ACTIONS.has(a.id))) buttons.push({ key: 'close', label: 'Close', send: { type: 'notice_closed', id: notice.id, how: 'dismissed' }, lead: false })
  return buttons
}

/** What Escape does: close the notice (how: dismissed). Null when there is no notice or another key was pressed. */
export function noticeEscape(state: HudState, key: string): HudAction | null {
  return key === 'Escape' && state.notice && !state.kill.killed ? { type: 'notice_closed', id: state.notice.id, how: 'dismissed' } : null
}

export function NoticeCard({ notice, onAction }: { notice: HudNotice; onAction(a: HudAction): void }): ReactElement {
  return (
    <section className="card notice" role={notice.urgent ? 'alert' : 'status'} aria-labelledby="notice-title" data-notice-id={notice.id}>
      <h2 id="notice-title">{notice.title}</h2>
      <p className="what">{notice.body}</p>
      <p className="source">{notice.source}</p>
      <div className="row">
        {noticeButtons(notice).map((b) => (
          <button key={b.key} type="button" className={b.lead ? 'btn look' : 'btn'} onClick={() => onAction(b.send)}>
            {b.label}
          </button>
        ))}
      </div>
    </section>
  )
}

/** Whether the HUD has anything to draw: the Stopped card, a notice, a proposal, or the Stop all pill (only while an agent acts). */
export function hudHasContent(state: HudState): boolean {
  return state.kill.killed || state.notice !== null || state.proposal !== null || state.agentActing
}

export function HudView({ state, onAction }: HudViewProps): ReactElement | null {
  const { kill, proposal, notice, agentActing } = state
  // Idle: nothing at all. The window hides itself; the kill hotkey and the menu-bar item are always there.
  if (!hudHasContent(state)) return null
  return (
    <div className="stack" data-hud-card>
      {kill.killed ? <StoppedCard kill={kill} onAction={onAction} /> : notice ? <NoticeCard notice={notice} onAction={onAction} /> : proposal ? <ProposalCard proposal={proposal} onAction={onAction} /> : null}
      {kill.killed || !agentActing ? null : (
        <div className="pill-row">
          <button type="button" className="pill stop" data-hint={KILL_HINT} onClick={() => onAction({ type: 'kill' })} aria-label="Stop everything. This is the kill switch.">
            <span className="glyph" aria-hidden="true" />
            Stop all
          </button>
        </div>
      )}
    </div>
  )
}
