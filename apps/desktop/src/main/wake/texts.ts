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
export type InfoAction = 'settings' | 'microphone' | 'screen' | 'speech' | 'accessibility' | 'dictation'
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
  // Pointing inside Knack, or inside a browser tab with the extension, never needs this: only "find it anywhere on my screen" does.
  screen_recording: { title: 'To find it, Knack must see your screen.', body: 'Pointing in Knack or in a browser with the extension works without this. Finding things anywhere on screen needs Screen Recording.', buttons: [{ id: 'screen', label: 'System Settings' }, CLOSE], action: 'screen' },
  // The listener itself is blocked (shown once per cause): the worker is told what to turn on, and the button opens the right pane.
  blocked_mic_denied: { title: 'Hey Knack needs the microphone.', body: 'Turn it on for Knack in System Settings, then switch Listen for Hey Knack off and on.', buttons: [{ id: 'microphone', label: 'System Settings' }, CLOSE], action: 'microphone' },
  blocked_speech_denied: { title: 'Hey Knack needs speech recognition.', body: 'Turn it on for Knack in System Settings, then switch Listen for Hey Knack off and on.', buttons: [{ id: 'speech', label: 'System Settings' }, CLOSE], action: 'speech' },
  blocked_on_device_unavailable: { title: 'Hey Knack cannot listen yet.', body: 'This Mac has no on-device speech for your language. Turn on Dictation in System Settings, Keyboard.', buttons: [{ id: 'dictation', label: 'System Settings' }, CLOSE], action: 'dictation' },
  // A click that was allowed but could not run: Knack says so and shows instead.
  click_not_ready: { title: 'I could not click for you.', body: 'Click for you is not ready on this Mac yet. I will show you instead.', buttons: [CLOSE], action: null },
  click_accessibility: { title: 'Click for you needs Accessibility.', body: 'Turn Knack on in System Settings, Accessibility. For now I will show you instead.', buttons: [{ id: 'accessibility', label: 'System Settings' }, CLOSE], action: 'accessibility' },
  click_screen_recording: { title: 'Click for you needs Screen Recording.', body: 'Turn Knack on in System Settings, Screen Recording. For now I will show you instead.', buttons: [{ id: 'screen', label: 'System Settings' }, CLOSE], action: 'screen' },
  task_unavailable: { title: 'Hey Knack heard you.', body: 'The task service is not answering. Try again soon.', buttons: [CLOSE], action: null },
  too_many_tasks: { title: 'Hey Knack heard you.', body: 'Too many tasks are running. Stop one or wait.', buttons: [CLOSE], action: null },
  ready: { title: 'Talking is on.', body: 'Hold Option-Space and talk, or say Hey Knack.', buttons: [CLOSE], action: null },
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
  'wake.started': 'Started. I will tell you when it is done.',
}

/**
 * The code-written instruction for the FIRST conversation a worker ever has (trusted text, sent to the model as the opening turn; the packet also says
 * first_run). One welcome line and one example, both fixed; the example is answered with point_at on the Knack window's sidebar row. After it the
 * conversation is the ordinary one. `{welcome}` is the only words the worker is meant to hear first.
 */
export const FIRST_WELCOME = 'Hi, I am Knack. Try saying: show me where the Needs you list is.'
export const FIRST_WAKE_OPENING =
  `This is the worker's first conversation with you. Say exactly: "${FIRST_WELCOME}" and then wait. ` +
  'If they say it, call point_at with the description "Needs you" and then say: "That is the Needs you list." Then tell them they can ask for help or say goodbye. ' +
  'Keep every sentence short and plain.'

/** The info card for a failed click run, by the closed reason the desktop port or the agent service gave. */
export function clickFailureCard(reason: string | undefined): string {
  if (reason === 'accessibility_missing') return 'click_accessibility'
  if (reason === 'screen_recording_missing') return 'click_screen_recording'
  return 'click_not_ready'
}

// ------------------------------------------------------------------------------------------------ "Hey Knack, do X": the cards
const words = (t: string): string[] => t.trim().split(/\s+/).filter(Boolean)
/** At most `n` words, cut at the last sentence end that fits (or at n words with no ellipsis trick: never a half word). */
export function fitWords(text: string, n: number): string {
  const w = words(text)
  if (w.length <= n) return text.trim()
  const cut = w.slice(0, n).join(' ')
  const end = Math.max(cut.lastIndexOf('. '), cut.lastIndexOf('? '), cut.lastIndexOf('! '))
  return end > 0 ? cut.slice(0, end + 1) : `${cut.replace(/[,;:]$/, '')}.`
}
const lcfirst = (t: string): string => (t ? t[0].toLowerCase() + t.slice(1) : t)
const stop = (t: string): string => t.replace(/[.\s]+$/, '')

export interface TaskCardInput {
  kind: string
  can: string[]
  cannot: string[]
  folder: string | null
  buttons: { allow: string; decline: string; more: Array<{ id: string; label: string }> }
}
const CONSENT_TITLES: Record<string, string> = { claude_agent: 'Start a Claude agent for this?', browser: "Open Knack's browser for this?" }

/** The consent card for a task: what it can and cannot do, in the service's own plain lines, then Allow for this task, Not now, and More when the service offers a wider option. */
export function taskConsentCard(nc: TaskCardInput): CardText {
  const parts: string[] = []
  if (nc.can[0]) parts.push(`It can ${lcfirst(stop(nc.can[0]))}.`)
  if (nc.cannot[0]) parts.push(`It cannot ${lcfirst(stop(nc.cannot[0]))}.`)
  let body = fitWords(parts.join(' '), 22)
  if (nc.folder && words(`${body} Folder: ${nc.folder}.`).length <= 22) body = `${body} Folder: ${nc.folder}.`
  const buttons = [{ id: 'allow', label: nc.buttons.allow }, { id: 'decline', label: nc.buttons.decline }, ...(nc.buttons.more.some((m) => m.id === 'everything') ? [{ id: 'more', label: 'More' }] : [])]
  return { title: CONSENT_TITLES[nc.kind] ?? 'Start this task?', body: body || 'Knack asks before it starts anything.', buttons }
}

/** The second card behind More: the wider option, said plainly, for this one task. */
export const EVERYTHING_CARD: CardText = {
  title: 'Allow everything for this task?',
  body: 'It can read and change files and run commands without asking again. Only for this task.',
  buttons: [{ id: 'everything', label: 'Allow everything' }, { id: 'not_now', label: 'Not now' }],
}

/** A question the service asked about the request: the service's own template and option labels, as buttons. */
export function taskQuestionCard(q: { text: string; options: Array<{ id: string; label: string }> }): CardText {
  return { title: 'A quick question', body: fitWords(q.text, 22), buttons: q.options.slice(0, 4).map((o) => ({ id: o.id, label: o.label })) }
}

/** An answer that arrives when no conversation is open to read it out: the result line (data from the task), on a card. */
export function taskResultCard(result: string): CardText {
  return { title: 'Your answer', body: fitWords(result, 22), buttons: [{ id: 'close', label: 'Close' }] }
}

// ------------------------------------------------------------------------------------------------ typed tasks (the Ask bar) and the first welcome
/** The one plain sentence under the Ask bar's input when a typed task cannot be taken. The text stays in the box. */
export const TYPED_LINES: Readonly<Record<string, string>> = {
  too_many_tasks: 'Too many tasks are running. Stop one or wait.',
  kill_switch: 'Everything is stopped. Resume from the menu bar.',
  unavailable: 'The task service is not answering. Try again soon.',
  refused: 'Knack could not take that request.',
  unclear: 'Knack could not tell what to do with that. Say it another way.',
  no_service: 'Tasks are not available right now.',
}
export const typedFailureLine = (reason: string): string => TYPED_LINES[reason === 'no_token' || reason === 'not_offered' ? 'unavailable' : reason] ?? TYPED_LINES.unavailable

/** A typed task has no spoken line (unless voice is on): the same words appear on small cards. */
export const STARTED_CARD: CardText = { title: 'Started.', body: 'I will tell you when it is done.', buttons: [{ id: 'close', label: 'Close' }] }
export const doneCard = (result: string | null): CardText => ({ title: 'Done.', body: result ? fitWords(result, 22) : 'You can see it in Knack.', buttons: [{ id: 'close', label: 'Close' }] })
export const failedCard = (reason: string | null): CardText => ({ title: 'That did not work.', body: reason ? fitWords(reason, 22) : 'It stopped. Nothing else was changed.', buttons: [{ id: 'close', label: 'Close' }] })
export const showInsteadCard = (summary: string): CardText => ({ title: 'I will show you instead.', body: summary ? fitWords(summary, 22) : 'Knack does not click for you yet.', buttons: [{ id: 'close', label: 'Close' }] })

/** The first conversation while set-up is still open: the window has no sidebar yet, so the example points at the button that is there. */
export const FIRST_WELCOME_SETUP = 'Hi, I am Knack. Try saying: show me where the Show my week button is.'
export const FIRST_WAKE_OPENING_SETUP =
  `This is the worker's first conversation with you, and Knack's set-up is still open. Say exactly: "${FIRST_WELCOME_SETUP}" and then wait. ` +
  'If they say it, call point_at with the description "Show my week" and then say: "That is the Show my week button." Then tell them they can ask for help or say goodbye. ' +
  'Keep every sentence short and plain.'
