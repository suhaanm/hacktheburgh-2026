// Screenshot page for the dock (pill, chat, progress, settings) at its real 380 px width. Not shipped in the app build.
// Query: ?theme=light|dark&glass=1&dys=1&scale=1.5&hc=1. Reuses the gallery's stubs and canned chat.
import { createRoot } from 'react-dom/client'
import type { ReactElement } from 'react'
import { PERSONAS } from '../../shared/personas'
import type { CompanionState } from '../../shared/protocol'
import { DEFAULT_SETTINGS, type Settings } from '../../shared/settings'
import { Panel } from '../dock/Panel'
import { Pill } from '../dock/Pill'
import { ToastCard } from '../toast/ToastCard'
import '../toast/toast.css'
import { applyDesignSettings, AwarenessCard, Onboarding } from './index'
import type { AwarenessCardState } from '../../shared/awareness'
import './gallery'
import './styles'
import { APP_NAME } from '../../shared/brand'

const q = new URLSearchParams(location.search)
const settings: Settings = {
  ...DEFAULT_SETTINGS,
  persona: 'understudy',
  theme: q.get('theme') === 'dark' ? 'dark' : 'light',
  glass: q.get('glass') !== '0',
  glassOpacity: Number(q.get('opacity') ?? 0.6),
  dyslexiaFont: q.get('dys') === '1',
  highContrast: q.get('hc') === '1',
  textScale: Number(q.get('scale') ?? 1),
}
// The imported gallery applies its own settings after mount; re-apply ours a few times so the query wins.
const apply = (): void => applyDesignSettings(settings, 'understudy', document.documentElement, { glassSupported: q.get('glass') !== '0' })
apply()
for (const ms of [30, 150, 400, 900, 1600]) setTimeout(apply, ms)
const now = Date.now()
const cardOff: AwarenessCardState = { available: true, consentText: `${APP_NAME} can take a quick look at your screen when you seem stuck, when you press its shortcut and, only if you turn it on, about every 30 seconds. Each look sends one small, reduced picture of your screen to a cloud vision model, which tells it what kind of app you are in and what seems to be in the way. The picture leaves this Mac for that one call, is held in memory only, and is never saved by ${APP_NAME}; what comes back is a few fixed labels, not text. Nothing is sent while a password manager or banking app is in front, while a password field has focus, while your screen is locked or shared, or while you are away.`, consentShort: 'Look at my screen when I seem stuck. Nothing is saved. See every call in Privacy.', agreed: false, enabled: false, trigger: false, periodic: false, strict: true, intervalSec: 30, dailyUsd: 0.5, callsToday: 0, lastSkip: null }
const cardOn: AwarenessCardState = { ...cardOff, agreed: true, enabled: true, trigger: true, periodic: false, callsToday: 3, lastSkip: 'secure_input' }
// The panel's Settings tab hosts the card through window.alongside.awareness; the harness answers with the canned (off) state.
;(window as unknown as { alongside?: Record<string, unknown> }).alongside = { ...((window as unknown as { alongside?: Record<string, unknown> }).alongside ?? {}), awareness: { state: async () => cardOff, setConsent: async () => cardOn } }
const name = PERSONAS.understudy.displayName
const st = (over: Partial<CompanionState>): CompanionState => ({
  persona: 'understudy', phase: 'live', micMuted: false, level: 2, levelLocked: false, captions: [], agents: [], settings, ...over,
})
const noop = (): void => undefined
const panel = (tab: 'chat' | 'progress' | 'settings' | 'profile', over: Partial<CompanionState> = {}): ReactElement => (
  <div className="al-app al-dock al-dock--fill shot-win" style={{ height: 580 }}>
    <Panel state={st({ skill: { id: 'bigger_text', name: 'Make the text bigger', step: 2, stepCount: 4 }, ...over })} settings={settings} personaName={name} tab={tab} onTab={noop} onCollapse={noop} onStop={noop} onToggleMute={noop} onWake={noop} onCancelAgent={noop} onSettings={noop} onSetUpAgain={noop} />
  </div>
)
const pill = (over: Partial<CompanionState>): ReactElement => (
  <div className="al-app al-dock al-dock--fill shot-win" style={{ width: 320, height: 64 }}>
    <Pill state={st(over)} personaName={name} onExpand={noop} onStop={noop} />
  </div>
)

const css = document.createElement('style')
css.textContent = `
  body { margin: 0; background: ${q.get('glass') === '1' ? 'linear-gradient(150deg, #5d7ba6 0%, #8a5da6 55%, #d6935a 100%)' : 'var(--bg)'}; min-height: 100vh; }
  #shots { display: flex; flex-wrap: wrap; gap: 24px; padding: 24px 16px; align-items: flex-start; box-sizing: border-box; width: 100%; max-width: 1700px; }
  .shot-win { max-width: 100%; }
  .shot-toast { width: 360px; max-width: 100%; }
  .shot-win { width: 360px; position: relative; }
  .shot-pills { display: flex; flex-direction: column; gap: 14px; width: 100%; flex-basis: 100%; }
  .shot-pills > div { display: flex; gap: 14px; }
`
document.head.append(css)
createRoot(document.getElementById('shots') as HTMLElement).render(
  <>
    <div className="shot-pills">
      <div>
        {pill({ phase: 'listening_for_name' })}
        {pill({ phase: 'live' })}
        {pill({ phase: 'speaking', level: 3 })}
        {pill({ phase: 'live', micMuted: true })}
      </div>
    </div>
    <div className="shot-toast">
      <ToastCard request={{ id: 't1', question: `${APP_NAME} wants to open the case note in your browser. Is that all right?`, options: ['Yes, open it', 'Not now'] }} remaining={0.6} armed onAnswer={noop} />
    </div>
    {panel('chat')}
    {panel('progress')}
    {panel('settings')}
    {panel('profile')}
    <div className="al-app al-dock shot-win" style={{ padding: 16 }}><AwarenessCard state={cardOff} onChoose={noop} /></div>
    <div className="al-app al-dock shot-win" style={{ padding: 16 }}><AwarenessCard state={cardOn} onChoose={noop} /></div>
    <div className="al-app al-dock shot-win" style={{ padding: 16 }}><Onboarding personaName={name} onRequestMicrophone={() => Promise.resolve(true)} onDone={noop} /></div>
  </>,
)
