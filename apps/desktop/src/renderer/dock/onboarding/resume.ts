// Remembers which screen the person was on, so a restart (macOS needs one after Screen Recording is allowed)
// brings them back to the same place instead of the beginning. Storage can be unavailable; that just means "start again".
import { LAST_STEP, STEP_IDS, type StepId } from './flow'

const KEY = 'alongside.onboarding.step'
type Reader = Pick<Storage, 'getItem'>
type Writer = Pick<Storage, 'setItem' | 'removeItem'>

const local = (): Storage | undefined => {
  try {
    return globalThis.localStorage
  } catch {
    return undefined
  }
}

export function readResumeStep(store: Reader | undefined = local()): number {
  try {
    const n = Number(store?.getItem(KEY))
    return Number.isInteger(n) && n > 0 && n < LAST_STEP ? n : 0
  } catch {
    return 0
  }
}

export function saveResumeStep(step: number, store: Writer | undefined = local()): void {
  try {
    if (step > 0 && step < LAST_STEP) store?.setItem(KEY, String(step))
    else store?.removeItem(KEY)
  } catch {
    // Private mode: the flow simply starts from the beginning next time.
  }
}

export const stepIndex = (id: StepId): number => STEP_IDS.indexOf(id)
