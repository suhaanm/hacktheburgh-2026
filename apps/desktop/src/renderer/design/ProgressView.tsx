import type { ReactElement } from 'react'
import type { ProgressData, SkillMode } from '../../main/teaching/progress'
import { Icon } from './icons'

const RECENT = 8

const MODE_TEXT: Record<SkillMode, string> = {
  not_started: 'Not tried yet',
  with_help: 'With help',
  mostly_alone: 'Mostly on my own',
  on_my_own: 'On my own',
}

function formatDate(ms: number): string {
  return new Date(ms).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

export function HintsChart({ hints }: { hints: readonly number[] }): ReactElement {
  const data = hints.slice(-RECENT)
  const W = 340
  const H = 210
  const L = 34
  const R = 8
  const T = 22
  const B = 40
  const top = Math.max(4, Math.ceil(Math.max(0, ...data) / 2) * 2)
  const ticks = [0, top / 2, top]
  const pw = W - L - R
  const ph = H - T - B
  const bw = pw / Math.max(data.length, 1)
  const y = (v: number): number => T + ph - (v / top) * ph
  const description = data.length ? `Bar chart. Hints I gave you in each of your last ${data.length} tasks: ${data.join(', ')}.` : 'Bar chart. No tasks yet.'
  return (
    <div className="al-chart">
      <h3 className="al-h3">Hints I gave you</h3>
      {data.length === 0 ? (
        <p className="al-muted">Your first lesson will show here.</p>
      ) : (
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={description}>
          {ticks.map((v) => (
            <g key={v}>
              <line className="al-chart__grid" x1={L} x2={W - R} y1={y(v)} y2={y(v)} />
              <text x={L - 8} y={y(v) + 4} textAnchor="end">
                {v}
              </text>
            </g>
          ))}
          {data.map((v, i) => {
            const x = L + i * bw + bw * 0.18
            const w = bw * 0.64
            return (
              <g key={i}>
                {v > 0 ? <rect className="al-chart__bar" x={x} y={y(v)} width={w} height={y(0) - y(v)} rx={4} /> : <rect className="al-chart__bar" x={x} y={y(0) - 4} width={w} height={4} rx={2} />}
                <text className="al-chart__val" x={x + w / 2} y={y(v) - 6} textAnchor="middle">
                  {v}
                </text>
                <text x={x + w / 2} y={H - B + 18} textAnchor="middle">
                  {hints.length - data.length + i + 1}
                </text>
              </g>
            )
          })}
          <text x={L + pw / 2} y={H - 6} textAnchor="middle">
            Task
          </text>
        </svg>
      )}
      <p className="al-chart__note">Fewer hints means you need me less.</p>
    </div>
  )
}

export function ConfidenceChart({ ratings }: { ratings: readonly number[] }): ReactElement {
  const data = ratings.slice(-RECENT)
  const W = 340
  const H = 150
  const L = 34
  const R = 16
  const T = 14
  const B = 26
  const pw = W - L - R
  const ph = H - T - B
  const x = (i: number): number => (data.length === 1 ? L + pw / 2 : L + (i / (data.length - 1)) * pw)
  const y = (v: number): number => T + ph - ((v - 1) / 4) * ph
  return (
    <div className="al-chart">
      <h3 className="al-h3">How you felt</h3>
      {data.length === 0 ? (
        <p className="al-muted">Ratings show here after a lesson.</p>
      ) : (
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Line chart. Your own confidence rating from 1 to 5 after each task: ${data.join(', ')}.`}>
          {[1, 3, 5].map((v) => (
            <g key={v}>
              <line className="al-chart__grid" x1={L} x2={W - R} y1={y(v)} y2={y(v)} />
              <text x={L - 8} y={y(v) + 4} textAnchor="end">
                {v}
              </text>
            </g>
          ))}
          <path className="al-chart__line" d={data.map((v, i) => `${i ? 'L' : 'M'}${x(i)} ${y(v)}`).join(' ')} />
          {data.map((v, i) => (
            <circle key={i} className="al-chart__dot" cx={x(i)} cy={y(v)} r={i === data.length - 1 ? 7 : 4} />
          ))}
          <text className="al-chart__val" x={x(data.length - 1)} y={y(data[data.length - 1]!) - 14} textAnchor="end">
            {data[data.length - 1]} of 5
          </text>
          <text x={L + pw / 2} y={H - 4} textAnchor="middle">
            How sure you felt
          </text>
        </svg>
      )}
    </div>
  )
}

export function ProgressView({ data }: { data: ProgressData | null }): ReactElement {
  if (!data) return <p className="al-muted">Loading your progress.</p>
  // Hints per task, all skills, oldest to newest: the anti-dependency picture.
  const hints = data.hintsPerTask
    .flatMap((s) => s.series)
    .sort((a, b) => a.at - b.at)
    .map((p) => p.hints)
  const next = data.nextSuggested ? data.skills.find((s) => s.skillId === data.nextSuggested?.skillId) : undefined
  return (
    <div className="al-progress">
      {data.overall.attempts > 0 ? <p className="al-h3">{data.overall.headline}</p> : null}
      {data.doneForMe ? <p className="al-donefor" role="note">{data.doneForMe.text}</p> : null}
      <section className="al-section">
        <h3 className="al-h2">Things you can do now</h3>
        {data.canDoNow.length === 0 ? (
          <p className="al-muted">Nothing yet.</p>
        ) : (
          <ul className="al-can">
            {data.canDoNow.map((item) => (
              <li key={item.skillId} className="al-can__item">
                <span className="al-can__tick">
                  <Icon name="check" />
                </span>
                <span className="al-can__text">{item.text}</span>
                <span className="al-can__date">{formatDate(item.since)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="al-section">
        <h3 className="al-h2">Your skills</h3>
        <ul className="al-tree">
          {data.skills.map((s) => {
            const label = s.reviewDue ? `${MODE_TEXT[s.mode]}. Refresher due` : MODE_TEXT[s.mode]
            return (
              <li key={s.skillId} className="al-skill">
                <div className="al-skill__top">
                  <span className="al-skill__name">{s.name}</span>
                  <span className="al-skill__state">{label}</span>
                </div>
                <div className="al-skill__fill" role="img" aria-label={`${s.name}: ${label}`}>
                  {[1, 2, 3, 4].map((i) => (
                    <span key={i} data-on={s.mode !== 'not_started' && i <= s.level} />
                  ))}
                </div>
              </li>
            )
          })}
        </ul>
        {next && data.nextSuggested ? (
          <p className="al-muted">
            Next: <strong>{next.name}</strong>
          </p>
        ) : null}
      </section>
      <HintsChart hints={hints} />
      <ConfidenceChart ratings={data.confidence.points.map((p) => p.rating)} />
    </div>
  )
}
