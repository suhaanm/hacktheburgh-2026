import { useCallback, useEffect, useReducer, useRef, useState, type ReactElement } from 'react'
import { DEFAULT_PERSONA, PERSONAS } from '../../../shared/personas'
import {
  STEP_IDS, answersToSettings, canGoBack, initialAnswers, isLastStep, nextLabel, profileLines, progressLabel, reduce, startFlow, stepId,
  type Answers, type OnboardingSettingsPatch, type OnboardingSettingsView,
} from './flow'
import { ONBOARDING_EVENT, type OnboardingRequest } from './request'
import { finishOnboarding, saveProfileLines, type PersistApi } from './persist'
import { readResumeStep, saveResumeStep, stepIndex } from './resume'
import type { PermissionsApi } from './permissions'
import { AboutStep, ComfortStep, HandsStep, HelloStep, HelperStep, LookStep, PermissionsScreen, ReadyStep, StyleStep, titleFor, type StepProps } from './steps'
import './onboarding.css'

export interface OnboardingFlowProps {
  /** What is saved now, so "Set up again" starts from the current choices. */
  settings: OnboardingSettingsView
  /** Optimistic settings patch (the dock's own useSettings patch): every change shows on the dock at once. */
  onPatch: (patch: OnboardingSettingsPatch) => void
  onDone: (outcome: 'finished' | 'skipped') => void
  /** Defaults to window.alongside. Tests and the gallery pass fakes. */
  api?: PersistApi
  permissionsApi?: PermissionsApi
  startStep?: number
}

const defaultApi = (): PersistApi => window.alongside as PersistApi

export function OnboardingFlow({ settings, onPatch, onDone, api, permissionsApi, startStep }: OnboardingFlowProps): ReactElement {
  const [state, dispatch] = useReducer(reduce, undefined, () => ({ ...startFlow(initialAnswers(settings, DEFAULT_PERSONA)), step: startStep ?? readResumeStep() }))
  const [busy, setBusy] = useState(false)
  const title = useRef<HTMLHeadingElement>(null)
  const scroller = useRef<HTMLDivElement>(null)
  const first = useRef(true)

  const id = stepId(state)
  const personaName = PERSONAS[state.answers.persona].displayName
  const heading = titleFor(id, state.answers, personaName)

  const set = useCallback(
    (patch: Partial<Answers>) => {
      dispatch({ type: 'set', patch })
      // The name is saved when leaving its screen, not on every keystroke.
      const { userName: _typing, ...rest } = patch
      const live = answersToSettings(rest)
      if (Object.keys(live).length > 0) onPatch(live)
    },
    [onPatch],
  )

  // A request from elsewhere (menu bar "Permissions…") can move a flow that is already open.
  useEffect(() => {
    const move = (e: Event): void => {
      const step = (e as CustomEvent<OnboardingRequest>).detail?.step
      dispatch({ type: 'go', step: step ? stepIndex(step) : 0 })
    }
    window.addEventListener(ONBOARDING_EVENT, move)
    return () => window.removeEventListener(ONBOARDING_EVENT, move)
  }, [])

  useEffect(() => {
    saveResumeStep(state.step)
    scroller.current?.scrollTo({ top: 0 })
    if (first.current) {
      first.current = false
      return
    }
    title.current?.focus({ preventScroll: true })
  }, [state.step])

  const finish = async (outcome: 'finished' | 'skipped'): Promise<void> => {
    if (busy) return
    setBusy(true)
    try {
      await finishOnboarding(api ?? defaultApi(), state.answers, state.touched)
    } finally {
      saveResumeStep(0)
      onDone(outcome)
    }
  }

  const next = (): void => {
    if (isLastStep(state)) return void finish('finished')
    if (id === 'about' && state.touched.userName) onPatch(answersToSettings({ userName: state.answers.userName }))
    // Save the get-to-know-you answers as soon as they are given, so a restart for Screen Recording loses nothing.
    if (id === 'style') void saveProfileLines(api ?? defaultApi(), profileLines(state.answers, state.touched)).catch(() => undefined)
    dispatch({ type: 'next' })
  }
  const props: StepProps = { answers: state.answers, set, personaName, next }

  let body: ReactElement
  switch (id) {
    case 'hello':
      body = <HelloStep {...props} />
      break
    case 'about':
      body = <AboutStep {...props} />
      break
    case 'style':
      body = <StyleStep {...props} />
      break
    case 'comfort':
      body = <ComfortStep {...props} />
      break
    case 'look':
      body = <LookStep {...props} />
      break
    case 'helper':
      body = <HelperStep {...props} />
      break
    case 'permissions':
      body = <PermissionsScreen api={permissionsApi} />
      break
    case 'hands':
      body = <HandsStep {...props} />
      break
    default:
      body = <ReadyStep {...props} />
  }

  return (
    <div className="ob" data-step={id}>
      <header className="ob__top">
        <div className="ob__prog" role="img" aria-label={progressLabel(state)}>
          <span className="ob__count">{progressLabel(state)}</span>
          <span className="ob__dots" aria-hidden="true">
            {STEP_IDS.map((s, i) => (
              <span key={s} data-state={i < state.step ? 'done' : i === state.step ? 'now' : 'todo'} />
            ))}
          </span>
        </div>
        {id !== 'ready' ? (
          <button type="button" className="al-btn al-btn--quiet ob__skip" disabled={busy} onClick={() => void finish('skipped')}>
            Skip for now
          </button>
        ) : null}
      </header>

      <div className="ob__scroll" ref={scroller}>
        <section className="ob__step" aria-labelledby="ob-title">
          <h2 className="ob__title" id="ob-title" ref={title} tabIndex={-1}>
            {heading}
          </h2>
          {body}
        </section>
      </div>

      <footer className="ob__foot">
        {canGoBack(state) ? (
          <button type="button" className="al-btn al-btn--lg ob__back" onClick={() => dispatch({ type: 'back' })}>
            Back
          </button>
        ) : null}
        <button type="button" className="al-btn al-btn--lg al-btn--primary ob__next" disabled={busy} onClick={next}>
          {nextLabel(id)}
        </button>
      </footer>
      <div className="ob__sr" role="status" aria-live="polite">{`${progressLabel(state)}. ${heading}`}</div>
    </div>
  )
}
