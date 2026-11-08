// "Check voice": one plain report of every stage a spoken conversation needs, each either Ready or the ONE thing to do. Pure over injected readings, so the tests run with fakes and no
// microphone, speaker, screen or network. It reads status only: it never asks macOS for anything (an Allow button on a stage is the worker's click, and the page asks through the
// permissions door the first run already uses), never opens the microphone, never plays a sound, and sends no audio or picture. The two network readings (the model exists, and the
// service gives out a voice token) are made only when the key and the model are set, and carry no content.
import type { KnackPermKind, KnackVoiceAction, KnackVoiceCheck, KnackVoiceStage } from '../../shared/knack'
import type { Dormancy } from '../wake/guards'
import { DORMANT_LINE } from '../wake/guards'
import type { BlockedCode } from '../wake/helper'
import { BLOCKED_LINE } from '../wake/texts'
import { MODELS_UNREACHABLE_LINE } from './model-mode'

export type MediaStatus = 'granted' | 'denied' | 'not-determined' | 'restricted' | 'unknown'

export interface VoiceCheckInputs {
  now: number
  /** UNDERSTUDY_X_LIVE and UNDERSTUDY_FLAG_VOICE (flags.ts liveFlagOn). */
  liveFlagOn: boolean
  /** The app runs on its offline stand-ins (UNDERSTUDY_MOCK or ALONGSIDE_MOCK): it never opens a real voice session. */
  offline: boolean
  /** Why the app chose models off (the shell's closed word: switched_off, no_key, boot_check_failed), or null when unknown. Only read while `offline`. */
  modelsReason?: string | null
  keyPresent: boolean
  /** The configured Live model id, or null. */
  modelId: string | null
  killed: boolean
  paused: boolean
  consent: { liveEnabled: boolean; consentCurrent: boolean; voiceAnswer: string; /** Looking at the screen while talking was agreed to (the card's second line). */ frames?: boolean; screenAnswer?: string }
  perms: { microphone: MediaStatus; screen: MediaStatus; accessibility: boolean }
  /** Hey Knack: null when the build has no listener. */
  wake: { switchOn: boolean; dormant: Dormancy | null; helper: { state: 'stopped' | 'starting' | 'listening' | 'backoff' | 'blocked'; code: string | null }; helperPresent: boolean } | null
  secureInput: 'on' | 'off' | 'unknown'
  sound: { outputMuted: boolean | null; outputVolume: number | null; inputVolume: number | null } | null
  /** Network readings; each is only called when it can mean something. */
  modelCheck: () => Promise<{ ok: boolean; reason: string }>
  tokenCheck: () => Promise<{ ok: boolean; reason: string }>
}

const ask = (what: KnackPermKind): KnackVoiceAction => ({ do: 'ask', what })
const open = (what: KnackPermKind | 'sound'): KnackVoiceAction => ({ do: 'open', what })
const SETTINGS: KnackVoiceAction = { do: 'settings' }

const ready = (id: string, title: string, line: string, extra: Partial<KnackVoiceStage> = {}): KnackVoiceStage => ({ id, title, state: 'ready', line, action: null, needs: 'both', ...extra })
const fix = (id: string, title: string, line: string, action: KnackVoiceAction | null, extra: Partial<KnackVoiceStage> = {}): KnackVoiceStage => ({ id, title, state: 'fix', line, action, needs: 'both', ...extra })

/** The report, stage by stage. `ok` is true when a conversation can happen; `heyKnack` when the hands-free words can start one too. */
export async function buildVoiceCheck(i: VoiceCheckInputs): Promise<KnackVoiceCheck> {
  const stages: KnackVoiceStage[] = []

  // 1. live models
  // The real reason: the Settings wording is only true when the switch is really off.
  if (i.offline && i.modelsReason === 'boot_check_failed') stages.push(fix('models', 'Live models', MODELS_UNREACHABLE_LINE, null))
  else if (i.offline && i.modelsReason === 'no_key') stages.push(fix('models', 'Live models', 'Live models are off because no Gemini key is set. Add it to the .env file and reopen Knack.', null))
  else if (i.offline) stages.push(fix('models', 'Live models', 'Voice needs live models. Turn on Use live models in Settings.', SETTINGS))
  else if (!i.liveFlagOn) stages.push(fix('models', 'Live models', 'Voice is switched off. Remove the setting that switches it off from the .env file and reopen Knack.', null))
  else stages.push(ready('models', 'Live models', 'Live models are on.'))

  // 2. key and model, then the voice service itself (only asked when the earlier ones can pass)
  const modelsOk = stages[0].state === 'ready'
  if (!i.keyPresent) stages.push(fix('key', 'Gemini key', 'Voice needs a Gemini key. Add it to the .env file and reopen Knack.', null))
  else if (!i.modelId) stages.push(fix('key', 'Voice model', 'Voice has no model set. Add the voice model name to the .env file and reopen Knack.', null))
  else if (!modelsOk) stages.push(ready('key', 'Key and model', 'A key and a voice model are set.'))
  else {
    const m = await i.modelCheck().catch(() => ({ ok: false, reason: 'unreachable' }))
    if (m.ok) stages.push(ready('key', 'Key and model', 'The voice model exists for this key.'))
    else if (m.reason === 'unreachable') stages.push(fix('key', 'Key and model', 'Knack could not reach the voice service. Check your internet connection, then check again.', null))
    else if (m.reason === 'cannot_stream') stages.push(fix('key', 'Key and model', 'The voice model set cannot hold a voice conversation. Set a Live model in the .env file and reopen Knack.', null))
    else stages.push(fix('key', 'Key and model', 'The key cannot use the voice model that is set. Check both in the .env file and reopen Knack.', null))
  }
  if (stages[1].state === 'ready' && modelsOk && i.modelId) {
    const t = await i.tokenCheck().catch(() => ({ ok: false, reason: 'network' }))
    if (t.ok) stages.push(ready('service', 'Voice service', 'The voice service accepts Knack.'))
    else if (t.reason === 'refused') stages.push(fix('service', 'Voice service', 'The voice service refused the key. Check it in the .env file and reopen Knack.', null))
    else stages.push(fix('service', 'Voice service', 'Knack could not reach the voice service. Check your internet connection, then check again.', null))
  } else stages.push(fix('service', 'Voice service', 'Not checked yet. Fix the line above first.', null))

  // 3. the stop file and the pause
  if (i.killed) stages.push(fix('stopped', 'Stop everything', 'Everything is stopped. Choose Resume in the menu bar.', null))
  else if (i.paused) stages.push(fix('stopped', 'Pause', 'Knack is paused. Choose Resume in the menu bar.', null))
  else stages.push(ready('stopped', 'Stop everything', 'Nothing is stopped or paused.'))

  // 4. the worker's yes (only their real click on the card gives it; the button here only shows the card)
  if (i.consent.consentCurrent && i.consent.liveEnabled) {
    stages.push(ready('consent', 'Your yes', i.consent.frames ? 'You said yes to talking with Knack and to it looking at your screen while you talk.' : 'You said yes to talking with Knack. It does not look at your screen while you talk.'))
  } else if (i.consent.voiceAnswer === 'never') stages.push(fix('consent', 'Your yes', 'You chose Never on the Talk with Knack card. Show the card to answer again.', { do: 'consent' }))
  else stages.push(fix('consent', 'Your yes', 'Knack needs your yes to talk. The card has two lines, your voice and your screen. Show the card, then click Yes.', { do: 'consent' }))

  // 5. microphone: a status read, then Allow (asks macOS) or the Settings list
  stages.push(permStage('microphone', 'Microphone', i.perms.microphone, 'Knack can use the microphone.', 'Knack has not asked for the microphone yet. Choose Allow.', 'Switch Knack on in System Settings, Microphone.', 'This Mac does not let Knack use the microphone.'))

  // 6. a password field, a secure app, or a locked screen
  if (i.secureInput === 'on') stages.push(fix('secure', 'Password fields', 'A password field or a secure app has the keyboard, so Knack will not listen. Close it, then check again.', null))
  else stages.push(ready('secure', 'Password fields', i.secureInput === 'unknown' ? 'Knack could not read this. It will check again before it listens.' : 'No password field is open.'))

  // 7. the Mac's own sound
  const s = i.sound
  if (s && s.outputMuted === true) stages.push(fix('sound', 'Sound', 'The Mac is muted, so you could not hear Knack. Turn the sound on.', open('sound')))
  else if (s && s.outputVolume !== null && s.outputVolume <= 0) stages.push(fix('sound', 'Sound', 'The Mac volume is at zero, so you could not hear Knack. Turn it up.', open('sound')))
  else if (s && s.inputVolume !== null && s.inputVolume <= 0) stages.push(fix('sound', 'Sound', 'The microphone volume is at zero. Raise it in System Settings, Sound, Input.', open('sound')))
  else stages.push(ready('sound', 'Sound', s ? 'The Mac sound and microphone volume are on.' : 'Knack could not read the sound settings.'))

  // Hey Knack (the hands-free words) needs more than the talk key does
  if (!i.wake) stages.push(fix('hey', 'Hey Knack', 'Hey Knack is not in this app. Hold Option-Space to talk.', null, { needs: 'hey' }))
  else {
    const w = i.wake
    const h = w.helper
    const speech = ((): KnackVoiceStage => {
      if (h.state === 'listening') return ready('speech', 'Speech recognition', 'Speech recognition is allowed.', { needs: 'hey' })
      if (h.state === 'blocked' && h.code === 'speech_denied') return fix('speech', 'Speech recognition', 'Switch Knack on in System Settings, Speech Recognition.', open('speech'), { needs: 'hey' })
      if (h.state === 'blocked' && h.code === 'speech_restricted') return fix('speech', 'Speech recognition', 'This Mac does not let Knack use speech recognition.', null, { needs: 'hey' })
      if (h.state === 'blocked' && (h.code === 'on_device_unavailable' || h.code === 'locale_unsupported')) return fix('speech', 'Speech recognition', 'This Mac has no on-device speech for your language. Turn on Dictation in System Settings, Keyboard.', null, { needs: 'hey' })
      // macOS asks for speech recognition when the listener starts, so with Hey Knack switched off an Allow button would do nothing: say what to turn on instead.
      if (!w.switchOn) return fix('speech', 'Speech recognition', 'Not asked yet. Turn on Listen for Hey Knack and macOS will ask.', null, { needs: 'hey' })
      return fix('speech', 'Speech recognition', 'Not asked yet. Choose Allow, then say yes when macOS asks.', ask('speech'), { needs: 'hey' })
    })()
    stages.push(speech)
    if (!w.switchOn) stages.push(fix('hey', 'Hey Knack', 'Hey Knack is off. Turn on Listen for Hey Knack in Settings.', SETTINGS, { needs: 'hey' }))
    else if (!w.helperPresent) stages.push(fix('hey', 'Hey Knack', BLOCKED_LINE.binary_missing, null, { needs: 'hey' }))
    else if (h.state === 'blocked' && h.code && h.code in BLOCKED_LINE) stages.push(fix('hey', 'Hey Knack', BLOCKED_LINE[h.code as BlockedCode], null, { needs: 'hey' }))
    else if (w.dormant && w.dormant !== 'live_session') stages.push(fix('hey', 'Hey Knack', `${DORMANT_LINE[w.dormant]}.`.replace(/\.\.$/, '.'), null, { needs: 'hey' }))
    else if (h.state === 'listening' || w.dormant === 'live_session') stages.push(ready('hey', 'Hey Knack', 'Hey Knack is listening for the words.', { needs: 'hey' }))
    else stages.push(fix('hey', 'Hey Knack', 'Hey Knack is starting. Check again in a moment.', null, { needs: 'hey' }))
  }

  // Not needed for talking: what the on-screen guide and clicks need
  stages.push(
    i.perms.accessibility
      ? ready('accessibility', 'Accessibility', 'Knack can click for you when you allow it.', { optional: true })
      : fix('accessibility', 'Accessibility', 'Only needed for clicks. Choose Allow to turn it on.', ask('accessibility'), { optional: true }),
  )
  stages.push(
    i.perms.screen === 'granted'
      ? ready('screen', 'Screen recording', 'Knack can look at your screen and point at it.', { optional: true })
      : i.perms.screen === 'denied' || i.perms.screen === 'restricted'
        ? fix('screen', 'Screen recording', 'Only needed to look anywhere on screen. Switch Knack on in System Settings, Screen Recording.', open('screen'), { optional: true })
        : fix('screen', 'Screen recording', 'Only needed to look anywhere on screen. Choose Allow to turn it on.', ask('screen'), { optional: true }),
  )

  const required = stages.filter((x) => !x.optional)
  const talk = required.filter((x) => x.needs !== 'hey')
  return { ok: talk.every((x) => x.state === 'ready'), heyKnack: required.every((x) => x.state === 'ready'), stages, at: i.now }
}

function permStage(id: 'microphone', title: string, st: MediaStatus, okLine: string, notAsked: string, denied: string, restricted: string): KnackVoiceStage {
  if (st === 'granted') return ready(id, title, okLine)
  if (st === 'denied') return fix(id, title, denied, open(id))
  if (st === 'restricted') return fix(id, title, restricted, null)
  return fix(id, title, notAsked, ask(id))
}
