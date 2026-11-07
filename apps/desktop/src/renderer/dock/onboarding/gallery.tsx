// Review page for the onboarding flow: every screen side by side in the variant named by the query string
// (?variant=light|dark|hc|hcdark|dyslexia|big|glass&only=<step index>). Not shipped in the app build.
import { createRoot } from 'react-dom/client'
import { DEFAULT_SETTINGS } from '../../../shared/settings'
import { applyDesignSettings } from '../../design'
import '../../design/styles'
import { OnboardingFlow } from './OnboardingFlow'
import { STEP_IDS } from './flow'
import type { PermissionStatus, PermissionsApi } from './permissions'

const params = new URLSearchParams(location.search)
const variant = params.get('variant') ?? 'light'
const only = params.get('only')
const perm = params.get('perm') ?? 'mixed'

const root = document.documentElement
const dark = variant === 'dark' || variant === 'hcdark'
root.dataset.theme = dark ? 'dark' : 'light'
const bigText = variant === 'big'
applyDesignSettings(
  { ...DEFAULT_SETTINGS, highContrast: variant === 'hc' || variant === 'hcdark', dyslexiaFont: variant === 'dyslexia', bigAnnotations: bigText },
  'marcus',
)
root.dataset.theme = dark ? 'dark' : 'light'
document.body.classList.add('al-app')
document.body.style.margin = '0'
document.body.style.background = dark ? '#000' : '#cfc8bb'

const statuses: Record<string, PermissionStatus> = {
  mixed: { microphone: 'granted', screen: 'not-determined', accessibility: false, probe: 'skipped', needsRestart: false, hint: 'In System Settings, switch on Electron (the app you are running me from).' },
  none: { microphone: 'denied', screen: 'denied', accessibility: false, probe: 'skipped', needsRestart: false, hint: 'In System Settings, switch on Electron (the app you are running me from).' },
  restart: { microphone: 'granted', screen: 'granted', accessibility: true, probe: 'empty', needsRestart: true, hint: 'Quit and reopen Alongside once Screen Recording is on.' },
}
const permissionsApi: PermissionsApi = {
  status: async () => statuses[perm] ?? statuses.mixed!,
  requestMicrophone: async () => true,
  requestAccessibility: () => false,
  requestScreen: async () => statuses[perm] ?? statuses.mixed!,
  openSettings: () => undefined,
  relaunch: () => undefined,
  onChange: () => () => undefined,
}
// The page records every call so an interactive run can be inspected: window.__log.
const log: { patches: unknown[]; profile: string; done: string | null } = { patches: [], profile: '# My Alongside profile\n', done: null }
;(window as unknown as { __log: typeof log }).__log = log
const api = {
  patchSettings: async (patch: unknown) => void log.patches.push(patch),
  learnerMarkdown: async (req: { op: string; content?: string }) => {
    if (req.op === 'write' && req.content !== undefined) log.profile = req.content
    return { ok: true, content: log.profile, revision: String(log.profile.length) }
  },
}

const glassOn = variant === 'glass'
const steps = only !== null ? [Number(only)] : STEP_IDS.map((_, i) => i)

createRoot(document.getElementById('root') as HTMLElement).render(
  <div style={{ display: 'grid', gridTemplateColumns: only !== null ? '380px' : 'repeat(3, 380px)', gap: 12, padding: 12, width: 'max-content' }}>
    {steps.map((i) => (
      <div key={i} className="al-app al-dock" style={{ width: 380, height: 620, maxWidth: 380 }} data-frame={STEP_IDS[i]}>
        <OnboardingFlow
          startStep={i}
          settings={{ userName: i >= 9 ? 'Peggy' : '', glass: glassOn, glassOpacity: Number(params.get('opacity') ?? 0.6), textScale: bigText ? 1.3 : 1, theme: dark ? 'dark' : 'light', persona: 'marcus' }}
          onPatch={(p) => void log.patches.push(p)}
          onDone={(o) => void (log.done = o)}
          api={api}
          permissionsApi={permissionsApi}
        />
      </div>
    ))}
  </div>,
)
