// The real readings behind "Check voice" (voice-check.ts is the pure part): macOS permission status (read only), the console probe for a password field, the Mac's volume settings, the
// model and token readings, and the worker's saved answers. Nothing here asks macOS for a permission, opens the microphone, plays a sound or sends audio or a picture. Every reading is
// injectable, so the tests run it with fakes.
import { execFile } from 'node:child_process'
import type { KnackConsentAsk, KnackVoiceCheck } from '../../shared/knack'
import type { PermissionStatus } from '../../shared/permissions'
import { createConsoleProbe, type ConsoleProbe } from '../awareness/probes'
import { liveFlagOn, liveModelId, type Env } from '../live/flags'
import { LIVE_CONSENT_VERSION, type LiveSettings } from '../live/settings'
import { checkLiveModel, createTokenMinter, TokenError, type ModelCheck, type TokenMinter } from '../live/token'
import type { WakeSettings } from '../wake/settings'
import type { WakeStatus } from '../wake/controller'
import { buildVoiceCheck, type MediaStatus, type VoiceCheckInputs } from './voice-check'

export interface Sound {
  outputMuted: boolean | null
  outputVolume: number | null
  inputVolume: number | null
}

/** Parses `osascript -e 'get volume settings'`: "output volume:63, input volume:63, alert volume:100, output muted:false". A value that is "missing value" is null. */
export function parseVolumeSettings(out: string): Sound | null {
  const num = (name: string): number | null => {
    const m = new RegExp(`${name} volume:\\s*(\\d{1,3})`).exec(out)
    return m ? Math.min(100, Number(m[1])) : null
  }
  const muted = /output muted:\s*(true|false)/.exec(out)
  const sound = { outputMuted: muted ? muted[1] === 'true' : null, outputVolume: num('output'), inputVolume: num('input') }
  return sound.outputMuted === null && sound.outputVolume === null && sound.inputVolume === null ? null : sound
}

const realVolume = (): Promise<string> =>
  new Promise((resolve) => {
    // Read only: it does not touch the sound hardware and needs no permission.
    execFile('osascript', ['-e', 'get volume settings'], { timeout: 3000, encoding: 'utf8' }, (err, stdout) => resolve(err ? '' : stdout))
  })

export interface VoiceCheckPortDeps {
  env: Env
  platform?: NodeJS.Platform
  live: () => { settings: { get(): LiveSettings } } | null
  wake: () => { status(): WakeStatus; settings: { get(): WakeSettings; patch(p: unknown, o: { trusted: boolean }): unknown }; helperPresent(): boolean; setListen(on: boolean): void; askConsent?(): Promise<KnackConsentAsk> } | null
  permissions: { status(): Promise<PermissionStatus> }
  killed: () => boolean
  paused: () => boolean
  now?: () => number
  // Test seams
  consoleProbe?: ConsoleProbe
  volume?: () => Promise<string>
  modelCheck?: (model: string | null) => Promise<ModelCheck>
  minter?: TokenMinter
}

const asMedia = (s: string): MediaStatus => (s === 'granted' || s === 'denied' || s === 'not-determined' || s === 'restricted' ? s : 'unknown')

export function createVoiceCheckPort(d: VoiceCheckPortDeps): { check(): Promise<KnackVoiceCheck>; askAgain(): boolean; askConsent(): Promise<KnackConsentAsk> } {
  const env = d.env
  const probe = d.consoleProbe ?? createConsoleProbe()
  const volume = d.volume ?? realVolume
  const mac = (d.platform ?? process.platform) === 'darwin'
  return {
    async check() {
      const live = d.live()?.settings.get()
      const wake = d.wake()
      const model = liveModelId(env)
      const [perms, cons, vol] = await Promise.all([
        d.permissions.status().catch(() => null),
        mac ? probe.read().catch(() => ({ secureInput: 'unknown' as const, locked: null })) : Promise.resolve({ secureInput: 'off' as const, locked: false }),
        mac ? volume().then(parseVolumeSettings, () => null) : Promise.resolve(null),
      ])
      const st = wake?.status()
      const inputs: VoiceCheckInputs = {
        now: (d.now ?? Date.now)(),
        liveFlagOn: liveFlagOn(env),
        offline: env.UNDERSTUDY_MOCK === '1' || env.ALONGSIDE_MOCK === '1',
        modelsReason: env.KNACK_MODELS_REASON ?? null,
        keyPresent: (env.GEMINI_API_KEY ?? '').trim().length > 0,
        modelId: model,
        killed: d.killed(),
        paused: d.paused(),
        consent: { liveEnabled: live?.liveEnabled === true, consentCurrent: live?.liveConsentVersion === LIVE_CONSENT_VERSION, voiceAnswer: wake?.settings.get().voiceAnswer ?? 'unset', frames: live?.liveFrames === true, screenAnswer: wake?.settings.get().screenAnswer ?? 'unset' },
        perms: { microphone: perms ? asMedia(perms.microphone) : 'unknown', screen: perms ? asMedia(perms.screen) : 'unknown', accessibility: perms?.accessibility === true },
        wake: wake && st ? { switchOn: st.switchOn, dormant: st.dormant, helper: { state: st.helper.state, code: st.helper.code }, helperPresent: wake.helperPresent() } : null,
        secureInput: cons.secureInput,
        sound: vol,
        modelCheck: () => (d.modelCheck ?? ((m) => checkLiveModel(m, { env })))(model),
        tokenCheck: async () => {
          try {
            await (d.minter ?? createTokenMinter({ env })).mint(model as string)
            return { ok: true, reason: 'ok' }
          } catch (err) {
            return { ok: false, reason: err instanceof TokenError ? err.code : 'network' }
          }
        },
      }
      return buildVoiceCheck(inputs)
    },
    // The "Your yes" button: the card is shown (explicitly asked for, so an earlier Not now or Never is forgotten first); the answer is a real click on the card, never this call.
    async askConsent() {
      const wake = d.wake()
      return wake?.askConsent ? wake.askConsent() : 'blocked'
    },
    // Forget an earlier Never or Not now on the Talk with Knack card (and the screen card), so each card shows again the next time it is due. The yes itself is still only the worker's click.
    askAgain() {
      const wake = d.wake()
      if (!wake) return false
      wake.settings.patch({ voiceAnswer: 'unset', voiceAskAfterMs: 0, screenAnswer: 'unset', screenAskAfterMs: 0 }, { trusted: true })
      wake.setListen(true)
      return true
    },
  }
}
