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
  /** Draw (or move) the one voice ring at this box. */
  show(box: [number, number, number, number]): void
  clear(): void
}

export interface ToolHost {
  candidates(): CandidateList
  point(description: string): Promise<{ found: boolean }>
  showStep(stepId: string): { ok: boolean; chip: string | null }
  askChoice(optionIds: string[]): boolean
}
