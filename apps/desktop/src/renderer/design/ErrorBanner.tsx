import type { ReactElement } from 'react'
import { Icon } from './icons'

export interface ErrorBannerProps {
  title?: string
  message: string
  actionLabel?: string
  onAction?: () => void
}

export function ErrorBanner({ title, message, actionLabel, onAction }: ErrorBannerProps): ReactElement {
  return (
    <div className="al-banner" role="alert">
      <span className="al-banner__icon">
        <Icon name="alert" />
      </span>
      <div className="al-banner__text">
        {title ? <strong>{title}</strong> : null}
        {message}
      </div>
      {actionLabel && onAction ? (
        <button type="button" className="al-btn" onClick={onAction}>
          {actionLabel}
        </button>
      ) : null}
    </div>
  )
}
