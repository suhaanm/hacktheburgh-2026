// Every word the Hey Knack feature shows, in one table, within the Knack word budgets (docs/KNACK_UX.md section 5): a corner card title is at most
// 8 words and its body at most 22, a button at most 3. Plain, no exclamation marks, no "please", no blame. Nothing here is built from model text,
// a transcript or anything on the screen: slots do not exist.
import type { Dormancy } from './guards'
import { DORMANT_LINE } from './guards'
import type { BlockedCode } from './helper'

export const LISTENING_LINE = 'Listening for Hey Knack. Stays on this Mac, nothing stored.'
export const SWITCH_LABEL = 'Listen for Hey Knack'
export const SWITCH_NOTE = 'Stays on this Mac. Nothing is stored.'

export interface CardText {
  title: string
  body: string
  buttons: ReadonlyArray<{ id: string; label: string }>
}

const THREE = [
  { id: 'yes', label: 'Yes' },
  { id: 'not_now', label: 'Not now' },
  { id: 'never', label: 'Never' },
] as const

export const CARDS: Readonly<Record<'voice' | 'screen' | 'click', CardText>> = {
  voice: {
    title: 'Talk with Knack?',
    body: 'Your voice goes to a cloud voice model while we talk. Nothing is saved on this Mac.',
    buttons: THREE,
  },
  screen: {
    title: 'Knack may look at your screen while we talk',
    body: 'A small picture goes to a cloud model about every 5 seconds. Never from private apps. Nothing is saved.',
    buttons: THREE,
  },
  click: {
    title: 'Click for you?',
    body: 'One click on the ringed spot, then it stops. You can press Stop at any time.',
    buttons: [
      { id: 'allow', label: 'Allow once' },
      { id: 'cancel', label: 'Cancel' },
    ],
  },
}

// What Knack says, on a card, when the words were heard but a conversation cannot open: never silence. Plain reasons, one action at most. `settings` opens
// Knack's Settings; `microphone` opens the macOS microphone pane. No card uses developer wording (a test pins this).
export const HEARD_TITLE = 'Hey Knack heard you.'
export type InfoAction = 'settings' | 'microphone'
export interface InfoCard {
  title: string
  body: string
  buttons: ReadonlyArray<{ id: string; label: string }>
  /** What the first button does (the second is always Close). Null: only Close. */
  action: InfoAction | null
}
const CLOSE = { id: 'close', label: 'Close' } as const
const NEEDS_LIVE: InfoCard = { title: HEARD_TITLE, body: 'Live voice needs live models. Turn them on in Settings.', buttons: [{ id: 'settings', label: 'Open Settings' }, CLOSE], action: 'settings' }
export const INFO_CARDS: Readonly<Record<string, InfoCard>> = {
  mock_mode: NEEDS_LIVE,
  no_key: NEEDS_LIVE,
  no_model: NEEDS_LIVE,
  model_unusable: NEEDS_LIVE,
  flag_off: NEEDS_LIVE,
  breaker_open: { title: HEARD_TITLE, body: 'The voice service is not answering. Try again soon.', buttons: [CLOSE], action: null },
  day_cap: { title: HEARD_TITLE, body: 'Today\u2019s talking limit is reached. You can raise it in Settings.', buttons: [{ id: 'settings', label: 'Open Settings' }, CLOSE], action: 'settings' },
  mic_permission: { title: HEARD_TITLE, body: 'Live voice needs the microphone. Turn it on in System Settings.', buttons: [{ id: 'microphone', label: 'System Settings' }, CLOSE], action: 'microphone' },
  paused: { title: HEARD_TITLE, body: 'Knack is paused. Resume it from the menu bar.', buttons: [CLOSE], action: null },
  killed: { title: HEARD_TITLE, body: 'Everything is stopped. Resume from the menu bar.', buttons: [CLOSE], action: null },
  agent_acting: { title: HEARD_TITLE, body: 'Knack is working. Try again when it finishes.', buttons: [CLOSE], action: null },
}
/** The card for a refusal code, or null when the conversation is simply already open ('busy') or the code is unknown. */
export const infoCardFor = (reason: string | null): InfoCard | null => (reason && reason !== 'busy' ? (INFO_CARDS[reason] ?? null) : null)

/** Why a wake could not start a conversation (fixed lines for the status row; the Live manager's closed refusal codes). */
export const REFUSAL_LINE: Readonly<Record<string, string>> = {
  flag_off: 'Voice is off in this build.',
  not_enabled: 'Talking is off. Say yes on the card to turn it on.',
  no_consent: 'Talking is off. Say yes on the card to turn it on.',
  paused: 'Knack is paused.',
  killed: 'Everything is stopped.',
  agent_acting: 'Knack is working. Try again when it finishes.',
  day_cap: 'Today’s talking limit is reached.',
  breaker_open: 'The voice service is not answering. Try again soon.',
  no_model: 'Live voice needs live models.',
  model_unusable: 'Live voice needs live models.',
  no_key: 'Live voice needs live models.',
  mock_mode: 'Live voice needs live models.',
  mic_permission: 'Knack needs the microphone. Turn it on in System Settings.',
  busy: 'Knack is already talking.',
}

export const BLOCKED_LINE: Readonly<Record<BlockedCode, string>> = {
  binary_missing: 'Hey Knack is not installed in this build.',
  mic_denied: 'Hey Knack needs the microphone. Turn it on in System Settings.',
  mic_restricted: 'The microphone is restricted on this Mac, so Hey Knack stays off.',
  speech_denied: 'Hey Knack needs speech recognition. Turn it on in System Settings.',
  speech_restricted: 'Speech recognition is restricted on this Mac, so Hey Knack stays off.',
  on_device_unavailable: 'This Mac cannot recognise speech on the device, so Hey Knack stays off.',
  locale_unsupported: 'Hey Knack does not support this language on the device.',
  recognizer_unavailable: 'Hey Knack stopped working. Switch it off and on to try again.',
  audio_engine_failed: 'Hey Knack stopped working. Switch it off and on to try again.',
  no_input_device: 'No microphone was found, so Hey Knack stays off.',
  internal: 'Hey Knack stopped working. Switch it off and on to try again.',
  protocol: 'Hey Knack stopped working. Switch it off and on to try again.',
  crash_loop: 'Hey Knack stopped working. Switch it off and on to try again.',
  spawn_failed: 'Hey Knack could not start. Switch it off and on to try again.',
}

export const dormantLine = (d: Dormancy): string => DORMANT_LINE[d]

/** Fixed spoken lines for the pack voice (ElevenLabs, by id) for the moments a Live conversation is not open. */
export const SPOKEN_LINES: Readonly<Record<string, string>> = {
  'wake.show_instead': 'I will show you instead.',
  'wake.done': 'Done.',
  'wake.did_not_work': 'That did not work. I stopped.',
  'wake.stopped': 'Stopped.',
}
