import { useId, useRef, type KeyboardEvent, type ReactElement } from 'react'

export interface SwitchProps {
  label: string
  hint?: string
  checked: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
}

export function Switch({ label, hint, checked, onChange, disabled }: SwitchProps): ReactElement {
  const id = useId()
  return (
    <label className="al-switch" htmlFor={id}>
      <span className="al-switch__text">
        <span className="al-switch__label">{label}</span>
        {hint ? <span className="al-switch__hint">{hint}</span> : null}
      </span>
      <input id={id} type="checkbox" role="switch" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span className="al-switch__track" aria-hidden="true">
        <span className="al-switch__thumb" />
      </span>
    </label>
  )
}

export interface SegmentedProps<T extends string | number> {
  label: string
  options: readonly { value: T; label: string }[]
  value: T
  onChange: (value: T) => void
}

/** Radio-group key model: which option a key moves to (arrows wrap, Home and End jump), or -1 when the key is not ours. */
export function nextSegmentIndex(key: string, current: number, count: number): number {
  const last = count - 1
  if (last < 0) return -1
  if (key === 'ArrowRight' || key === 'ArrowDown') return current >= last ? 0 : current + 1
  if (key === 'ArrowLeft' || key === 'ArrowUp') return current <= 0 ? last : current - 1
  if (key === 'Home') return 0
  if (key === 'End') return last
  return -1
}

export function Segmented<T extends string | number>({ label, options, value, onChange }: SegmentedProps<T>): ReactElement {
  const group = useRef<HTMLDivElement>(null)
  const selected = options.findIndex((o) => o.value === value)
  const tabbable = selected >= 0 ? selected : 0

  // Radio-group keyboard model: arrows move and select, Home and End jump, one tab stop for the whole group.
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>): void => {
    const next = nextSegmentIndex(e.key, tabbable, options.length)
    if (next < 0 || !options[next]) return
    e.preventDefault()
    onChange(options[next].value)
    group.current?.querySelectorAll<HTMLButtonElement>('[role="radio"]')[next]?.focus()
  }

  return (
    <div className="al-seg" role="radiogroup" aria-label={label} ref={group} onKeyDown={onKeyDown}>
      {options.map((o, i) => (
        <button key={o.value} type="button" role="radio" aria-checked={o.value === value} tabIndex={i === tabbable ? 0 : -1} className="al-seg__btn" onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  )
}
