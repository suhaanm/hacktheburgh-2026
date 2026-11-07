// Adapted from google-gemini/gemini-live-api-examples — gemini-live-ephemeral-tokens-websocket/frontend/mediaUtils.js (BaseVideoCapture 1 fps capture interval)
// 1 fps screen-frame sender with change gating. The Live API accepts at most 1 frame per second and, with the default
// turn coverage, every frame lands in context (about 70 tokens each), so an unchanged screen is sent at most every 5 s.
export interface FrameSample {
  jpegBase64: string
  changeScore: number
}

export interface FrameLoopOptions {
  grab: () => Promise<FrameSample | null>
  send: (jpegBase64: string) => void
  intervalMs?: number
  // changeScore at or below this counts as "nothing changed". Capture's score is a mean absolute luma difference on a 32x18 grid
  // (0..1): a lit-up button is about 0.001, a new window is above 0.05, a still screen with a blinking cursor is ~0.
  epsilon?: number
  // After the last change, keep sending at full rate this long so the model sees the screen settle.
  settleMs?: number
  // Never go longer than this without a frame.
  maxGapMs?: number
  now?: () => number
  onError?: (err: unknown) => void
}

// A frame the model cannot decode is fatal: the server closes the whole session with 1007 "invalid argument" the moment it
// generates a reply (reproduced with the mock capture's 1x1 JPEG). So refuse degenerate frames up front: not a JPEG, or smaller
// than MIN_FRAME_SIDE (what capture returns when screen recording is denied or the display is gone).
export const MIN_FRAME_SIDE = 64

export function jpegSize(base64: string): { width: number; height: number } | null {
  let bytes: Uint8Array
  try {
    const bin = atob(base64.slice(0, 4096))
    bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0))
  } catch {
    return null
  }
  if (bytes.length < 4 || bytes[0] !== 0xff || bytes[1] !== 0xd8) return null
  let i = 2
  while (i + 9 < bytes.length) {
    if (bytes[i] !== 0xff) {
      i++
      continue
    }
    const marker = bytes[i + 1]!
    if (marker === 0xd8 || marker === 0x01 || (marker >= 0xd0 && marker <= 0xd7) || marker === 0xff) {
      i += marker === 0xff ? 1 : 2
      continue
    }
    const isSof = marker >= 0xc0 && marker <= 0xcf && marker !== 0xc4 && marker !== 0xc8 && marker !== 0xcc
    if (isSof) return { height: (bytes[i + 5]! << 8) | bytes[i + 6]!, width: (bytes[i + 7]! << 8) | bytes[i + 8]! }
    i += 2 + ((bytes[i + 2]! << 8) | bytes[i + 3]!)
  }
  return null
}

export function isUsableFrame(base64: string): boolean {
  const size = jpegSize(base64)
  return !!size && size.width >= MIN_FRAME_SIDE && size.height >= MIN_FRAME_SIDE
}

// Pure decision function so the gating is unit-testable without timers.
export function shouldSendFrame(
  s: { now: number; changeScore: number; lastChangeAt: number; lastSentAt: number | null },
  cfg: { epsilon: number; settleMs: number; maxGapMs: number },
): boolean {
  if (s.lastSentAt === null) return true
  if (s.changeScore > cfg.epsilon) return true
  if (s.now - s.lastChangeAt <= cfg.settleMs) return true
  return s.now - s.lastSentAt >= cfg.maxGapMs
}

export class FrameLoop {
  private timer: ReturnType<typeof setInterval> | null = null
  private inflight = false
  private lastChangeAt: number
  private lastSentAt: number | null = null
  readonly stats = { sent: 0, skipped: 0, rejected: 0 }
  private readonly now: () => number
  private readonly cfg: { epsilon: number; settleMs: number; maxGapMs: number }

  constructor(private readonly o: FrameLoopOptions) {
    this.now = o.now ?? (() => Date.now())
    this.lastChangeAt = this.now()
    this.cfg = { epsilon: o.epsilon ?? 0.0008, settleMs: o.settleMs ?? 3000, maxGapMs: o.maxGapMs ?? 5000 }
  }

  start(): void {
    if (this.timer) return
    void this.tick()
    this.timer = setInterval(() => void this.tick(), this.o.intervalMs ?? 1000)
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer)
    this.timer = null
  }

  async tick(): Promise<void> {
    if (this.inflight) return
    this.inflight = true
    try {
      const frame = await this.o.grab()
      if (!frame || !frame.jpegBase64) return
      if (!isUsableFrame(frame.jpegBase64)) {
        if (this.stats.rejected++ === 0) this.o.onError?.(new Error('screen frame is not a usable JPEG (too small or corrupt); not sending frames like it'))
        return
      }
      const now = this.now()
      if (frame.changeScore > this.cfg.epsilon) this.lastChangeAt = now
      if (!shouldSendFrame({ now, changeScore: frame.changeScore, lastChangeAt: this.lastChangeAt, lastSentAt: this.lastSentAt }, this.cfg)) {
        this.stats.skipped++
        return
      }
      this.lastSentAt = now
      this.stats.sent++
      this.o.send(frame.jpegBase64)
    } catch (err) {
      this.o.onError?.(err)
    } finally {
      this.inflight = false
    }
  }
}
