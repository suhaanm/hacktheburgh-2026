// Small accessible controls for the flow. Native radios, checkboxes and ranges underneath, so arrow keys, Space and
// screen readers behave exactly as people expect; the styling only makes them big and calm.
import { useId, type ReactElement, type ReactNode } from 'react'

export interface ChoiceOption<T extends string | number> {
  value: T
  title: string
  line?: string
  /** A colour token name for a small dot, e.g. 'accent-marcus'. Never the only cue: the title says it too. */
  swatch?: string
}

export interface ChoiceProps<T extends string | number> {
  legend: string
  /** null = nothing chosen yet. */
  value: T | null
  /** For numbers saved by other screens: tick the nearest option instead of requiring an exact match. */
  snap?: boolean
  options: readonly ChoiceOption<T>[]
  onChange: (value: T) => void
  layout?: 'stack' | 'row' | 'grid'
  hint?: string
  disabled?: boolean
}

function nearest<T extends string | number>(options: readonly ChoiceOption<T>[], value: T): T | undefined {
  const target = Number(value)
  let best: T | undefined
  let gap = Infinity
  for (const o of options) {
    const d = Math.abs(Number(o.value) - Number(value))
    if (d < gap) {
      gap = d
      best = o.value
    }
  }
  return best
}

export function Choice<T extends string | number>({ legend, value, snap, options, onChange, layout = 'stack', hint, disabled }: ChoiceProps<T>): ReactElement {
  const name = useId()
  const selected = value === null ? undefined : snap ? nearest(options, value) : options.find((o) => o.value === value)?.value
  return (
    <fieldset className="ob-field" disabled={disabled}>
      <legend className="ob-legend">{legend}</legend>
      {hint ? <p className="ob-hint">{hint}</p> : null}
      <div className="ob-opts" data-layout={layout}>
        {options.map((o) => (
          <label key={String(o.value)} className="ob-opt ob-opt--radio">
            <input type="radio" name={name} value={String(o.value)} checked={o.value === selected} onChange={() => onChange(o.value)} />
            <span className="ob-opt__body">
              <span className="ob-opt__mark" aria-hidden="true" />
              <span className="ob-opt__text">
                <span className="ob-opt__title">{o.title}</span>
                {o.line ? <span className="ob-opt__line">{o.line}</span> : null}
              </span>
              {o.swatch ? <span className="ob-opt__swatch" aria-hidden="true" style={{ background: `var(--${o.swatch})` }} /> : null}
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  )
}

export interface ChipGroupProps<T extends string> {
  legend: string
  hint?: string
  options: readonly { value: T; label: string }[]
  selected: readonly T[]
  onToggle: (value: T) => void
}

export function ChipGroup<T extends string>({ legend, hint, options, selected, onToggle }: ChipGroupProps<T>): ReactElement {
  return (
    <fieldset className="ob-field">
      <legend className="ob-legend">{legend}</legend>
      {hint ? <p className="ob-hint">{hint}</p> : null}
      <div className="ob-chips">
        {options.map((o) => (
          <label key={o.value} className="ob-opt ob-opt--chip">
            <input type="checkbox" checked={selected.includes(o.value)} onChange={() => onToggle(o.value)} />
            <span className="ob-opt__body">
              <span className="ob-opt__mark" aria-hidden="true" />
              <span className="ob-opt__title">{o.label}</span>
            </span>
          </label>
        ))}
      </div>
    </fieldset>
  )
}

export interface TextFieldProps {
  label: string
  hint?: string
  value: string
  placeholder?: string
  onChange: (value: string) => void
  onEnter?: () => void
  autoComplete?: string
}

export function TextField({ label, hint, value, placeholder, onChange, onEnter, autoComplete }: TextFieldProps): ReactElement {
  const id = useId()
  const hintId = `${id}-hint`
  return (
    <div className="ob-field">
      <label className="ob-legend" htmlFor={id}>
        {label}
      </label>
      {hint ? (
        <p className="ob-hint" id={hintId}>
          {hint}
        </p>
      ) : null}
      <input
        id={id}
        className="ob-input"
        type="text"
        value={value}
        maxLength={40}
        placeholder={placeholder}
        autoComplete={autoComplete ?? 'off'}
        aria-describedby={hint ? hintId : undefined}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && onEnter) {
            e.preventDefault()
            onEnter()
          }
        }}
      />
    </div>
  )
}

export interface SliderProps {
  label: string
  value: number
  min: number
  max: number
  step: number
  lowLabel: string
  highLabel: string
  valueText: string
  disabled?: boolean
  onChange: (value: number) => void
}

export function Slider({ label, value, min, max, step, lowLabel, highLabel, valueText, disabled, onChange }: SliderProps): ReactElement {
  const id = useId()
  return (
    <div className="ob-field ob-slider" data-disabled={disabled ? 'true' : 'false'}>
      <label className="ob-legend" htmlFor={id}>
        {label}
      </label>
      <input id={id} type="range" min={min} max={max} step={step} value={value} disabled={disabled} aria-valuetext={valueText} onChange={(e) => onChange(Number(e.target.value))} />
      <div className="ob-slider__ends" aria-hidden="true">
        <span>{lowLabel}</span>
        <span>{highLabel}</span>
      </div>
    </div>
  )
}

export function Section({ children }: { children: ReactNode }): ReactElement {
  return <div className="ob-section">{children}</div>
}
