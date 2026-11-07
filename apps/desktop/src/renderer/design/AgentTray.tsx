import { useId, useState, type ReactElement } from 'react'
import type { AgentChip } from '../../shared/protocol'
import { Icon } from './icons'

const STATUS_TEXT: Record<AgentChip['status'], string> = { running: 'Looking', done: 'Done', error: 'Couldn’t finish', cancelled: 'Stopped' }

function Detail({ chip }: { chip: AgentChip }): ReactElement {
  const result = chip.result
  return (
    <>
      {chip.summary ? <p>{chip.summary}</p> : null}
      {result?.kind === 'scam_check' ? (
        <>
          {result.report.redFlags.length > 0 ? (
            <ul className="al-flags">
              {result.report.redFlags.map((f) => (
                <li key={f.phrase} className="al-flag">
                  <q>{f.phrase}</q> {'–'} {f.why}
                </li>
              ))}
            </ul>
          ) : null}
          {result.report.advice.map((a) => (
            <p key={a}>{a}</p>
          ))}
          <p className="al-small">{result.report.humanHelp}</p>
        </>
      ) : null}
      {result?.kind === 'lookup' || result?.kind === 'lesson_summary' ? <p>{result.text}</p> : null}
    </>
  )
}

function AgentChipView({ chip, onCancel }: { chip: AgentChip; onCancel: (id: string) => void }): ReactElement {
  const [open, setOpen] = useState(chip.status === 'done' && chip.kind === 'scam_check')
  const bodyId = useId()
  return (
    <div className="al-agent" data-status={chip.status} role="listitem">
      <button type="button" className="al-agent__head" aria-expanded={open} aria-controls={bodyId} onClick={() => setOpen((v) => !v)}>
        <span className="al-agent__title">{chip.title}</span>
        <span className="al-agent__status">
          {chip.status === 'running' ? <span className="al-spinner" aria-hidden="true" /> : null}
          {STATUS_TEXT[chip.status]}
        </span>
        <span className="al-agent__chev">
          <Icon name="down" />
        </span>
      </button>
      <div className="al-agent__body" id={bodyId} hidden={!open}>
        <Detail chip={chip} />
        {chip.status === 'running' ? (
          <button type="button" className="al-btn" onClick={() => onCancel(chip.id)}>
            Stop this check
          </button>
        ) : null}
      </div>
    </div>
  )
}

export interface AgentTrayProps {
  agents: readonly AgentChip[]
  onCancel: (id: string) => void
}

export function AgentTray({ agents, onCancel }: AgentTrayProps): ReactElement | null {
  if (agents.length === 0) return null
  return (
    <div className="al-tray" role="list" aria-label="Helpers working for you">
      {agents.map((a) => (
        <AgentChipView key={a.id} chip={a} onCancel={onCancel} />
      ))}
    </div>
  )
}
