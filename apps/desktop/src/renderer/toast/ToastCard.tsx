import type { MouseEvent, ReactElement } from 'react'
import type { ConfirmRequest } from '../../shared/protocol'

export const TOAST_TITLE = 'Alongside needs your OK'

export interface ToastCardProps {
  request: ConfirmRequest
  /** 0 to 1 of the auto-decline time still left; null when unknown (no bar). */
  remaining: number | null
  /** false for a moment after the toast appears: a click already on its way to something else must not answer it. */
  armed: boolean
  onAnswer: (choice: string) => void
}

/** Pure view of one confirmation. Only a real (trusted) pointer or key activation of a button answers; nothing else does. */
export function ToastCard({ request, remaining, armed, onAnswer }: ToastCardProps): ReactElement {
  const [first, second] = request.options
  const choose = (choice: string) => (e: Pick<MouseEvent<HTMLButtonElement>, 'isTrusted'>) => {
    if (!e.isTrusted || !armed) return
    onAnswer(choice)
  }
  return (
    <div className="al-toast" data-toast-card role="alertdialog" aria-labelledby="al-toast-title" aria-describedby="al-toast-q">
      <p className="al-toast__title" id="al-toast-title">
        {TOAST_TITLE}
      </p>
      <p className="al-toast__q" id="al-toast-q">
        {request.question.slice(0, 500)}
      </p>
      <div className="al-toast__choices">
        <button type="button" className="al-btn al-btn--primary al-btn--lg al-toast__yes" onClick={choose(first)}>
          {first}
        </button>
        <button type="button" className="al-btn al-btn--lg al-toast__no" onClick={choose(second)}>
          {second}
        </button>
      </div>
      {remaining === null ? null : (
        <div className="al-toast__time" role="progressbar" aria-label="Time left to answer" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(remaining * 100)}>
          <div className="al-toast__timefill" style={{ width: `${Math.max(0, Math.min(1, remaining)) * 100}%` }} />
        </div>
      )}
    </div>
  )
}

/** Share (0 to 1) of the time between `startedAt` and `expiresAt` that is still left at `now`. */
export function countdownRemaining(startedAt: number, expiresAt: number, now: number): number {
  const total = expiresAt - startedAt
  if (total <= 0) return 0
  return Math.max(0, Math.min(1, (expiresAt - now) / total))
}
