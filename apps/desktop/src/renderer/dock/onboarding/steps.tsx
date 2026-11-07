// The nine screens. Each is presentational: it reads `answers`, calls `set` with the change, and says one thing.
import { useState, type ReactElement } from 'react'
import type { AlongsideApi } from '../../../shared/ipc'
import { PERSONA_LIST } from '../../../shared/personas'
import type { PersonaId } from '../../../shared/protocol'
import { PresenceOrb, Switch } from '../../design'
import { ChipGroup, Choice, Slider, TextField } from './controls'
import {
  AGENCY_CHOICES, COMFORT_LEVELS, cleanName, GLASS_MAX, GLASS_MIN, TEXT_SIZES, TOPICS, VOICE_SPEEDS, hotkeyLabel, toggleTopic, type Agency, type Answers, type Comfort, type Pacing, type Theme,
} from './flow'
import { GlassPreview, glassDescription } from './GlassPreview'
import { PermissionsStep, type PermissionsStepProps } from './PermissionsStep'

export interface StepProps {
  answers: Answers
  set: (patch: Partial<Answers>) => void
  personaName: string
  next: () => void
}

export function HelloStep({ personaName }: StepProps): ReactElement {
  return (
    <>
      <div className="ob-hero" aria-hidden="true">
        <PresenceOrb phase="live" size={88} />
      </div>
      <p className="ob-lede">This takes about two minutes. You can skip anything.</p>
      <p className="ob-hint">{personaName} is an AI helper, not a person.</p>
    </>
  )
}

export function AboutStep({ answers, set, next }: StepProps): ReactElement {
  return (
    <>
      <TextField label="What should I call you?" hint="Optional. Just your first name is fine." value={answers.userName} placeholder="Your name" autoComplete="given-name" onChange={(userName) => set({ userName })} onEnter={next} />
      <ChipGroup legend="What would you like help with?" hint="Pick any, or none." options={TOPICS.map((t) => ({ value: t.id, label: t.label }))} selected={answers.topics} onToggle={(id) => set({ topics: toggleTopic(answers.topics, id) })} />
    </>
  )
}

export function StyleStep({ answers, set }: StepProps): ReactElement {
  return (
    <>
      <Choice<number>
        legend="How comfortable are you with computers?"
        value={answers.comfort}
        options={COMFORT_LEVELS.map((c) => ({ value: c.value, title: c.label }))}
        onChange={(v) => set({ comfort: v as Comfort })}
      />
      <Choice<Pacing>
        legend="How should I help?"
        value={answers.pacing}
        options={[
          { value: 'gentle', title: 'Gentle and slow', line: 'One small step at a time.' },
          { value: 'fast', title: 'Quick and short', line: 'Just the next thing to do.' },
        ]}
        onChange={(pacing) => set({ pacing })}
      />
    </>
  )
}

export function ComfortStep({ answers, set }: StepProps): ReactElement {
  return (
    <>
      <div className="ob-sample" style={{ ['--ob-text-scale' as string]: String(answers.textScale) }}>
        <p>This is how words will look. Is it easy to read?</p>
      </div>
      <Choice<number> legend="Text size" layout="grid" snap value={answers.textScale} options={TEXT_SIZES.map((t) => ({ value: t.value, title: t.label }))} onChange={(textScale) => set({ textScale })} />
      <div className="ob-switches">
        <Switch label="Dyslexia-friendly font" hint="Letters that are easier to tell apart." checked={answers.dyslexiaFont} onChange={(dyslexiaFont) => set({ dyslexiaFont })} />
        <Switch label="High contrast" hint="Stronger black and white." checked={answers.highContrast} onChange={(highContrast) => set({ highContrast })} />
        <Switch label="Words instead of talking" hint="I write to you, and you can type back." checked={answers.textOnly} onChange={(textOnly) => set({ textOnly })} />
      </div>
      <Choice<number> legend="How fast I speak" layout="row" snap disabled={answers.textOnly} value={answers.voiceSpeed} options={VOICE_SPEEDS.map((v) => ({ value: v.value, title: v.label }))} onChange={(voiceSpeed) => set({ voiceSpeed })} />
    </>
  )
}

export function LookStep({ answers, set, personaName }: StepProps): ReactElement {
  // High contrast always wins: the dock stays solid so edges and text keep their full contrast.
  const glassActive = answers.glass && !answers.highContrast
  return (
    <>
      <GlassPreview glass={glassActive} opacity={answers.glassOpacity} personaName={personaName} />
      <Choice<Theme>
        legend="Colours"
        layout="row"
        value={answers.theme}
        options={[
          { value: 'system', title: 'Like my computer' },
          { value: 'light', title: 'Light' },
          { value: 'dark', title: 'Dark' },
        ]}
        onChange={(theme) => set({ theme })}
      />
      <Switch label="See-through window" hint={answers.highContrast ? 'Stays solid while High contrast is on.' : 'Lets your desktop show through.'} checked={answers.glass} onChange={(glass) => set({ glass })} />
      <Slider
        label="How solid"
        value={answers.glassOpacity}
        min={GLASS_MIN}
        max={GLASS_MAX}
        step={0.01}
        lowLabel="More see-through"
        highLabel="More solid"
        valueText={glassDescription(glassActive, answers.glassOpacity)}
        disabled={!answers.glass}
        onChange={(glassOpacity) => set({ glassOpacity })}
      />
    </>
  )
}

export function HelperStep({ answers, set }: StepProps): ReactElement {
  return (
    <>
      <p className="ob-lede">You can change this any time in Settings.</p>
      <Choice<PersonaId>
        legend="Who would you like?"
        value={answers.persona}
        options={PERSONA_LIST.map((p) => ({ value: p.id, title: p.displayName, line: p.styleBlurb, swatch: p.accentToken }))}
        onChange={(persona) => set({ persona })}
      />
    </>
  )
}

export function PermissionsScreen(props: PermissionsStepProps): ReactElement {
  return (
    <>
      <p className="ob-lede">I only look at your screen while you are talking to me. A red light shows when I can.</p>
      <PermissionsStep {...props} />
    </>
  )
}

// window.alongside is absent in the browser gallery, so the lookup stays optional.
const getFilesApi = (): AlongsideApi['files'] | undefined => (window.alongside as Partial<AlongsideApi> | undefined)?.files

export function HandsStep({ answers, set }: StepProps): ReactElement {
  const [note, setNote] = useState('')

  const toggleFiles = async (on: boolean): Promise<void> => {
    setNote('')
    if (!on) return set({ filesEnabled: false })
    const files = getFilesApi()
    if (!files) return setNote('You can choose folders later, in Settings.')
    try {
      const res = await files.addFolder()
      if (res.ok) set({ filesEnabled: true })
      else if (res.error) setNote(res.error)
    } catch {
      setNote('I could not open the folder picker. You can try again in Settings.')
    }
  }

  return (
    <>
      <p className="ob-lede">You are always in charge. Stop is one click away.</p>
      <Choice<Agency>
        legend="How much should I do for you?"
        value={answers.agency}
        options={AGENCY_CHOICES.map((c) => ({ value: c.value, title: c.title, line: c.line }))}
        onChange={(agency) => set({ agency })}
      />
      <p className="ob-hint">Money, passwords and sending messages always stay with you.</p>
      <div className="ob-files">
        <Switch label="Let me look at files I choose" hint="Off unless you turn it on." checked={answers.filesEnabled} onChange={(on) => void toggleFiles(on)} />
        <p className="ob-hint">To find things, short pieces of the files in folders you choose are sent to Google&rsquo;s Gemini to be indexed. Nothing else is read, and you can delete it all any time.</p>
        {note ? (
          <p className="ob-hint" role="status">
            {note}
          </p>
        ) : null}
      </div>
    </>
  )
}

export function ReadyStep({ answers, personaName }: StepProps): ReactElement {
  const hotkey = hotkeyLabel(typeof navigator === 'undefined' ? '' : navigator.platform)
  return (
    <>
      <dl className="ob-how">
        <div>
          <dt>Say</dt>
          <dd>&ldquo;Hey {personaName}&rdquo; whenever you want me.</dd>
        </div>
        <div>
          <dt>Or press</dt>
          <dd>{hotkey}</dd>
        </div>
        <div>
          <dt>Menu bar</dt>
          <dd>Find me at the top of your screen.</dd>
        </div>
        <div>
          <dt>Type instead</dt>
          <dd>Open Chat in this panel and write to me.</dd>
        </div>
      </dl>
      <p className="ob-hint">{answers.agency === 'off' ? 'I will show you how, and you do the clicking.' : 'I will always ask before I do anything for you.'}</p>
    </>
  )
}

export function titleFor(id: string, answers: Answers, personaName: string): string {
  switch (id) {
    case 'hello':
      return `Hello. I'm ${personaName}.`
    case 'about':
      return 'A little about you'
    case 'style':
      return 'How you like to learn'
    case 'comfort':
      return 'Make it comfortable'
    case 'look':
      return 'Look and feel'
    case 'helper':
      return 'Choose your helper'
    case 'permissions':
      return 'Let me hear and see'
    case 'hands':
      return 'How much should I do?'
    default:
      return cleanName(answers.userName) ? `You're all set, ${cleanName(answers.userName).split(' ')[0]}.` : "You're all set."
  }
}
