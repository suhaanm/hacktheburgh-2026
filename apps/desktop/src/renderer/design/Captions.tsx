import type { ReactElement } from 'react'
import type { CaptionLine } from '../../shared/protocol'

export interface CaptionsProps {
  lines: readonly CaptionLine[]
  personaName: string
  /** How many of the latest lines to show; default 3. */
  max?: number
}

const WHO = { user: 'You', system: 'Note' } as const

/** Only finished lines are announced: interim text is replaced in place many times a second and would flood a screen reader. */
export function announcedLines(lines: readonly CaptionLine[]): CaptionLine[] {
  return lines.filter((line) => line.final)
}

export function Captions({ lines, personaName, max = 3 }: CaptionsProps): ReactElement {
  const shown = lines.slice(-max)
  const who = (line: CaptionLine): string => (line.speaker === 'assistant' ? personaName : WHO[line.speaker])
  return (
    <div className="al-captions" aria-label="Captions">
      <div className="al-sr-only" role="log" aria-live="polite" aria-relevant="additions">
        {announcedLines(shown).map((line) => (
          <p key={line.id}>{`${who(line)}: ${line.text}`}</p>
        ))}
      </div>
      {shown.map((line) => (
        <div key={line.id} className="al-caption" data-speaker={line.speaker} data-final={line.final} aria-hidden="true">
          <span className="al-caption__who">{who(line)}</span>
          <p className="al-caption__text">{line.text}</p>
        </div>
      ))}
    </div>
  )
}
