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

// `both` is the card the first wake, the talk key and the end of first run show when the voice question and the screen question are both due: one window, two clear lines (each its
// own answer in the settings), and four buttons of one weight. It is answered only by a real mouse click, like every card. Its body is two lines of one idea each, so its word budget is
// 30 (the other cards keep 22): the voice line is never longer than the screen line, and neither is cut, because a consent has to say all of it. `voice` and `screen` alone are shown
// when only one of the two is due (the other was answered earlier).
export const CARDS: Readonly<Record<'both' | 'voice' | 'screen' | 'click', CardText>> = {
  both: {
    title: 'Talk with Knack?',
    body: 'Voice: your voice goes to a cloud voice model while we talk.\nScreen: a small picture goes with it about every 5 seconds. Never from private apps. Nothing is saved.',
    buttons: [
      { id: 'yes', label: 'Yes, allow both' },
      { id: 'voice_only', label: 'Voice only' },
      { id: 'not_now', label: 'Not now' },
      { id: 'never', label: 'Never' },
    ],
  },
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

// What Knack says, on a card, when the words were heard (or the talk key was held) but a conversation cannot open or cannot hear: never silence, and the title names the one real cause.
// Plain reasons, one action at most. `settings` opens Knack's Settings; `microphone` asks macOS (when it has not been asked) or opens its microphone pane (when it said no); `sound` opens
// the macOS Sound pane. No card uses developer wording (a test pins this).
export const HEARD_TITLE = 'Hey Knack heard you.'
export type InfoAction = 'settings' | 'microphone' | 'screen' | 'screen_ask' | 'speech' | 'accessibility' | 'dictation' | 'sound'
export interface InfoCard {
  title: string
  body: string
  buttons: ReadonlyArray<{ id: string; label: string }>
  /** What the first button does (the second is always Close). Null: only Close. */
  action: InfoAction | null
}
const CLOSE = { id: 'close', label: 'Close' } as const
const SETTINGS_BTN = [{ id: 'settings', label: 'Open Settings' }, CLOSE] as const
// Screen Recording is asked the way the microphone is: the button asks macOS first (that is what lists Knack under Privacy and Security, Screen Recording), then opens that pane.
// macOS applies the new permission only to a Knack that is opened again, so the card says so.
const ALLOW_SCREEN = [{ id: 'screen', label: 'Allow screen help' }, CLOSE] as const
const card = (title: string, body: string, buttons: InfoCard['buttons'] = [CLOSE], action: InfoAction | null = null): InfoCard => ({ title, body, buttons, action })
export const INFO_CARDS: Readonly<Record<string, InfoCard>> = {
  // The switch is off (the worker's own choice): the Settings wording is true. When the switch is on and the service just could not be reached, `models_unreachable` says so.
  mock_mode: card('Voice needs live models.', 'Turn on Use live models in Settings, then try again.', SETTINGS_BTN, 'settings'),
  models_unreachable: card('Knack could not reach the model service.', 'It keeps trying and will switch on by itself.'),
  no_key: card('Voice needs a Gemini key.', 'Add the key to the .env file and reopen Knack.', [CLOSE]),
  no_model: card('Voice has no model set.', 'Add the voice model name to the .env file and reopen Knack.', [CLOSE]),
  model_unusable: card('The voice model was not accepted.', 'The key cannot use the voice model that is set. Run Check voice in Settings.', SETTINGS_BTN, 'settings'),
  flag_off: card('Voice is switched off.', 'Remove the setting that switches it off from the .env file and reopen Knack.', [CLOSE]),
  breaker_open: card('The voice service is not answering.', 'Try again soon.'),
  day_cap: card('Today’s talking limit is reached.', 'You can raise it in Settings.', SETTINGS_BTN, 'settings'),
  // Pointing inside Knack, or inside a browser tab with the extension, never needs this: only "find it anywhere on my screen" does.
  screen_recording: card('To find it, Knack must see your screen.', 'Pointing in Knack or in a browser with the extension works without this. Finding things anywhere on screen needs Screen Recording.', ALLOW_SCREEN, 'screen_ask'),
  // The listener itself is blocked (shown once per cause): the worker is told what to turn on, and the button opens the right pane. The listener tries again by itself once it is on.
  blocked_mic_denied: card('Hey Knack needs the microphone.', 'Switch Knack on in System Settings, Microphone. Hey Knack starts by itself.', [{ id: 'microphone', label: 'System Settings' }, CLOSE], 'microphone'),
  blocked_speech_denied: card('Hey Knack needs speech recognition.', 'Switch Knack on in System Settings, Speech Recognition. Hey Knack starts by itself. Option-Space works meanwhile.', [{ id: 'speech', label: 'System Settings' }, CLOSE], 'speech'),
  blocked_on_device_unavailable: card('Hey Knack cannot listen yet.', 'This Mac has no on-device speech for your language. Turn on Dictation in System Settings, Keyboard.', [{ id: 'dictation', label: 'System Settings' }, CLOSE], 'dictation'),
  // A click that was allowed but could not run: Knack says so and shows instead.
  click_not_ready: card('I could not click for you.', 'Click for you is not ready on this Mac yet. I will show you instead.'),
  click_accessibility: card('Click for you needs Accessibility.', 'Turn Knack on in System Settings, Accessibility. For now I will show you instead.', [{ id: 'accessibility', label: 'System Settings' }, CLOSE], 'accessibility'),
  click_screen_recording: card('Click for you needs Screen Recording.', 'Choose Allow screen help, switch Knack on, then reopen Knack. For now I will show you instead.', ALLOW_SCREEN, 'screen_ask'),
  task_unavailable: card(HEARD_TITLE, 'The task service is not answering. Try again soon.'),
  too_many_tasks: card(HEARD_TITLE, 'Too many tasks are running. Stop one or wait.'),
  ready: card('Talking is on.', 'Hold Option-Space and talk, or say Hey Knack.'),
  mic_permission: card('Knack needs the microphone.', 'Switch Knack on in System Settings, Microphone, then try again.', [{ id: 'microphone', label: 'System Settings' }, CLOSE], 'microphone'),
  paused: card('Knack is paused.', 'Choose Resume in the menu bar, then try again.'),
  killed: card('Everything is stopped.', 'Choose Resume in the menu bar, then try again.'),
  agent_acting: card('Knack is working.', 'Try again when it finishes.'),
  // A conversation opened and could not hear or answer: each cause says the one thing to do.
  mic_device: card('Knack could not open the microphone.', 'Check that a microphone is connected and chosen in System Settings, Sound, Input.', [{ id: 'sound', label: 'System Settings' }, CLOSE], 'sound'),
  secure_input: card('Knack cannot listen right now.', 'A password field or a secure app is open. Close it, then try again.'),
  denylisted_app: card('Knack skips private apps.', 'A private app is in front, so Knack did not listen. Switch to another app and try again.'),
  locked: card('The screen is locked.', 'Unlock it, then try again.'),
  gate_stale: card('Knack could not check the screen.', 'It checks that nothing private is in front before it listens. Try again in a moment.'),
  ledger_unavailable: card('Knack could not start talking.', 'The privacy record is not answering, so nothing was sent. Reopen Knack and try again.'),
  voice_no_key: card('Voice needs a Gemini key.', 'Add the key to the .env file and reopen Knack.'),
  voice_refused: card('The voice service said no.', 'It did not accept the key or the voice model. Run Check voice in Settings.', SETTINGS_BTN, 'settings'),
  voice_network: card('Knack could not reach the voice service.', 'Check your internet connection, then try again.'),
  connection_lost: card('The voice connection dropped.', 'Try again in a moment.'),
  // The conversation goes on by voice, but it was meant to see the screen and cannot: one card per conversation, the cause in the body, never silence and never a pretence of seeing.
  screen_missing: card('Knack cannot see your screen yet.', 'Choose Allow screen help, switch Knack on, then reopen Knack. Talking still works.', ALLOW_SCREEN, 'screen_ask'),
  screen_failed: card('Knack could not capture your screen.', 'Talking still works. Knack will say what it cannot see.'),
  screen_secure_input: card('Knack cannot see your screen right now.', 'A password field is open. Talking still works.'),
  screen_private_app: card('Knack cannot see your screen right now.', 'A private app is in front. Talking still works.'),
  screen_locked: card('Knack cannot see your screen right now.', 'The screen is locked. Talking still works.'),
  screen_shared: card('Knack cannot see your screen right now.', 'The screen is being shared, so Knack does not look. Talking still works.'),
  screen_stale: card('Knack cannot see your screen right now.', 'It could not check what is in front. Talking still works.'),
  screen_paused: card('Knack cannot see your screen right now.', 'Knack is paused. Choose Resume in the menu bar.'),
  // After the yes to talking and looking, when macOS has not allowed Screen Recording yet.
  screen_help: card('One more step for screen help.', 'Choose Allow screen help, switch Knack on, then reopen Knack. Talking works meanwhile.', ALLOW_SCREEN, 'screen_ask'),
}
/** The card for a refusal code, or null when the conversation is simply already open ('busy') or the code is unknown. */
export const infoCardFor = (reason: string | null): InfoCard | null => (reason && reason !== 'busy' ? (INFO_CARDS[reason] ?? null) : null)

/** The microphone cards when macOS has not been asked yet: Knack is not in the Microphone list until it has been, so the button asks (the macOS question appears) instead of opening a list that does not hold Knack. */
const MIC_ASK_CARD = card('Knack needs the microphone.', 'Choose Allow, then say yes when macOS asks.', [{ id: 'microphone', label: 'Allow' }, CLOSE], 'microphone')
export function infoCardWith(reason: string | null, ctx: { micStatus?: string } = {}): InfoCard | null {
  if ((reason === 'mic_permission' || reason === 'blocked_mic_denied') && ctx.micStatus === 'not-determined') return reason === 'mic_permission' ? MIC_ASK_CARD : { ...MIC_ASK_CARD, title: 'Hey Knack needs the microphone.' }
  return infoCardFor(reason)
}

/** Why a wake could not start a conversation (fixed lines for the status row; the Live manager's closed refusal codes). */
export const REFUSAL_LINE: Readonly<Record<string, string>> = {
  flag_off: 'Voice is switched off.',
  not_enabled: 'Talking is off. Say yes on the card to turn it on.',
  no_consent: 'Talking is off. Say yes on the Talk with Knack card, in the corner, to turn it on.',
  paused: 'Knack is paused.',
  killed: 'Everything is stopped.',
  agent_acting: 'Knack is working. Try again when it finishes.',
  day_cap: 'Today’s talking limit is reached.',
  breaker_open: 'The voice service is not answering. Try again soon.',
  no_model: 'Voice has no model set.',
  model_unusable: 'The voice model was not accepted.',
  no_key: 'Voice needs a Gemini key.',
  mock_mode: 'Voice needs live models.',
  models_unreachable: 'Knack could not reach the model service. It keeps trying.',
  mic_permission: 'Knack needs the microphone. Turn it on in System Settings.',
  busy: 'Knack is already talking.',
}

export const BLOCKED_LINE: Readonly<Record<BlockedCode, string>> = {
  binary_missing: 'Hey Knack is not installed. Hold Option-Space to talk instead.',
  mic_denied: 'Hey Knack needs the microphone. Turn it on in System Settings.',
  mic_restricted: 'The microphone is restricted on this Mac, so Hey Knack stays off.',
  speech_denied: 'Hey Knack needs speech recognition. Turn it on in System Settings. Hold Option-Space to talk meanwhile.',
  speech_restricted: 'Speech recognition is restricted on this Mac, so Hey Knack stays off. Hold Option-Space to talk instead.',
  on_device_unavailable: 'This Mac cannot recognise speech on the device, so Hey Knack stays off. Hold Option-Space to talk instead.',
  locale_unsupported: 'Hey Knack does not support this language on the device. Hold Option-Space to talk instead.',
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

// ------------------------------------------------------------------------------------------------ a screen task that did not run
/** The service's result line for a screen task that did not click ("Reported, not checked: ..." is a real run's prefix). */
const RAN_PREFIX = 'Reported, not checked: '
const REFUSED_RE = /^Knack won['\u2019]t work in ([^:]{1,40}): /
/** The app named in a "Knack won't work in <App>: ..." result, cleaned to letters, digits and a few marks (it is a window's name: data, never words of ours), or null when the result is something else. */
export function refusedAppOf(result: string | null | undefined): string | null {
  const m = REFUSED_RE.exec(result ?? '')
  if (!m) return null
  const app = m[1].replace(/[^\p{L}\p{N} .&+_-]/gu, '').trim().slice(0, 30)
  return app || 'that app'
}
/** True when a done screen task did not work on the screen: its result is the service's explanation of what is missing, not a report of a run. */
export const screenTaskDidNotRun = (result: string | null | undefined): boolean => typeof result === 'string' && result.trim() !== '' && !result.startsWith(RAN_PREFIX)

/** Why a screen task did not run: which app Knack will not work in, and what to do. Built from fixed words and the cleaned app name; the service's sentence is only read for the name. */
export const refusedAppCard = (app: string): CardText => ({ title: `Knack cannot work in ${app}.`, body: 'Bring the app you want help in to the front and ask again.', buttons: [{ id: 'close', label: 'Close' }] })
/** Any other reason a screen task did not run: the service's own plain sentence (data from the task), cut to the budget. */
export const screenTaskStoppedCard = (result: string): CardText => ({ title: 'Knack could not work on the screen.', body: fitWords(result, 22), buttons: [{ id: 'close', label: 'Close' }] })

/** The first conversation while set-up is still open: the window has no sidebar yet, so the example points at the button that is there. */
export const FIRST_WELCOME_SETUP = 'Hi, I am Knack. Try saying: show me where the Show my week button is.'
export const FIRST_WAKE_OPENING_SETUP =
  `This is the worker's first conversation with you, and Knack's set-up is still open. Say exactly: "${FIRST_WELCOME_SETUP}" and then wait. ` +
  'If they say it, call point_at with the description "Show my week" and then say: "That is the Show my week button." Then tell them they can ask for help or say goodbye. ' +
  'Keep every sentence short and plain.'
