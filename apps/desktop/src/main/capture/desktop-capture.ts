// desktopCapturer wrapper for the primary display. Findings (docs/OVERLAY_NOTES.md): getSources() sometimes returns
// [] on the first call after launch and has been seen to stall, so every attempt has a timeout and a retry.
import type { Display, NativeImage } from 'electron'

export class CaptureError extends Error {
  constructor(
    message: string,
    readonly code: 'permission' | 'no-source' | 'timeout',
  ) {
    super(message)
    this.name = 'CaptureError'
  }
}

const ATTEMPTS = 3
const ATTEMPT_TIMEOUT_MS = 3000
const RETRY_DELAY_MS = 150

export const PERMISSION_HINT =
  'Screen Recording permission is not granted. Open System Settings > Privacy & Security > Screen Recording, enable this app (Electron in development), then quit and reopen it.'

function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new CaptureError(`desktopCapturer.getSources timed out after ${ms} ms`, 'timeout')), ms)
    p.then(
      (v) => {
        clearTimeout(timer)
        resolve(v)
      },
      (e) => {
        clearTimeout(timer)
        reject(e)
      },
    )
  })
}

export async function captureDisplay(display: Display, size: { width: number; height: number }): Promise<NativeImage> {
  const { desktopCapturer, systemPreferences } = await import('electron')
  if (process.platform === 'darwin') {
    const status = systemPreferences.getMediaAccessStatus('screen')
    if (status === 'denied' || status === 'restricted') throw new CaptureError(PERMISSION_HINT, 'permission')
  }
  let lastError: unknown = null
  for (let attempt = 1; attempt <= ATTEMPTS; attempt++) {
    try {
      const sources = await withTimeout(desktopCapturer.getSources({ types: ['screen'], thumbnailSize: size }), ATTEMPT_TIMEOUT_MS)
      const source = sources.find((s) => s.display_id === String(display.id)) ?? sources[0]
      if (source && !source.thumbnail.isEmpty()) return source.thumbnail
      lastError = new CaptureError('desktopCapturer returned no screen source', 'no-source')
    } catch (err) {
      lastError = err
    }
    await new Promise((r) => setTimeout(r, RETRY_DELAY_MS))
  }
  if (lastError instanceof CaptureError && lastError.code === 'no-source' && process.platform === 'darwin') {
    throw new CaptureError(`No screen source available. ${PERMISSION_HINT}`, 'no-source')
  }
  throw lastError instanceof Error ? lastError : new Error(String(lastError))
}
