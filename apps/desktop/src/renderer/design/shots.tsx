// Screenshot page for the dock (pill, chat, progress, settings) at its real 380 px width. Not shipped in the app build.
// Query: ?theme=light|dark&glass=1&dys=1&scale=1.5&hc=1. Reuses the gallery's stubs and canned chat.
import { createRoot } from 'react-dom/client'
import type { ReactElement } from 'react'
import { PERSONAS } from '../../shared/personas'
import type { CompanionState } from '../../shared/protocol'
import { DEFAULT_SETTINGS, type Settings } from '../../shared/settings'
import { Panel } from '../dock/Panel'
import { Pill } from '../dock/Pill'
import { applyDesignSettings } from './index'
import './gallery'
import './styles'

const q = new URLSearchParams(location.search)
const settings: Settings = {
  ...DEFAULT_SETTINGS,
  persona: 'marcus',
  theme: q.get('theme') === 'dark' ? 'dark' : 'light',
  glass: q.get('glass') !== '0',
  glassOpacity: Number(q.get('opacity') ?? 0.6),
  dyslexiaFont: q.get('dys') === '1',
  highContrast: q.get('hc') === '1',
  textScale: Number(q.get('scale') ?? 1),
}
// The imported gallery applies its own settings after mount; re-apply ours a few times so the query wins.
const apply = (): void => applyDesignSettings(settings, 'marcus', document.documentElement, { glassSupported: true })
apply()
for (const ms of [30, 150, 400, 900, 1600]) setTimeout(apply, ms)
const now = Date.now()
const name = PERSONAS.marcus.displayName
const st = (over: Partial<CompanionState>): CompanionState => ({
  persona: 'marcus', phase: 'live', micMuted: false, level: 2, levelLocked: false, captions: [], agents: [], settings, ...over,
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
  body { margin: 0; background: linear-gradient(150deg, #5d7ba6 0%, #8a5da6 55%, #d6935a 100%); min-height: 100vh; }
  #shots { display: flex; flex-wrap: wrap; gap: 24px; padding: 28px; align-items: flex-start; width: 1700px; }
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
    {panel('chat')}
    {panel('progress')}
    {panel('settings')}
    {panel('profile')}
  </>,
)
