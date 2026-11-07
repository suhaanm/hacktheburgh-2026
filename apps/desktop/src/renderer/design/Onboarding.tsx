import { useState, type ReactElement, type ReactNode } from 'react'
import { Icon } from './icons'

export interface OnboardingProps {
  personaName: string
  /** Triggers the system microphone prompt; resolves true when granted. */
  onRequestMicrophone: () => Promise<boolean>
  onDone: () => void
}

type MicState = 'idle' | 'asking' | 'granted' | 'denied'

const PROMISES = [
  'I only look at your screen while a session is on. A red light shows when I can.',
  'Nothing is saved. Your screen is never stored.',
  'Money, passwords and card numbers stay with you. I never read them out.',
  'You can press Stop at any time. I am an AI, not a person.',
]

export function Onboarding({ personaName, onRequestMicrophone, onDone }: OnboardingProps): ReactElement {
  const [step, setStep] = useState(0)
  const [mic, setMic] = useState<MicState>('idle')
  const last = 4

  const askMic = async (): Promise<void> => {
    setMic('asking')
    setMic((await onRequestMicrophone()) ? 'granted' : 'denied')
  }

  let body: ReactNode
  switch (step) {
    case 0:
      body = (
        <>
          <h2 className="al-h1">Hello. I am {personaName}.</h2>
          <p>I am an AI helper. I teach you to use your computer, one step at a time, and I step back as you learn.</p>
          <p className="al-muted">I draw on your screen to show you where to look. You do the clicking.</p>
        </>
      )
      break
    case 1:
      body = (
        <>
          <h2 className="al-h1">What I can see, and when</h2>
          <p>
            When you say <strong>{`“Hey ${personaName}”`}</strong>, I can see your screen and hear you until you say goodbye or press Stop.
          </p>
          <p className="al-muted">Before that, I only listen for my name. A light always shows which it is.</p>
        </>
      )
      break
    case 2:
      body = (
        <>
          <h2 className="al-h1">Let me hear you</h2>
          <p>Your computer will ask if I may use the microphone. Choose Allow.</p>
          {mic === 'granted' ? (
            <p className="al-banner" role="status">
              <span className="al-banner__icon">
                <Icon name="check" />
              </span>
              <span className="al-banner__text">The microphone is on. Thank you.</span>
            </p>
          ) : (
            <button type="button" className="al-btn al-btn--lg al-btn--primary" disabled={mic === 'asking'} onClick={() => void askMic()}>
              Allow the microphone
            </button>
          )}
          {mic === 'denied' ? <p className="al-note">It was not allowed. Open System Settings, then Privacy and Security, then Microphone, and turn Alongside on. You can carry on without it and type instead.</p> : null}
        </>
      )
      break
    case 3:
      body = (
        <>
          <h2 className="al-h1">Let me see your screen</h2>
          <p>Open System Settings, then Privacy and Security, then Screen Recording. Turn Alongside on.</p>
          <p className="al-note">Your computer will say Alongside needs to restart. Choose Quit and Reopen, then come back here.</p>
        </>
      )
      break
    default:
      body = (
        <>
          <h2 className="al-h1">Four promises</h2>
          <ul className="al-onboard__promises">
            {PROMISES.map((p) => (
              <li key={p}>
                <Icon name="shield" />
                <span>{p}</span>
              </li>
            ))}
          </ul>
        </>
      )
  }

  return (
    <div className="al-onboard">
      <div className="al-onboard__steps" role="img" aria-label={`Step ${step + 1} of ${last + 1}`}>
        {Array.from({ length: last + 1 }, (_, i) => (
          <span key={i} data-state={i < step ? 'done' : i === step ? 'now' : 'todo'} />
        ))}
      </div>
      {body}
      <div className="al-modal__choices">
        {step < last ? (
          <button type="button" className="al-btn al-btn--lg al-btn--primary" onClick={() => setStep(step + 1)}>
            {step === 0 ? 'Get started' : step === 2 && mic !== 'granted' ? 'Skip for now' : 'Next'}
          </button>
        ) : (
          <button type="button" className="al-btn al-btn--lg al-btn--primary" onClick={onDone}>
            {`Start with ${personaName}`}
          </button>
        )}
        {step > 0 ? (
          <button type="button" className="al-btn al-btn--quiet" onClick={() => setStep(step - 1)}>
            Back
          </button>
        ) : null}
      </div>
    </div>
  )
}
