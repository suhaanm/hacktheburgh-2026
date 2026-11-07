// Adapted from farzaa/clicky (MIT) — leanring-buddy/CompanionScreenCaptureUtility.swift (capture, JPEG sizing; own windows excluded from the shot)
// Real Capture service: primary display via desktopCapturer, sizing per purpose, a cheap change score, and a
// screen-change watcher. The overlay is excluded by content protection (see overlay-window.ts) or, in capturable
// mode, hidden around ground/verify grabs.
// electron is imported lazily so unit tests can import services.ts without Electron.
import { randomUUID } from 'node:crypto'
import type { Capture } from '../../shared/contracts'
import type { Shot, ShotPurpose } from '../../shared/protocol'
import type { ServiceContext } from '../context'
import { changeScore, grayGrid } from './change-score'
import { captureDisplay } from './desktop-capture'
import { withOverlayHidden } from './overlay-window'
import { PROFILES, targetSize } from './sizing'
import { ScreenChangeWatcher } from './watcher'

const WATCH_THUMB = { width: 128, height: 72 }

export function createCapture(ctx: ServiceContext): Capture {
  const inflight = new Map<ShotPurpose, Promise<Shot>>()
  let lastLiveGrid: Uint8Array | null = null

  async function grabNow(purpose: ShotPurpose): Promise<{ shot: Shot; grid: Uint8Array }> {
    const { screen } = await import('electron')
    const display = screen.getPrimaryDisplay()
    const size = targetSize(display.size, display.scaleFactor, purpose)
    const { value: image, hidden } = await withOverlayHidden(purpose !== 'live', () => captureDisplay(display, size))
    const { width, height } = image.getSize()
    const small = image.resize({ width: 64, height: 36, quality: 'good' })
    return {
      grid: grayGrid(small.toBitmap(), 64, 36, 'bgra'),
      shot: {
        id: randomUUID(),
        displayId: display.id,
        widthPx: width,
        heightPx: height,
        scaleFactor: display.scaleFactor,
        jpegBase64: image.toJPEG(PROFILES[purpose].quality).toString('base64'),
        takenAt: Date.now(),
        overlayHidden: hidden,
      },
    }
  }

  // Concurrent callers of the same purpose share one capture (the dock polls at 1 fps while tools also grab).
  function grab(purpose: ShotPurpose): Promise<Shot> {
    const existing = inflight.get(purpose)
    if (existing) return existing
    const p = grabNow(purpose)
      .then(({ shot, grid }) => {
        if (purpose === 'live') lastLiveGrid = grid
        return shot
      })
      .finally(() => inflight.delete(purpose))
    inflight.set(purpose, p)
    return p
  }

  const watcher = new ScreenChangeWatcher({
    async sample() {
      const { screen } = await import('electron')
      const display = screen.getPrimaryDisplay()
      const image = await captureDisplay(display, WATCH_THUMB)
      const { width, height } = image.getSize()
      return grayGrid(image.toBitmap(), width, height, 'bgra')
    },
  })

  return {
    grab,
    async liveFrame() {
      const { shot, grid } = await grabNow('live')
      const score = lastLiveGrid ? changeScore(lastLiveGrid, grid) : 0
      lastLiveGrid = grid
      return { jpegBase64: shot.jpegBase64, changeScore: score }
    },
    watch(on) {
      return watcher.subscribe((score) => {
        ctx.bus.emit('screen:changed', { score })
        on(score)
      })
    },
  }
}
