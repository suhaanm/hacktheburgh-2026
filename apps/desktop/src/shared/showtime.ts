// Showtime: the automated, hard-coded walkthrough of Alongside. Types shared by main, the dock (narration audio,
// view cues) and the overlay (roadmap strip). Pure types only.
import type { PersonaId } from './protocol'

export type ShowtimeMode = 'scripted' | 'live'
export type ShowtimeChapterStatus = 'pending' | 'current' | 'done' | 'unavailable'

export interface ShowtimeChapterInfo {
  id: string
  n: number
  title: string
  caption: string
  status: ShowtimeChapterStatus
  durationMs: number
  // Why an unavailable chapter was skipped (shown nowhere on stage, logged and in the docs).
  reason?: string
}

export interface ShowtimeState {
  running: boolean
  paused: boolean
  mode: ShowtimeMode
  full: boolean
  // The discreet "Scripted walkthrough" pill (off only with ALONGSIDE_SHOWTIME_BADGE=0).
  badge: boolean
  // -1 when idle.
  chapterIndex: number
  chapters: ShowtimeChapterInfo[]
  chapterDurationMs: number
  // Elapsed inside the current chapter at `since` (renderers interpolate: elapsed + (Date.now() - since) while running).
  chapterElapsedMs: number
  since: number | null
  totalMs: number
  elapsedTotalMs: number
  // The tour finished and the app is back in normal live mode for questions.
  handover: boolean
  note?: string
}

export const IDLE_SHOWTIME_STATE: ShowtimeState = {
  running: false,
  paused: false,
  mode: 'scripted',
  full: false,
  badge: true,
  chapterIndex: -1,
  chapters: [],
  chapterDurationMs: 0,
  chapterElapsedMs: 0,
  since: null,
  totalMs: 0,
  elapsedTotalMs: 0,
  handover: false,
}

export type ShowtimeDockView = 'now' | 'chat' | 'progress' | 'profile' | 'settings'

// main -> dock window: narration audio and view cues.
export type ShowtimeCue =
  | { type: 'say'; id: string; text: string; persona: PersonaId; audioBase64?: string; mime?: string }
  | { type: 'stop-audio' }
  | { type: 'pause-audio' }
  | { type: 'resume-audio' }
  | { type: 'view'; view: ShowtimeDockView }
  | { type: 'chat'; id: string; role: 'user' | 'assistant'; text: string }
  | { type: 'profile-refresh' }

export interface ShowtimeStartOptions {
  full?: boolean
  mode?: ShowtimeMode
}

export interface ShowtimeApi {
  start(opts?: ShowtimeStartOptions): Promise<void>
  stop(): Promise<void>
  next(): Promise<void>
  prev(): Promise<void>
  pause(): Promise<void>
  state(): Promise<ShowtimeState>
  onState(cb: (state: ShowtimeState) => void): () => void
  onCue(cb: (cue: ShowtimeCue) => void): () => void
}
