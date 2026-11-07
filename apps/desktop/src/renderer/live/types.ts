// Types local to the Live renderer module. Shared domain types come from src/shared (imported type-only elsewhere).
import type { LiveAuth } from './wire'

// 'idle' = not started. The dock maps these onto CompanionState.phase / LiveStatus.phase.
export type LivePhase = 'idle' | 'connecting' | 'live' | 'thinking' | 'speaking' | 'error' | 'ended'
export type LiveEndReason = 'idle' | 'goodbye' | 'stop' | 'error' | 'replaced'
export type TranscriptRole = 'user' | 'assistant'

export interface TranscriptEvent {
  role: TranscriptRole
  // Accumulated text of the current turn (replace, not append).
  text: string
  final: boolean
}

export interface ToolCallRequest {
  id: string
  name: string
  args: Record<string, unknown>
}

// Must resolve with the tool result (or { error } ); the signal aborts when the server cancels the call (barge-in) or the session stops.
export type ToolHandler = (call: ToolCallRequest, signal: AbortSignal) => Promise<unknown>

export interface LiveHost {
  getAuth(): Promise<LiveAuth>
  systemInstruction(): Promise<string>
}

export interface AudioInput {
  // Chunks are base64 PCM16 mono 16 kHz, ~32 ms; level is RMS 0..1.
  start(onChunk: (base64Pcm16: string, level: number) => void): Promise<void>
  stop(): void
}

export interface AudioOutput {
  init(): Promise<void>
  // Base64 PCM16 mono 24 kHz, queued gaplessly.
  play(base64Pcm16: string): void
  // Drops everything queued, immediately.
  flush(): void
  // Smoothed output RMS 0..1 for the orb.
  level(): number
  isPlaying(): boolean
  // Fires each time the queue drains to empty.
  onIdle(cb: () => void): () => void
  close(): void
}

export interface LiveSessionEvents {
  transcript: TranscriptEvent
  state: { phase: LivePhase; connected: boolean; reconnecting: boolean }
  toolCall: ToolCallRequest
  toolDone: { id: string; name: string; ms: number; error?: string; cancelled?: boolean }
  error: { message: string; fatal: boolean }
  ended: { reason: LiveEndReason }
  // Non-fatal happenings worth logging; never shown to the learner.
  notice: { kind: 'echo_guard' | 'mic_unavailable'; message: string }
  resumption: { handle: string | null; reconnected: boolean; resumed: boolean }
  // Per model turn: time from the last user audio above the noise floor (or an injected text) to the first model audio chunk.
  metrics: { kind: 'ttfa'; ms: number; trigger: 'voice' | 'text' } | { kind: 'setup'; ms: number } | { kind: 'usage'; totalTokens: number }
}

export type LiveEventName = keyof LiveSessionEvents
