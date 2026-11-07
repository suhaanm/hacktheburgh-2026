import type { ReactElement } from 'react'

export interface SkillStepperProps {
  name: string
  /** 1-based step number, as published in CompanionState.skill. */
  step: number
  stepCount: number
}

export function SkillStepper({ name, step, stepCount }: SkillStepperProps): ReactElement {
  const n = Math.min(Math.max(step, 1), Math.max(stepCount, 1))
  return (
    <div className="al-stepper">
      <div className="al-stepper__top">
        <strong>{name}</strong>
        <span className="al-stepper__count">
          Step {n} of {stepCount}
        </span>
      </div>
      <div className="al-stepper__dots" role="img" aria-label={`Step ${n} of ${stepCount}`}>
        {Array.from({ length: stepCount }, (_, i) => (
          <span key={i} className="al-stepper__dot" data-state={i + 1 < n ? 'done' : i + 1 === n ? 'now' : 'todo'} />
        ))}
      </div>
    </div>
  )
}
