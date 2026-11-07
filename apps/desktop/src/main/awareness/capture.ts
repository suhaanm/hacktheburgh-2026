// One frame of the screen for one glance (AWR-2). The rules, all in this file and tested:
//   - the frame is downscaled to a long edge of at most 1280 px and encoded as JPEG quality 70;
//   - it lives in memory for the length of one call and is zeroed after it (FrameHandle.release);
//   - nothing here writes to disk or to a log; no function takes a path.
// `FrameSource` is the port. capture-fake.ts has a fake (a PNG fixture). `createDesktopFrameSource` is the real one: Electron's
// desktopCapturer, which needs the macOS Screen Recording permission. The worker grants that permission; this code never asks for it
// (it reads the status and refuses unless it is "granted", so no prompt can appear from here), and it has not been run against a real
// screen by the build agent.
import { createHash } from 'node:crypto'
import { captureDisplay, CaptureError } from '../capture/desktop-capture'
import type { Frame } from './types'

export { CaptureError }

export const FRAME_MAX_EDGE = 1280
export const FRAME_JPEG_QUALITY = 70

// The part of Electron's NativeImage this module uses, so a fake can stand in.
export interface ImageLike {
  isEmpty(): boolean
  getSize(): { width: number; height: number }
  resize(opts: { width: number; height: number; quality?: 'good' | 'better' | 'best' }): ImageLike
  toJPEG(quality: number): Buffer
}

export interface FrameSource {
  readonly kind: 'fake' | 'desktop'
  /** One image of the display the cursor is on, in memory. Rejects with CaptureError ('permission', 'no-source', 'timeout') or another Error. */
  grab(): Promise<ImageLike>
}

export interface FrameHandle extends Frame {
  /** Zeroes the JPEG bytes. Call it when the call is over, in a finally. Safe to call twice. */
  release(): void
  released(): boolean
}

/** Largest size with the same aspect ratio whose long edge is at most `maxEdge`. Never upscales; at least 1 px each way. */
export function scaleToLongEdge(width: number, height: number, maxEdge = FRAME_MAX_EDGE): { width: number; height: number } {
  const w = Math.max(1, Math.round(width))
  const h = Math.max(1, Math.round(height))
  const long = Math.max(w, h)
  if (long <= maxEdge) return { width: w, height: h }
  const k = maxEdge / long
  return { width: Math.max(1, Math.round(w * k)), height: Math.max(1, Math.round(h * k)) }
}

export function sha256Prefix(buf: Buffer, n = 12): string {
  return createHash('sha256').update(buf).digest('hex').slice(0, n)
}

/** Downscale and encode an image. Pure apart from the image object; no I/O. */
export function encodeFrame(img: ImageLike): FrameHandle {
  if (img.isEmpty()) throw new CaptureError('the screen image was empty', 'no-source')
  const { width, height } = img.getSize()
  const target = scaleToLongEdge(width, height)
  const scaled = target.width === width && target.height === height ? img : img.resize({ width: target.width, height: target.height, quality: 'good' })
  const jpeg = scaled.toJPEG(FRAME_JPEG_QUALITY)
  if (jpeg.length === 0) throw new CaptureError('the screen image could not be encoded', 'no-source')
  let released = false
  return {
    jpeg,
    width: target.width,
    height: target.height,
    bytes: jpeg.length,
    sha256_prefix: sha256Prefix(jpeg),
    release() {
      if (released) return
      jpeg.fill(0)
      released = true
    },
    released: () => released,
  }
}

/** Grab and encode one frame. The caller owns the handle and must release it. */
export async function captureFrame(source: FrameSource): Promise<FrameHandle> {
  const img = await source.grab()
  return encodeFrame(img)
}

// ------------------------------------------------------------------------------------------------ real source (Electron)
export interface DisplayLike {
  id: number
  size: { width: number; height: number }
  scaleFactor: number
}

export interface DesktopFrameSourceDeps {
  // The display the cursor is on. Default: screen.getDisplayNearestPoint(screen.getCursorScreenPoint()).
  getDisplay?: () => Promise<DisplayLike>
  // macOS Screen Recording status without prompting. Default: systemPreferences.getMediaAccessStatus('screen').
  screenStatus?: () => Promise<'granted' | 'denied' | 'restricted' | 'not-determined' | 'unknown'>
  // Default: the existing desktopCapturer wrapper (retries, timeouts).
  capture?: (display: DisplayLike, size: { width: number; height: number }) => Promise<ImageLike>
}

export const SCREEN_PERMISSION_INSTRUCTION =
  'Screen Recording is not allowed for this app. Open System Settings > Privacy & Security > Screen Recording, switch on this app (Electron while developing), then quit and reopen it.'

export function createDesktopFrameSource(deps: DesktopFrameSourceDeps = {}): FrameSource {
  const getDisplay =
    deps.getDisplay ??
    (async () => {
      const { screen } = await import('electron')
      return screen.getDisplayNearestPoint(screen.getCursorScreenPoint()) as DisplayLike
    })
  const screenStatus =
    deps.screenStatus ??
    (async () => {
      if (process.platform !== 'darwin') return 'granted'
      const { systemPreferences } = await import('electron')
      return systemPreferences.getMediaAccessStatus('screen')
    })
  const capture = deps.capture ?? (async (display, size) => (await captureDisplay(display as never, size)) as unknown as ImageLike)

  return {
    kind: 'desktop',
    async grab() {
      // Never ask: a request would raise the macOS prompt, and granting it is the worker's act, not this code's.
      if ((await screenStatus()) !== 'granted') throw new CaptureError(SCREEN_PERMISSION_INSTRUCTION, 'permission')
      const display = await getDisplay()
      const physW = Math.max(1, Math.round(display.size.width * display.scaleFactor))
      const physH = Math.max(1, Math.round(display.size.height * display.scaleFactor))
      // Ask for the final size straight away, so a full-resolution retina image is never held.
      return capture(display, scaleToLongEdge(physW, physH))
    },
  }
}
