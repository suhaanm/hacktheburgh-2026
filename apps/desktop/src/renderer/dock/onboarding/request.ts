// How the rest of the dock (Settings "Set up again", the menu-bar item, "Permissions…") opens the flow.
import { useEffect, useState } from 'react'
import type { StepId } from './flow'
import { saveResumeStep, stepIndex } from './resume'

export const ONBOARDING_EVENT = 'alongside:onboarding'
export interface OnboardingRequest {
  step?: StepId
}

/** Opens onboarding, from the start or at one screen (for example 'permissions'). */
export function requestOnboarding(req: OnboardingRequest = {}): void {
  saveResumeStep(req.step ? stepIndex(req.step) : 0)
  window.dispatchEvent(new CustomEvent<OnboardingRequest>(ONBOARDING_EVENT, { detail: req }))
}

/** True from a request until `close` is called. Use it next to `settings.onboardingDone`. */
export function useOnboardingRequested(): readonly [boolean, () => void] {
  const [requested, setRequested] = useState(false)
  useEffect(() => {
    const open = (): void => setRequested(true)
    window.addEventListener(ONBOARDING_EVENT, open)
    return () => window.removeEventListener(ONBOARDING_EVENT, open)
  }, [])
  return [requested, () => setRequested(false)] as const
}
