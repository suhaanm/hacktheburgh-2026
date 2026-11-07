import type { ReactElement } from 'react'
import type { CompanionState } from '../../shared/protocol'
import type { Settings, SettingsPatch } from '../../shared/settings'
import { PERSONA_LIST } from '../../shared/personas'
import { Icon, ListeningLight, MuteButton, PHASE_LABELS, PresenceOrb, ProgressView, SettingsPanel, StopButton } from '../design'
import { ChatTab } from './ChatTab'
import { sessionActive, useProgressData, useScreenBlocked, useShowtimeActive } from './hooks'
import { MoreExtras } from './MoreExtras'
import { ProfileTab } from './ProfileTab'

export type DockTab = 'chat' | 'progress' | 'profile' | 'settings'
// "About you" (profile) is one tap inside Settings, so the bar stays at three calm choices.
const TABS: readonly { id: DockTab; label: string }[] = [
  { id: 'chat', label: 'Chat' },
  { id: 'progress', label: 'Progress' },
  { id: 'settings', label: 'Settings' },
]
const PERSONA_OPTIONS = PERSONA_LIST.map((p) => ({ id: p.id, name: p.displayName }))

export interface PanelProps {
  state: CompanionState
  settings: Settings
  personaName: string
  tab: DockTab
  onTab: (tab: DockTab) => void
  onCollapse: () => void
  onStop: () => void
  onToggleMute: () => void
  onWake: () => void
  onCancelAgent: (id: string) => void
  onSettings: (patch: SettingsPatch) => void
  onSetUpAgain: () => void
  /** FILES' section, mounted inside "More settings" when it exists. */
  files?: ReactElement
}

/** Expanded dock: a quiet header, four tabs, and a footer with the listening light and Stop that never goes away. */
export function Panel(props: PanelProps): ReactElement {
  const { state, settings, personaName, tab, onTab } = props
  const progress = useProgressData(tab === 'progress', settings.demoMode)
  const screenBlocked = useScreenBlocked()
  const demoActive = useShowtimeActive()
  const stoppable = sessionActive(state.phase) || demoActive

  return (
    <>
      <div className="al-dock__head al-drag">
        <div className="al-dock__headrow">
          <PresenceOrb phase={state.phase} size={32} personaName={personaName} />
          <div className="al-pill__who al-dock__who">
            <span className="al-pill__name">{personaName}</span>
            {state.phase === 'error' ? <span className="al-pill__phase">{PHASE_LABELS.error}</span> : null}
          </div>
          <MuteButton muted={state.micMuted} onToggle={props.onToggleMute} />
          <button type="button" className="al-btn al-btn--quiet" aria-label="Collapse the panel" onClick={props.onCollapse}>
            <Icon name="up" />
          </button>
        </div>
      </div>

      <div className="al-tabs" role="tablist" aria-label="Sections">
        {TABS.map((t) => (
          <button key={t.id} type="button" role="tab" id={`al-tab-${t.id}`} aria-selected={tab === t.id || (t.id === 'settings' && tab === 'profile')} aria-controls="al-tabpanel" className="al-tab" onClick={() => onTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>
      <div className={`al-dock__body${tab === 'chat' ? ' al-dock__body--chat' : ''}`} role="tabpanel" id="al-tabpanel" aria-labelledby={`al-tab-${tab}`}>
        {tab === 'chat' ? <ChatTab state={state} personaName={personaName} onWake={props.onWake} onCancelAgent={props.onCancelAgent} /> : null}
        {tab === 'progress' ? <ProgressView data={progress} /> : null}
        {tab === 'profile' ? (
          <button type="button" className="al-btn al-btn--quiet al-back" onClick={() => onTab('settings')}>
            <Icon name="up" /> Settings
          </button>
        ) : null}
        {tab === 'profile' ? <ProfileTab carerSharing={settings.carerSharing} onCarerSharing={(carerSharing) => props.onSettings({ carerSharing })} /> : null}
        {tab === 'settings' ? (
          <button type="button" className="al-row-link" onClick={() => onTab('profile')}>
            <span>About you</span>
            <Icon name="down" />
          </button>
        ) : null}
        {tab === 'settings' ? <SettingsPanel settings={settings} onChange={props.onSettings} personas={PERSONA_OPTIONS} more={<MoreExtras onSetUpAgain={props.onSetUpAgain} files={props.files} />} /> : null}
      </div>

      {settings.listeningLight || stoppable ? (
      <div className="al-dock__foot">
        {settings.listeningLight ? <ListeningLight phase={state.phase} muted={state.micMuted} personaName={personaName} screenBlocked={screenBlocked} onFixScreen={() => window.alongside.permissions.openSettings('screen')} /> : <span style={{ flex: 1 }} />}
        {stoppable ? <StopButton onStop={props.onStop} /> : null}
      </div>
      ) : null}
    </>
  )
}
