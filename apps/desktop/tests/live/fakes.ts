// Test doubles for LiveSession: a scriptable WebSocket and in-memory audio IO.
import type { AudioInput, AudioOutput } from '../../src/renderer/live/types'

export class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  static reset(): void {
    FakeWebSocket.instances = []
  }
  readyState = 0
  binaryType = 'blob'
  sent: Array<Record<string, unknown>> = []
  closedWith: { code?: number; reason?: string } | null = null
  private listeners: Record<string, Array<(ev: unknown) => void>> = {}
  // Set to false to hold back the automatic setupComplete.
  static autoSetup = true
  // New sockets close right after opening (an unreachable server).
  static failOpen = false

  constructor(public url: string) {
    FakeWebSocket.instances.push(this)
    queueMicrotask(() => {
      this.readyState = 1
      this.emit('open', {})
      if (FakeWebSocket.failOpen) this.close(1006, 'unreachable')
    })
  }

  addEventListener(type: string, cb: (ev: unknown) => void): void {
    ;(this.listeners[type] ??= []).push(cb)
  }

  send(data: string): void {
    const m = JSON.parse(data) as Record<string, unknown>
    this.sent.push(m)
    if (m.setup && FakeWebSocket.autoSetup) queueMicrotask(() => this.readyState === 1 && this.serverSend({ setupComplete: {} }))
  }

  close(code?: number, reason?: string): void {
    if (this.readyState === 3) return
    this.readyState = 3
    this.closedWith = { code, reason }
    queueMicrotask(() => this.emit('close', { code: code ?? 1005, reason: reason ?? '' }))
  }

  serverSend(obj: unknown): void {
    this.emit('message', { data: JSON.stringify(obj) })
  }

  // Simulate the network dropping.
  drop(code = 1006): void {
    this.readyState = 3
    this.emit('close', { code, reason: 'drop' })
  }

  private emit(type: string, ev: unknown): void {
    for (const cb of this.listeners[type] ?? []) cb(ev)
  }

  get realtime(): Array<Record<string, unknown>> {
    return this.sent.filter((m) => m.realtimeInput).map((m) => m.realtimeInput as Record<string, unknown>)
  }
  get toolResponses(): Array<Record<string, unknown>> {
    return this.sent.flatMap((m) => ((m.toolResponse as { functionResponses?: Array<Record<string, unknown>> } | undefined)?.functionResponses ?? []))
  }
  get setups(): Array<Record<string, unknown>> {
    return this.sent.filter((m) => m.setup).map((m) => m.setup as Record<string, unknown>)
  }
}

export class FakeMic implements AudioInput {
  push: ((b64: string, level: number) => void) | null = null
  stopped = false
  starts = 0
  failStart = false
  async start(onChunk: (b64: string, level: number) => void): Promise<void> {
    this.starts++
    if (this.failStart) throw new DOMException('Permission denied', 'NotAllowedError')
    this.stopped = false
    this.push = onChunk
  }
  stop(): void {
    this.stopped = true
  }
}

export class FakeSpeaker implements AudioOutput {
  played: string[] = []
  flushes = 0
  playing = false
  closed = false
  private idleCbs = new Set<() => void>()
  async init(): Promise<void> {}
  play(b64: string): void {
    this.played.push(b64)
    this.playing = true
  }
  flush(): void {
    this.flushes++
    this.playing = false
  }
  level(): number {
    return this.playing ? 0.3 : 0
  }
  isPlaying(): boolean {
    return this.playing
  }
  onIdle(cb: () => void): () => void {
    this.idleCbs.add(cb)
    return () => this.idleCbs.delete(cb)
  }
  drain(): void {
    this.playing = false
    for (const cb of this.idleCbs) cb()
  }
  close(): void {
    this.closed = true
  }
}

export const tick = (ms = 0) => new Promise<void>((r) => setTimeout(r, ms))

// Smallest header-valid JPEG of a given size (SOI, SOF0, EOI): passes the frame size check, never decoded in tests.
export function headerJpeg(width = 1280, height = 720): string {
  const sof = [0xff, 0xc0, 0x00, 0x11, 0x08, height >> 8, height & 255, width >> 8, width & 255, 0x03, 1, 0x22, 0, 2, 0x11, 1, 3, 0x11, 1]
  return btoa(String.fromCharCode(0xff, 0xd8, ...sof, 0xff, 0xd9))
}
