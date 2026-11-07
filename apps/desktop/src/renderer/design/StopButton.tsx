import type { ReactElement } from 'react'
import { Icon } from './icons'

export function StopButton({ onStop, compact = false }: { onStop: () => void; compact?: boolean }): ReactElement {
  return (
    <button type="button" className={`al-btn al-btn--danger al-stop${compact ? ' al-stop--compact' : ''}`} aria-label="Stop. I will stop listening and looking." onClick={onStop}>
      <Icon name="stop" />
      Stop
    </button>
  )
}
