// Cue: the stuck-rescue feature (docs/REQ7_PLAN.md section 4), the Electron side. Two calls from main/index.ts:
//     import { startCue, stopCue } from './cue'
//     startCue({ ...ctx, ... })    after createServices, and    stopCue()    in the will-quit handler.
// Off unless UNDERSTUDY_X_CUE=1 AND the worker's own switch (settings.cueEnabled) is on: with the flag off nothing is created, no window, no
// timer, no shortcut, no request. Cue is visual by default; nothing speaks and no microphone opens unless the worker turned cueVoice on,
// the build has UNDERSTUDY_VOICE=1 and they used voice or asked. It never requests Accessibility or Screen Recording and never captures the screen.
import { globalShortcut, screen } from 'electron'
import { IPC } from '../../shared/ipc'
import type { ServiceContext } from '../context'
import { endpointsFromEnv } from '../engine/endpoints'
import { isKilled } from '../kill-flag'
import { createOverlayController } from '../overlay-controller'
import { createCueController, type AttentionPort, type CueController, type CueGrounder, type CueSignals, type OverlayPort } from './controller'
import { readCueSettings, type Policy } from './guards'
import { createDomRecheck, type DomRecheckDeps } from './dom-recheck'
import { createPanelWindow, type PanelWindow } from './panel-window'
import type { Pt, Rect } from './place'
import { createHttpEngine, type CueEnginePort } from './source'
import type { CueSpeaker, CueVoice, LiveCuePort } from './voice'

export interface CueStartContext extends ServiceContext {
  // The overlay the ring and the ghost cursor are drawn with. Default: a plain overlay controller on ctx (not the coach-telemetry one).
  overlay?: OverlayPort
  // From LIVE's registerLive(...): { voice, speaker, workerUsedVoice }. All optional; without them Cue is silent and deaf.
  voice?: CueVoice
  speaker?: CueSpeaker
  workerUsedVoice?: () => boolean
  // From AWARENESS: typing, and a reason to stay away (a denylisted frontmost app, secure input).
  signals?: Partial<CueSignals> & { suppressed?: () => string | null }
  // The one-voice rule (ATTENTION): admit before a new cue is drawn, release when it is gone. Optional; without it Cue behaves as before.
  attention?: AttentionPort
  // Finds a ring again after the screen changed, and follows it as the page moves (the DOM tracker, or a glance). Without it a stale ring is dropped.
  grounder?: CueGrounder
  // The shell's DOM grounder, to build that grounder from the decision's `step.target` (a zone): `{ grounder: domGrounder, display, calibration, onContent }`.
  // Ignored when `grounder` is given. Without a zone on the decision (an older engine) nothing can follow the ring, and it drops after 1.2 s as before.
  dom?: DomRecheckDeps
  // The page's visible text and controls in screen DIPs (from the browser extension's `content` field). Without it the card docks at a corner.
  content?: () => Rect[] | null
  // "Something else" on a question: open the conversation (LIVE). Not called unless the worker picks it.
  onConverse?: () => void
  // Who the decisions are for (the engine client's identity).
  person?: () => string | null
  // Tests and the storyboard: a port instead of the engine over loopback.
  engine?: CueEnginePort
  force?: boolean
}

export interface CueHandle {
  controller: CueController
  // For registerLive: the closed list of steps, show a step, ask a choice, hear the answer.
  livePort: LiveCuePort
  panel: PanelWindow
}

interface Running {
  handle: CueHandle
  quietUntilMemory: { value: number | null }
  disposers: Array<() => void>
}

let running: Running | null = null

/** The tray's "Quiet Cue for an hour": settings.cueQuietUntil when the key exists, and in memory in any case. */
export function quietCueFor(ms: number, now: number = Date.now()): void {
  if (running) {
    running.quietUntilMemory.value = now + ms
    running.handle.controller.refresh()
  }
}

export function cueEnabledByFlag(env: Record<string, string | undefined> = process.env): boolean {
  return env.UNDERSTUDY_X_CUE === '1'
}

export function startCue(ctx: CueStartContext): CueHandle | null {
  if (running) return running.handle
  if (!cueEnabledByFlag() && ctx.force !== true) return null

  const quietUntilMemory: { value: number | null } = { value: null }
  const settings = () => readCueSettings(ctx.settings.get())
  const suppressed = (): string | null => ctx.signals?.suppressed?.() ?? null
  const policy = (): Policy => {
    const s = settings()
    const quiet = Math.max(s.cueQuietUntil ?? 0, quietUntilMemory.value ?? 0)
    return { enabled: s.cueEnabled, proactivity: s.cueProactivity, quietUntil: quiet > 0 ? quiet : null, pausedUntil: s.pausedUntil, killed: isKilled(), suppressed: suppressed() }
  }

  const overlay: OverlayPort = ctx.overlay ?? createOverlayController(ctx)
  const engine: CueEnginePort = ctx.engine ?? createHttpEngine({ baseUrl: endpointsFromEnv().engine, person: ctx.person ?? (() => null), log: ctx.log })
  const cursor = (): Pt | null => {
    try {
      return screen.getCursorScreenPoint()
    } catch {
      return null
    }
  }

  // The controller needs the panel's actions and the panel needs the controller: the panel reports through a box filled just below.
  const box: { act: (a: import('./ipc').CueCardAction) => void } = { act: () => undefined }
  const panel = createPanelWindow({ onAction: (a) => box.act(a), shortcuts: globalShortcut, content: ctx.content, cursor, log: ctx.log })
  const controller = createCueController({
    engine,
    overlay,
    panel,
    policy,
    settings: () => ({ proactivity: settings().cueProactivity, voice: settings().cueVoice }),
    // Every optional signal the shell passes reaches the controller (typingNow, away, and quietS once CueSignals has it); `suppressed` lives in the policy.
    signals: { ...ctx.signals, workerUsedVoice: ctx.workerUsedVoice ?? ctx.signals?.workerUsedVoice },
    attention: ctx.attention,
    voice: ctx.voice,
    speaker: ctx.speaker,
    grounder: ctx.grounder ?? (ctx.dom ? createDomRecheck({ log: ctx.log, ...ctx.dom }) : undefined),
    onConverse: ctx.onConverse,
    buildVoiceOn: process.env.UNDERSTUDY_VOICE === '1',
    chord: process.platform === 'darwin' ? '⌥' : 'Alt+',
    log: ctx.log,
  })
  box.act = (a) => controller.action(a)

  const disposers: Array<() => void> = []
  // A change of settings, a stop or the kill switch takes down what is up straight away (otherwise the next poll would).
  const offSettings = ctx.settings.onChange(() => controller.refresh())
  disposers.push(offSettings)
  disposers.push(ctx.bus.on('session:ended', () => controller.refresh()))
  // The screen changed (the capture watcher's own event; Cue does not watch the screen itself): a ring that may have moved is checked.
  disposers.push(ctx.bus.on('screen:changed', ({ score }) => controller.screenChanged(score)))
  // The overlay page reloaded: whatever Cue had drawn there is gone with it, so the cue ends instead of waiting for its clock.
  disposers.push(ctx.bus.on('overlay:ready', () => controller.refresh()))
  void IPC // (the overlay channels are used through the overlay port; nothing else of the shared IPC is touched)

  controller.start()
  running = { handle: { controller, livePort: controller.livePort(), panel }, quietUntilMemory, disposers }
  return running.handle
}

export function stopCue(): void {
  const r = running
  if (!r) return
  running = null
  for (const d of r.disposers) d()
  r.handle.controller.dispose()
}
