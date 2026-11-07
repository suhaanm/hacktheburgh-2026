// Frames for the voice session: one screen frame, long edge at most 1024 px, JPEG, in memory only, zeroed after use. Built on the awareness
// layer's FrameSource (Electron's desktopCapturer, which needs the Screen Recording permission the worker grants; this code never asks: the
// source reads the status and refuses unless it is "granted"). Nothing is written to disk and no function here takes a path.
import { CaptureError, scaleToLongEdge, type FrameSource, type ImageLike } from '../awareness/capture'
import type { LiveFrame } from './egress'
import type { FrameProvider } from './session'

export const LIVE_FRAME_MAX_EDGE = 1024
export const LIVE_FRAME_JPEG_QUALITY = 60

export function encodeLiveFrame(img: ImageLike, maxEdge = LIVE_FRAME_MAX_EDGE): LiveFrame {
  if (img.isEmpty()) throw new CaptureError('the screen image was empty', 'no-source')
  const { width, height } = img.getSize()
  const target = scaleToLongEdge(width, height, maxEdge)
  const scaled = target.width === width && target.height === height ? img : img.resize({ width: target.width, height: target.height, quality: 'good' })
  const jpeg = scaled.toJPEG(LIVE_FRAME_JPEG_QUALITY)
  if (jpeg.length === 0) throw new CaptureError('the screen image could not be encoded', 'no-source')
  let released = false
  return {
    jpeg,
    width: target.width,
    height: target.height,
    capturedAt: Date.now(),
    release() {
      if (released) return
      jpeg.fill(0)
      released = true
    },
  }
}

export function createFrameProvider(source: FrameSource, maxEdge = LIVE_FRAME_MAX_EDGE): FrameProvider {
  return {
    async grab() {
      try {
        return encodeLiveFrame(await source.grab(), maxEdge)
      } catch {
        return null // no permission, no display, a failed encode: that frame is skipped
      }
    },
  }
}
