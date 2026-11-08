// The ports the voice session talks through. Each has a real adapter (electron.ts, http-ground.ts) and a fake for tests. Types only.
import type { CandidateList } from './tools'

/** The microphone and the speaker live in a renderer (getUserMedia exists only there); main drives them over IPC. */
export interface AudioBridge {
  /** Open the microphone; chunks are base64 PCM16 mono 16 kHz (~32 ms) with an RMS level 0..1. Rejects with MicError. Never prompts for permission. */
  startMic(onChunk: (b64: string, level: number) => void): Promise<void>
  stopMic(): void
  /** Queue base64 PCM16 mono 24 kHz model audio for playback. */
  play(b64: string): void
  /** Drop everything queued, at once (barge-in, end of session). */
  flush(): void
  /** The queue drained to empty. */
  onPlaybackIdle(cb: () => void): () => void
  isPlaying(): boolean
}

export class MicError extends Error {
  constructor(
    readonly code: 'permission' | 'device',
    message: string,
  ) {
    super(message)
    this.name = 'MicError'
  }
}

/** A clip of fixed pack speech (ElevenLabs, cached by the agent service) for CueSpeaker. */
export interface ClipPlayer {
  play(bytes: Uint8Array, mime: string): Promise<void>
  stop(): void
}

// ---- grounding (the shape of POST /cue/ground, and of the desktop's DOM grounder, which answers with source 'dom')
export interface GroundMenuItem {
  id: string
  label: string
}

export interface GroundRequest {
  menu: GroundMenuItem[]
  app_kind?: string
}

export interface GroundAnswer {
  available: string[]
  chosen: string | null
  // [y0, x0, y1, x1] on the 0..1000 grid from the top-left of the display.
  box_2d: [number, number, number, number] | null
  confidence: number
  source: 'vision' | 'dom'
  model_tier?: 'lite' | 'full'
  latency_ms?: number
}

export interface GroundPort {
  ground(req: GroundRequest): Promise<GroundAnswer | null>
}

/** What the model's tools reach. The Cue module implements `cue` (its LiveCuePort); the overlay draws the ring. */
export interface LiveCuePort {
  /** The closed list of pack steps for this moment: at most 6 ids with their pack labels. */
  candidates(): Array<{ id: string; label: string }>
  showStep(stepId: string): { ok: boolean; chip: string | null }
  /** Opens the question card for 2 to 4 candidate ids. */
  askChoice(optionIds: string[]): boolean
  /** The card was answered (click, key or voice). */
  onAnswer(cb: (answerId: string) => void): () => void
}

export interface RingPort {
  /** Draw (or move) the one voice ring at this box. With `ghost`, the ghost cursor also glides to its centre (a pointer, never a click). */
  show(box: [number, number, number, number], opts?: { ghost?: boolean }): void
  clear(): void
}

/** What `do_it_for_me` hands to code: the thing the model named, and where the grounder found it (null: not found). */
export interface DoItRequest {
  description: string
  box: [number, number, number, number] | null
}
export type DoItAnswer = { ok: true; started: true } | { ok: false; reason: string }

/** The closed answer `start_task` gets back: the route the service chose and whether a card is waiting for the worker. Never a summary, never row text
 *  (except `result`, one cleaned line of at most 140 characters, only for a question that was answered inline). */
export type TaskRoute = 'answer' | 'browser' | 'desktop' | 'claude_agent' | 'unclear'
export type TaskAnswer =
  | { ok: true; started: false; waiting_consent: boolean; route: TaskRoute; asked?: boolean; result?: string | null; desktop_click_possible?: boolean }
  | { ok: false; reason: 'too_many_tasks' | 'kill_switch' | 'unavailable' | 'refused' | 'no_session' }

export interface ToolHost {
  candidates(): CandidateList
  point(description: string): Promise<{ found: boolean }>
  showStep(stepId: string): { ok: boolean; chip: string | null }
  askChoice(optionIds: string[]): boolean
  /** Wake sessions only: take the ring and the ghost cursor away. */
  clear?(): void
  /** Wake sessions only: ring the named thing, then ask code whether it may be clicked. Resolves with the closed answer; never clicks itself. */
  doItForMe?(description: string): Promise<DoItAnswer>
  /** Talk-key and wake sessions: hand the worker's request (the model's wording, cleaned and capped) to the task service. Never starts anything itself. */
  startTask?(text: string): Promise<TaskAnswer>
}
