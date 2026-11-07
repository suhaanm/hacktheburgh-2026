/// <reference lib="dom" />
import type { WakeMatcherOptions, WakePersona } from './matcher'

// Why the spotter is not listening. Several can be active at once; it listens only when none are.
export type WakePauseReason = 'live' | 'tts' | 'muted' | 'disabled' | 'push-to-talk-only' | 'manual'

export interface WakeStatus {
  state: 'off' | 'starting' | 'listening' | 'reconnecting' | 'paused' | 'unavailable'
  // True only while audio is actually being sent to the recogniser. Drives DESIGN's ListeningLight.
  listening: boolean
  pausedFor: WakePauseReason[]
  // Privacy truth: while `listening`, microphone audio is streamed to Google (Gemini transcribe-live) to hear the name.
  cloud: true
  engine: 'gemini-transcribe-live'
  // Human-readable reason when `unavailable`/`reconnecting`; safe to show in the dock.
  detail?: string
}

export interface WakeEvent<Id extends string = string> {
  personaId: Id
  source: 'wake'
  // 1 for an exact configured phrase/alias, lower for a fuzzy hit.
  score: number
  // What the recogniser heard (name words only; the rest of the utterance is not exposed).
  heard: string
  // Anything said after the name in the same breath, normalised.
  trailing: string
  // Milliseconds from the start of the spotter's current audio stream (diagnostics only).
  atMs: number
}

export interface WakeToken {
  token: string
  model?: string
  expiresAt?: number
}

export interface WakeSettings {
  wakeEnabled: boolean
  pushToTalkOnly: boolean
  micMuted: boolean
}

// Source of 16 kHz mono PCM16 frames. Injectable so tests and the Node harness can feed files.
export interface WakeAudioSource {
  start(onPcm: (pcm: Int16Array) => void): Promise<void>
  stop(): void
}

export interface WakeEngineHandlers {
  onTranscript(text: string, final: boolean): void
  // `fatal` = the engine will not recover on its own (bad token, unsupported); the spotter surfaces `unavailable`.
  onError(error: Error, fatal: boolean): void
  onReady(): void
  // The server announced the connection will close soon; the spotter rotates to a fresh stream.
  onGoAway?(): void
}

// Streaming recogniser. The spotter owns reconnect policy; the engine only reports and exposes `send`.
export interface WakeEngine {
  start(): Promise<void>
  send(pcm: Int16Array): void
  stop(): void
}
export type WakeEngineFactory = (handlers: WakeEngineHandlers) => WakeEngine

export interface WakeSpotterOptions<Id extends string = string> {
  // Only wakePhrases/wakeAliases are read; pass PERSONA_LIST straight in.
  personas: readonly WakePersona<Id>[]
  onWake(event: WakeEvent<Id>): void
  onStatus?(status: WakeStatus): void
  // Mint a short-lived transcribe-live token via main (window.alongside.wake.getToken). Never an API key in a renderer.
  getToken?(): Promise<WakeToken>
  // Microphone stream; defaults to getUserMedia({audio}). The spotter releases it whenever it is not listening.
  getStream?(): Promise<MediaStream>
  settings?: Partial<WakeSettings>
  matcher?: WakeMatcherOptions
  // Test/Node hooks.
  createAudioSource?: () => WakeAudioSource
  createEngine?: WakeEngineFactory
  // Optional diagnostics hook; receives raw transcript text. Do not log or persist it in production.
  onDebug?(text: string, final: boolean): void
  prerollMs?: number
  // Ignore further hits for this long after a wake (default 4000).
  cooldownMs?: number
  // Keep capturing locally (no network) this long after `pause('live')`, so LIVE can take the pre-roll (default 6000).
  handoffMs?: number
  // An unchanged interim transcript counts as final after this long (default 1200).
  stableInterimMs?: number
  // Proactively reconnect before the 10-minute connection cap (default 540000).
  maxSessionMs?: number
}

export interface WakeSpotter<Id extends string = string> {
  start(): Promise<void>
  stop(): void
  pause(reason?: WakePauseReason): void
  resume(reason?: WakePauseReason): void
  dispose(): void
  // PCM16 16 kHz mono for roughly the 3 s before and just after the wake phrase; null if nothing is buffered.
  // Call once your Live session is connected; it also lets the spotter release the mic.
  takePreroll(): Int16Array | null
  setSettings(patch: Partial<WakeSettings>): void
  setPersonas(personas: readonly WakePersona<Id>[]): void
  getStatus(): WakeStatus
}
