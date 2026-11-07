import { useEffect, useRef, useState, type ReactElement } from 'react'
import type { HelpLevel } from '../../shared/protocol'
import { Icon } from './icons'
import { LEVEL_NAMES, LEVEL_SHORT, LEVEL_SUPPORT } from './levels'

export interface LevelChipProps {
  level: HelpLevel
  locked?: boolean
  variant?: 'default' | 'compact' | 'hero' | 'dots'
}

interface Word {
  key: number
  level: HelpLevel
  state: 'idle' | 'in' | 'out'
}

/**
 * The Help Ladder made visible: four quiet dots that empty as the learner takes over, with the level name sliding to the next.
 * Hero variant is sized to be read from five metres away.
 */
export function LevelChip({ level, locked = false, variant = 'default' }: LevelChipProps): ReactElement {
  const [words, setWords] = useState<Word[]>([{ key: 0, level, state: 'idle' }])
  const [change, setChange] = useState<'less' | 'more' | null>(null)
  const previous = useRef(level)
  const counter = useRef(1)

  useEffect(() => {
    if (previous.current === level) return
    const from = previous.current
    previous.current = level
    setWords((w) => [...w.map((x) => ({ ...x, state: 'out' as const })), { key: counter.current++, level, state: 'in' }])
    setChange(level > from ? 'less' : 'more')
    const settle = setTimeout(() => setWords((w) => w.filter((x) => x.state !== 'out')), 340)
    const quiet = setTimeout(() => setChange(null), 3600)
    return () => {
      clearTimeout(settle)
      clearTimeout(quiet)
    }
  }, [level])

  const name = LEVEL_NAMES[level]
  const className = `al-level${variant === 'compact' ? ' al-level--compact' : ''}${variant === 'hero' ? ' al-level--hero' : ''}${variant === 'dots' ? ' al-level--dots' : ''}`
  const deltaText = change === 'less' ? 'Less help. You’re leading.' : 'More help, as you asked.'

  return (
    <div className={className} role="group" aria-label={`Help level ${level} of 4: ${name}${locked ? ', locked' : ''}`} data-level={level} data-changing={change !== null}>
      <div className="al-level__bars" aria-hidden="true">
        {[1, 2, 3, 4].map((i) => (
          <span key={i} className="al-level__bar" data-on={i <= LEVEL_SUPPORT[level]} />
        ))}
      </div>
      <span className="al-level__text">
        <span className="al-level__kicker">Help level {level} of 4</span>
        <span className="al-level__name">
          {words.map((w) => (
            <span key={w.key} className={`al-level__word${w.state === 'in' ? ' is-entering' : ''}${w.state === 'out' ? ' is-leaving' : ''}`}>
              {LEVEL_SHORT[w.level]}
            </span>
          ))}
        </span>
      </span>
      {locked ? (
        <span className="al-level__lock">
          <Icon name="lock" />
          <span className="al-level__locktext">Locked</span>
        </span>
      ) : null}
      <span className="al-level__delta" aria-hidden="true">
        {deltaText}
      </span>
      <span className="al-sr" aria-live="polite">
        {change ? `Help level changed to ${name}. ${change === 'less' ? 'Less help.' : 'More help.'}` : ''}
      </span>
    </div>
  )
}
