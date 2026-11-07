// Review page for every design component in every state. Not shipped in the app build.
import { useEffect, useState, type ReactElement, type ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import { PERSONA_LIST } from '../../shared/personas'
import { PERSONAS } from '../../shared/personas'
import type { AgentChip, AttemptRecord, CaptionLine, CompanionState, HelpLevel, LearnerSnapshot, Phase, PersonaId } from '../../shared/protocol'
import { DEFAULT_SETTINGS, type Settings } from '../../shared/settings'
import type { AlongsideApi } from '../../shared/ipc'
import { buildProgress } from '../../main/teaching/progress'
import { Panel, type DockTab } from '../dock/Panel'
import { ProfileTab } from '../dock/ProfileTab'
import { chatBus } from '../dock/chat/bus'
import { Pill } from '../dock/Pill'
import {
  AgentTray, Captions, ConfirmModal, ErrorBanner, LevelChip, ListeningLight, MuteButton, Onboarding, PHASE_LABELS, PresenceOrb, ProgressView,
  Segmented, SettingsPanel, SkillStepper, StopButton, Switch, applyDesignSettings, followSystemTheme, listeningLightState,
} from './index'
import './styles'

const now = Date.now()
const day = 86_400_000
const attempts: AttemptRecord[] = [6, 5, 5, 3, 3, 2, 1, 0].map((hints, i) => ({
  id: `a${i}`, skillId: 'video_call', lessonId: 'l', startedAt: now - (8 - i) * day, endedAt: now - (8 - i) * day + 60_000, levelAtStart: 2, levelAtEnd: 2,
  completed: true, hintsUsed: hints, errors: 0, stalls: 0, safetyFlag: false, anxietyPhrase: false, teachBackScore: 0.8, confidence: 3, clean: hints < 3,
}))
const snapshot: LearnerSnapshot = {
  skills: {
    video_call: { level: 4, streakClean: 3, lastSeen: now - day, nextReview: now + 3 * day },
    spot_scam: { level: 2, streakClean: 1, lastSeen: now - 2 * day, nextReview: null },
    bigger_text: { level: 1, streakClean: 0, lastSeen: null, nextReview: null },
  },
  confidenceLog: [2, 2, 3, 3, 3, 4, 4, 5].map((rating, i) => ({ at: now - (8 - i) * day, skillId: 'video_call' as const, rating })),
  attempts, whatWorks: [], avoidJargon: [], doneForMe: { video_call: 2 },
}
const emptySnapshot: LearnerSnapshot = { ...snapshot, skills: { video_call: { level: 1, streakClean: 0, lastSeen: null, nextReview: null }, spot_scam: { level: 1, streakClean: 0, lastSeen: null, nextReview: null }, bigger_text: { level: 1, streakClean: 0, lastSeen: null, nextReview: null } }, confidenceLog: [], attempts: [], doneForMe: {} }

// Panel's progress and profile tabs talk to main through the preload API; the gallery stands in for it.
const profileSeed = `# My Alongside profile

> This file is yours. Read it, change it, or delete any line and Alongside will follow what it says here.

## About me & accessibility

- Call me Peggy
- I find small text hard to read

## Goals

- See my granddaughter Lily on a video call
- Send photos to my son

## Skills

| Skill | Level |
|---|---|
| Start a video call | 2 |

## What works for me

- Comparing the contacts list to a phone book helped
- Being asked what I would try before being told

## Jargon to avoid

- browser, URL, swipe

## Who can see what

- Nobody sees anything unless you switch on carer sharing in Settings.

## Last session

- yesterday \u00b7 Start a video call \u00b7 Found the green Start call button with one hint.
`
const fakeFile = { content: profileSeed, revision: 1, stale: false }
const fakeMarkdown: AlongsideApi['learnerMarkdown'] = (req) => {
  const result = (ok: boolean, conflict?: boolean) => ({ ok, conflict, content: fakeFile.content, revision: `r${fakeFile.revision}` })
  if (req.op === 'read') return Promise.resolve(result(true))
  if (fakeFile.stale) {
    // Someone else changed the file after the learner's last read: reject, hand back the latest.
    fakeFile.stale = false
    fakeFile.content += '\n- (changed elsewhere)'
    fakeFile.revision += 1
    return Promise.resolve(result(false, true))
  }
  if (req.revision !== `r${fakeFile.revision}`) return Promise.resolve(result(false, true))
  fakeFile.content = req.content ?? fakeFile.content
  fakeFile.revision += 1
  return Promise.resolve(result(true))
}
;(window as unknown as { alongside: Partial<AlongsideApi> }).alongside = { learnerSnapshot: () => Promise.resolve(snapshot), learnerMarkdown: fakeMarkdown }

const captions: CaptionLine[] = [
  { id: '1', speaker: 'user', text: 'How do I make the writing bigger?', final: true, at: now },
  { id: '2', speaker: 'assistant', text: 'Let’s do it together. Look for the gear icon.', final: true, at: now },
  { id: '3', speaker: 'assistant', text: 'It is in the top right corner of', final: false, at: now },
]

const agents: AgentChip[] = [
  {
    id: 'a1', kind: 'scam_check', title: 'Checking the text from “Royal Post”', status: 'done', startedAt: now, summary: 'This looks like a scam. I found 3 warning signs.',
    result: { kind: 'scam_check', report: { verdict: 'likely_scam', confidence: 0.9, redFlags: [{ phrase: 'within 24 hours', why: 'Real services don’t rush you.' }, { phrase: 'pay a £1.50 fee', why: 'Small fees are a common way in.' }], advice: ['Don’t tap the link.'], humanHelp: 'Use the official app, or call the number on your card.', models: [], latencyMs: 1 } },
  },
  { id: 'a2', kind: 'lookup', title: 'Looking up how to turn on subtitles', status: 'running', startedAt: now },
  { id: 'a3', kind: 'lesson_summary', title: 'Writing your lesson summary', status: 'error', startedAt: now, summary: 'I couldn’t reach the internet. Your progress is saved.' },
  { id: 'a4', kind: 'lookup', title: 'Looking up the bank opening hours', status: 'cancelled', startedAt: now },
]

// Seed the shared chat bus and answer typed turns with a canned echo, standing in for LIVE's transport.
chatBus.push({ id: 'u1', role: 'user', text: 'How do I make the writing bigger?', final: true, at: now, via: 'voice' })
chatBus.push({ id: 'a1', role: 'assistant', text: 'Let\u2019s do it together. Look for the gear icon in the top right.', final: true, at: now, via: 'voice' })
let echoN = 0
chatBus.onSend(() => {
  const id = `a-echo-${echoN++}`
  setTimeout(() => chatBus.push({ id, role: 'assistant', text: 'Sure. Take your time, I am here.', final: false, at: Date.now(), via: 'typed' }), 400)
  setTimeout(() => chatBus.push({ id, role: 'assistant', text: 'Sure. Take your time, I am here.', final: true, at: Date.now(), via: 'typed' }), 1200)
})

const PHASES: Phase[] = ['asleep', 'listening_for_name', 'connecting', 'live', 'speaking', 'thinking', 'error']

function baseState(over: Partial<CompanionState>, settings: Settings): CompanionState {
  return { persona: settings.persona, phase: 'live', micMuted: false, level: 2, levelLocked: false, captions, agents: [], settings, ...over }
}

function Specimen({ title, children, wide }: { title: string; children: ReactNode; wide?: boolean }): ReactElement {
  return (
    <section className="gl-spec" style={wide ? { gridColumn: '1 / -1' } : undefined}>
      <h2 className="al-eyebrow">{title}</h2>
      {children}
    </section>
  )
}

function Gallery(): ReactElement {
  const [dark, setDark] = useState(false)
  const [settings, setSettings] = useState<Settings>({ ...DEFAULT_SETTINGS, persona: 'marcus' })
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [answer, setAnswer] = useState('')
  const [level, setLevel] = useState<HelpLevel>(2)
  const [tab, setTab] = useState<DockTab>('chat')
  const [empty, setEmpty] = useState(false)
  const persona: PersonaId = settings.persona ?? 'marcus'
  const name = PERSONAS[persona].displayName
  const patch = (p: Partial<Settings>): void => setSettings((s) => ({ ...s, ...p }))

  useEffect(() => {
    patch({ theme: dark ? 'dark' : 'light' })
  }, [dark])
  useEffect(() => applyDesignSettings(settings, persona, document.documentElement, { glassSupported: true }), [settings.bigAnnotations, settings.highContrast, settings.dyslexiaFont, settings.glass, settings.glassOpacity, settings.textScale, persona]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    window.alongside.learnerSnapshot = () => Promise.resolve(empty ? emptySnapshot : snapshot)
  }, [empty])

  const noop = (): void => undefined
  return (
    <div className="al-app gl">
      <header className="gl-bar">
        <strong>Alongside design gallery</strong>
        <div className="gl-bar__row">
          <Segmented label="Theme" value={dark ? 'dark' : 'light'} onChange={(v) => setDark(v === 'dark')} options={[{ value: 'light', label: 'Light' }, { value: 'dark', label: 'Dark' }]} />
          <Segmented label="Companion" value={persona} onChange={(p) => patch({ persona: p })} options={PERSONA_LIST.map((p) => ({ value: p.id, label: p.displayName }))} />
        </div>
        <div className="gl-bar__row">
          <Switch label="High contrast" checked={settings.highContrast} onChange={(v) => patch({ highContrast: v })} />
          <Switch label="Big marks (also scales the UI)" checked={settings.bigAnnotations} onChange={(v) => patch({ bigAnnotations: v })} />
          <Switch label="Dyslexia font" checked={settings.dyslexiaFont} onChange={(v) => patch({ dyslexiaFont: v })} />
          <Switch label="Glass" checked={settings.glass} onChange={(v) => patch({ glass: v })} />
          <Switch label="Empty progress" checked={empty} onChange={setEmpty} />
        </div>
      </header>

      <main className="gl-grid">
        <Specimen title="PresenceOrb: every phase" wide>
          <div className="gl-row">
            {PHASES.map((p) => (
              <figure key={p} className="gl-fig"><PresenceOrb phase={p} size={84} personaName={name} /><figcaption>{PHASE_LABELS[p]}</figcaption></figure>
            ))}
          </div>
        </Specimen>

        <Specimen title="LevelChip: hero, default, compact, locked" wide>
          <div className="gl-row">
            {([1, 2, 3, 4] as HelpLevel[]).map((l) => <button key={l} type="button" className="al-btn" aria-pressed={level === l} onClick={() => setLevel(l)}>Go to {l}</button>)}
          </div>
          <LevelChip level={level} variant="hero" />
          <div className="gl-row">
            <LevelChip level={level} />
            <LevelChip level={level} locked />
            <LevelChip level={level} variant="compact" />
          </div>
          <div className="gl-row">{([1, 2, 3, 4] as HelpLevel[]).map((l) => <LevelChip key={l} level={l} />)}</div>
        </Specimen>

        <Specimen title="ListeningLight and mute">
          <div className="gl-col">
            {PHASES.slice(0, 4).map((p) => <ListeningLight key={p} phase={p} muted={false} personaName={name} />)}
            <ListeningLight phase="live" muted personaName={name} />
            <div className="gl-row"><MuteButton muted={false} onToggle={noop} /><MuteButton muted onToggle={noop} /></div>
            <div className="gl-row">{(['asleep', 'listening_for_name', 'live'] as Phase[]).map((p) => <PresenceOrb key={p} phase={p} size={48} light={listeningLightState(p, false)} personaName={name} />)}</div>
          </div>
        </Specimen>

        <Specimen title="StopButton, SkillStepper, ErrorBanner">
          <div className="gl-col">
            <div className="gl-row"><StopButton onStop={noop} /><StopButton compact onStop={noop} /></div>
            <SkillStepper name="Make the text bigger" step={1} stepCount={4} />
            <SkillStepper name="Start a video call" step={3} stepCount={5} />
            <ErrorBanner title="I lost the connection." message="Your lesson is saved. Check the internet and try again." actionLabel="Try again" onAction={noop} />
          </div>
        </Specimen>

        <Specimen title="Captions (final, in progress, system)">
          <Captions lines={[...captions, { id: '4', speaker: 'system', text: 'Captions are on. You can turn them off in Settings.', final: true, at: now }]} personaName={name} max={4} />
        </Specimen>

        <Specimen title="AgentTray: done, running, error, stopped">
          <AgentTray agents={agents} onCancel={noop} />
        </Specimen>

        <Specimen title="ConfirmModal (real click only)">
          <div className="gl-frame">
            <button type="button" className="al-btn al-btn--primary" onClick={() => { setAnswer(''); setConfirmOpen(true) }}>Show the question</button>
            <p role="status">{answer}</p>
            {confirmOpen ? <ConfirmModal personaName={name} request={{ id: 'c1', question: 'May I click the green “Send” button for you?', options: ['Yes, go ahead', 'No, leave it'] }} onAnswer={(c) => { setAnswer(`You chose: ${c}`); setConfirmOpen(false) }} /> : null}
          </div>
        </Specimen>

        <Specimen title="Onboarding">
          <div className="gl-card"><Onboarding personaName={name} onRequestMicrophone={() => Promise.resolve(true)} onDone={noop} /></div>
        </Specimen>

        <Specimen title="ProgressView">
          <div className="gl-card"><ProgressView data={buildProgress(empty ? emptySnapshot : snapshot, { now: Date.now() })} /></div>
        </Specimen>

        <Specimen title="SettingsPanel">
          <div className="gl-card"><SettingsPanel settings={settings} onChange={patch} personas={PERSONA_LIST.map((p) => ({ id: p.id, name: p.displayName }))} /></div>
        </Specimen>

        <Specimen title="ProfileTab (What I know about you)">
          <div className="al-dock gl-dock gl-profile">
            <div className="al-dock__body"><ProfileTab carerSharing={settings.carerSharing} onCarerSharing={(v) => patch({ carerSharing: v })} /></div>
          </div>
          <button type="button" className="al-btn" onClick={() => { fakeFile.stale = true }}>Make the next save fail as stale</button>
        </Specimen>

        <Specimen title="Dock: collapsed pill in every phase" wide>
          <div className="gl-col gl-pills">
            {PHASES.map((p) => (
              <div key={p} className="al-dock gl-dock"><Pill state={baseState({ phase: p, level }, settings)} personaName={name} onExpand={noop} onStop={noop} /></div>
            ))}
            <div className="al-dock gl-dock"><Pill state={baseState({ levelLocked: true }, settings)} personaName={name} onExpand={noop} onStop={noop} /></div>
            <div className="al-dock gl-dock"><Pill state={baseState({ micMuted: true }, settings)} personaName={name} onExpand={noop} onStop={noop} /></div>
          </div>
        </Specimen>

        <Specimen title="Dock: expanded panel (chat, with a canned reply to typed messages)" wide>
          <div className="gl-row gl-panels gl-stage">
            {(['live', 'speaking', 'asleep', 'error'] as Phase[]).map((p) => (
              <div key={p} className="al-dock al-dock--panel gl-dock">
                <Panel
                  state={baseState({ phase: p, level, agents: p === 'live' ? agents.slice(0, 2) : [], skill: p === 'live' || p === 'speaking' ? { id: 'bigger_text', name: 'Make the text bigger', step: 2, stepCount: 4 } : undefined, lastError: p === 'error' ? 'I could not reach the internet.' : undefined, captions: p === 'asleep' ? [] : captions }, settings)}
                  settings={settings} personaName={name} tab={tab} onTab={setTab} onCollapse={noop} onStop={noop} onToggleMute={noop} onWake={noop}
                  onCancelAgent={noop} onSettings={patch} onSetUpAgain={noop}
                />
              </div>
            ))}
          </div>
        </Specimen>
      </main>
    </div>
  )
}

followSystemTheme()
const style = document.createElement('style')
style.textContent = `
  body { margin: 0; background: var(--bg); }
  .gl { min-height: 100vh; padding: 0 16px 64px; }
  .gl-bar { position: sticky; top: 0; z-index: 30; display: flex; flex-direction: column; gap: 8px; margin: 0 -16px; padding: 12px 16px; background: var(--surface); border-bottom: 1.5px solid var(--line-strong); }
  .gl-bar__row { display: flex; flex-wrap: wrap; gap: 4px 24px; align-items: center; }
  .gl-bar__row .al-switch { min-height: 48px; padding: 4px 0; }
  .gl-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 380px), 1fr)); gap: 24px; padding-top: 24px; align-items: start; }
  .gl-spec { display: flex; flex-direction: column; gap: 12px; min-width: 0; padding: 16px; border: 1.5px solid var(--line); border-radius: 22px; background: var(--bg); }
  .gl-row { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; }
  .gl-col { display: flex; flex-direction: column; gap: 12px; align-items: flex-start; }
  .gl-col > * { max-width: 100%; }
  .gl-fig { margin: 0; display: grid; justify-items: center; gap: 8px; width: 130px; text-align: center; font-size: var(--fs-sm); }
  .gl-card { padding: 16px; border: 1.5px solid var(--line); border-radius: 22px; background: var(--surface); }
  .gl-frame { position: relative; min-height: 340px; display: grid; place-content: start; gap: 12px; padding: 16px; border: 1.5px dashed var(--line-strong); border-radius: 22px; overflow: hidden; }
  .gl-dock { position: relative; width: 360px; max-width: 100%; }
  .gl-panels .al-dock--panel { height: 640px; }
  .gl-stage { padding: 20px; border-radius: 22px; background: linear-gradient(150deg, #5d7ba6 0%, #8a5da6 55%, #d6935a 100%); }
  .gl-profile { height: 720px; display: flex; flex-direction: column; }
  .gl-profile .al-dock__body { flex: 1; }
  .gl-pills { flex-direction: row; flex-wrap: wrap; }
`
document.head.append(style)
createRoot(document.getElementById('root') as HTMLElement).render(<Gallery />)
