import { useState, type ReactElement, type ReactNode } from 'react'
import type { HelpLevel, PersonaId } from '../../shared/protocol'
import type { Settings, SettingsPatch } from '../../shared/settings'
import { annotationStyle, strokeLayers } from './annotation-style'
import { LEVEL_NAMES } from './levels'
import { Icon } from './icons'
import { Segmented, Switch } from './Switch'

export interface SettingsPanelProps {
  settings: Settings
  onChange: (patch: SettingsPatch) => void
  personas: readonly { id: PersonaId; name: string }[]
  /** Extra rows at the end of "More settings" (files, demo, set up again). */
  more?: ReactNode
}

function Group({ title, children }: { title: string; children: ReactNode }): ReactElement {
  return (
    <section className="al-group" aria-label={title}>
      <h3 className="al-eyebrow">{title}</h3>
      {children}
    </section>
  )
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }): ReactElement {
  return (
    <div className="al-setrow">
      <span className="al-setrow__label">{label}</span>
      {children}
      {hint ? <span className="al-small">{hint}</span> : null}
    </div>
  )
}

/** What marks on the user's screen will look like with the current settings. */
export function AnnotationPreview({ settings }: { settings: Pick<Settings, 'bigAnnotations' | 'highContrast' | 'dyslexiaFont'> }): ReactElement {
  const st = annotationStyle(settings)
  const tone = 'guide'
  const ring = { x: 22, y: 40, w: 126, h: 60 }
  const rx = Math.min(st.ring.radius, ring.h / 2)
  const layers = strokeLayers(st, tone)
  const core = st.tones[tone]
  const arrow = `M270 120 Q 227 110 186 92`
  return (
    <div className="al-preview">
      <svg viewBox="0 0 320 150" role="img" aria-label="What on-screen marks will look like with these settings">
        <rect x="30" y="48" width="110" height="44" rx="10" fill="#e8ecf3" />
        <text x="85" y="76" textAnchor="middle" fontSize="18" fontWeight="700" fill="#1d2330" fontFamily="system-ui">
          Send
        </text>
        {layers.map((l, i) => (
          <rect key={i} x={ring.x} y={ring.y} width={ring.w} height={ring.h} rx={rx} fill="none" stroke={l.color} strokeWidth={l.width} strokeOpacity={l.opacity} />
        ))}
        {layers.map((l, i) => (
          <path key={i} d={arrow} fill="none" stroke={l.color} strokeWidth={l.width} strokeOpacity={l.opacity} strokeLinecap="round" />
        ))}
        <polygon points="172,86 192,84 182,102" fill={core.core} stroke={core.casing} strokeWidth={st.stroke.core * 0.6} strokeLinejoin="round" />
        <circle cx={ring.x + 4} cy={ring.y + 2} r={st.badge.diameter / 2} fill={core.core} stroke={core.casing} strokeWidth={st.stroke.core * 0.5} />
        <text x={ring.x + 4} y={ring.y + 2 + st.badge.fontSize * 0.36} textAnchor="middle" fontSize={st.badge.fontSize} fontWeight="700" fill={core.onCore} fontFamily={st.badge.fontFamily}>
          1
        </text>
      </svg>
    </div>
  )
}

export function SettingsPanel({ settings, onChange, personas, more }: SettingsPanelProps): ReactElement {
  const [moreOpen, setMoreOpen] = useState(false)
  const toggle = (key: keyof Settings) => (checked: boolean) => onChange({ [key]: checked })
  const levels: HelpLevel[] = [1, 2, 3, 4]
  return (
    <div className="al-settings">
      <Group title="Basics">
        <Field label="Companion">
          <Segmented label="Companion" value={settings.persona ?? personas[0]?.id ?? 'marcus'} onChange={(persona) => onChange({ persona })} options={personas.map((p) => ({ value: p.id, label: p.name }))} />
        </Field>
        <Field label="Text size">
          <div className="al-rangewrap">
            <span aria-hidden="true">Smaller</span>
            <input className="al-range" type="range" min={0.9} max={1.5} step={0.05} value={settings.textScale} aria-label="Text size" onChange={(e) => onChange({ textScale: Number(e.target.value) })} />
            <span aria-hidden="true">Larger</span>
          </div>
        </Field>
        <Switch label="Keep the panel open" hint="Off hides it until you ask, from the menu bar" checked={settings.showDock} onChange={toggle('showDock')} />
        <Switch label="Easier-to-read font" hint="OpenDyslexic" checked={settings.dyslexiaFont} onChange={toggle('dyslexiaFont')} />
        <Field label="Theme">
          <Segmented
            label="Theme"
            value={settings.theme}
            onChange={(theme) => onChange({ theme })}
            options={[
              { value: 'system', label: 'Auto' },
              { value: 'light', label: 'Light' },
              { value: 'dark', label: 'Dark' },
            ]}
          />
        </Field>
        <Switch label="Glass look" checked={settings.glass && !settings.highContrast} onChange={toggle('glass')} disabled={settings.highContrast} />
        {settings.glass && !settings.highContrast ? (
          <Field label="See-through">
            <div className="al-rangewrap">
              <span aria-hidden="true">More</span>
              <input className="al-range" type="range" min={0.35} max={1} step={0.05} value={settings.glassOpacity} aria-label="How see-through the glass is" onChange={(e) => onChange({ glassOpacity: Number(e.target.value) })} />
              <span aria-hidden="true">Less</span>
            </div>
          </Field>
        ) : null}
        <Switch label="Captions" checked={settings.captions} onChange={toggle('captions')} />
        <Switch label="High contrast" checked={settings.highContrast} onChange={toggle('highContrast')} />
      </Group>

      <button type="button" className="al-btn al-more" aria-expanded={moreOpen} aria-controls="al-more-settings" onClick={() => setMoreOpen((v) => !v)}>
        {moreOpen ? 'Fewer settings' : 'More settings'}
        <Icon name="down" />
      </button>

      {moreOpen ? (
        <div id="al-more-settings" className="al-settings">
          <Group title="Help">
            <Field label="Help level">
              <Segmented
                label="Help level mode"
                value={settings.helpLevelMode}
                onChange={(helpLevelMode) => onChange({ helpLevelMode })}
                options={[
                  { value: 'auto', label: 'Adjust for me' },
                  { value: 'locked', label: 'Keep it fixed' },
                ]}
              />
            </Field>
            {settings.helpLevelMode === 'locked' ? (
              <Field label="Keep me at">
                <Segmented label="Help level to keep" value={settings.lockedLevel} onChange={(lockedLevel) => onChange({ lockedLevel })} options={levels.map((l) => ({ value: l, label: LEVEL_NAMES[l] }))} />
              </Field>
            ) : null}
            <Field label="Pace">
              <Segmented
                label="Pace"
                value={settings.pacing}
                onChange={(pacing) => onChange({ pacing })}
                options={[
                  { value: 'gentle', label: 'Gentle' },
                  { value: 'fast', label: 'Quick' },
                ]}
              />
            </Field>
            <Field label="Voice speed">
              <input className="al-range" type="range" min={0.75} max={1.25} step={0.05} value={settings.voiceSpeed} aria-label="Voice speed" onChange={(e) => onChange({ voiceSpeed: Number(e.target.value) })} />
            </Field>
            <Switch label="Ask me to explain it back" checked={settings.teachBack} onChange={toggle('teachBack')} />
            <Switch label="Explain computer words" checked={settings.explainJargon} onChange={toggle('explainJargon')} />
            <Switch label="Demo mode" hint="Move up after one clean try" checked={settings.demoMode} onChange={toggle('demoMode')} />
          </Group>

          <Group title="On screen">
            <Switch label="Big marks" checked={settings.bigAnnotations} onChange={toggle('bigAnnotations')} />
            <AnnotationPreview settings={settings} />
            <Switch label="Text only, no speaking" checked={settings.textOnly} onChange={toggle('textOnly')} />
          </Group>

          <Group title="Listening">
            <Switch label="Listen for my name" checked={settings.wakeEnabled} onChange={toggle('wakeEnabled')} />
            <Switch label="Only when I press a key" checked={settings.pushToTalkOnly} onChange={toggle('pushToTalkOnly')} />
            <Switch label="Show the listening light" checked={settings.listeningLight} onChange={toggle('listeningLight')} />
          </Group>

          <Group title="Safety">
            <Switch label="Scam check" checked={settings.scamShield} onChange={toggle('scamShield')} />
            <Field label="Let me do things for you" hint="Off means I only show you how.">
              <Segmented
                label="Let me do things for you"
                value={settings.agency}
                onChange={(agency) => onChange({ agency })}
                options={[
                  { value: 'off', label: 'Off' },
                  { value: 'ask_each', label: 'Ask each time' },
                  { value: 'ask_per_task', label: 'Ask per task' },
                ]}
              />
            </Field>
            <Switch
              label="Let it act on its own when I am away"
              hint="Off by default. Only if you step away mid-lesson and a step is stuck, I may do that one step myself. I never pay, send, delete or log in, and Stop ends it."
              checked={settings.agency === 'autonomous'}
              onChange={(on) => onChange({ agency: on ? 'autonomous' : 'ask_each' })}
            />
          </Group>

          <Group title="Menu bar">
            <Switch label="Show in the menu bar" checked={settings.showMenuBarIcon} onChange={toggle('showMenuBarIcon')} />
            <Switch label="Open at login" checked={settings.launchAtLogin} onChange={toggle('launchAtLogin')} />
          </Group>

          {more}
        </div>
      ) : null}
    </div>
  )
}
