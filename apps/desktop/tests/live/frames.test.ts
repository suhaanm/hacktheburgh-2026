import { describe, expect, it } from 'vitest'
import { FrameLoop, isUsableFrame, jpegSize, shouldSendFrame } from '../../src/renderer/live/frames'

const cfg = { epsilon: 0.003, settleMs: 3000, maxGapMs: 5000 }

describe('shouldSendFrame', () => {
  it('always sends the first frame and any changed frame', () => {
    expect(shouldSendFrame({ now: 0, changeScore: 0, lastChangeAt: 0, lastSentAt: null }, cfg)).toBe(true)
    expect(shouldSendFrame({ now: 1000, changeScore: 0.2, lastChangeAt: 1000, lastSentAt: 0 }, cfg)).toBe(true)
  })

  it('keeps sending for settleMs after the last change, then drops to one per maxGapMs', () => {
    const at = (now: number, lastSentAt: number) => shouldSendFrame({ now, changeScore: 0, lastChangeAt: 0, lastSentAt }, cfg)
    expect(at(2000, 1000)).toBe(true) // still settling
    expect(at(3500, 2500)).toBe(false) // quiet >3s, sent 1s ago
    expect(at(6000, 2500)).toBe(false) // 3.5s since last sent
    expect(at(7600, 2500)).toBe(true) // >=5s since last sent: always at least one
  })
})

describe('FrameLoop', () => {
  it('skips unchanged frames, never overlaps grabs, and reports errors without dying', async () => {
    let now = 0
    const sent: number[] = []
    const errors: unknown[] = []
    let score = 0.5
    let fail = false
    const loop = new FrameLoop({
      grab: async () => {
        if (fail) throw new Error('capture down')
        return { jpegBase64: fakeJpeg(1280, 720), changeScore: score }
      },
      send: () => sent.push(now),
      now: () => now,
      onError: (e) => errors.push(e),
    })
    await loop.tick()
    score = 0
    now = 1000
    await loop.tick()
    now = 5000
    await loop.tick() // quiet for 5s since the change at t=0, sent at 1000 -> 4s gap -> skip
    expect(sent).toEqual([0, 1000])
    now = 6500
    await loop.tick() // 5.5s since last send
    expect(sent).toEqual([0, 1000, 6500])
    fail = true
    await loop.tick()
    expect(errors).toHaveLength(1)
    expect(loop.stats.skipped).toBe(1)
  })
})

// Minimal JPEG: SOI, APP0, SOF0 with the given size, EOI. Enough for header parsing.
function fakeJpeg(width: number, height: number, sof = 0xc0): string {
  const app0 = [0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46, 0x49, 0x46, 0x00, 0x01, 0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00]
  const sofSeg = [0xff, sof, 0x00, 0x11, 0x08, height >> 8, height & 255, width >> 8, width & 255, 0x03, 1, 0x22, 0, 2, 0x11, 1, 3, 0x11, 1]
  const bytes = new Uint8Array([0xff, 0xd8, ...app0, ...sofSeg, 0xff, 0xd9])
  return btoa(String.fromCharCode(...bytes))
}

describe('frame validation (a 1x1 mock JPEG made the server close the session with 1007)', () => {
  it('reads JPEG dimensions from baseline and progressive headers', () => {
    expect(jpegSize(fakeJpeg(1280, 720))).toEqual({ width: 1280, height: 720 })
    expect(jpegSize(fakeJpeg(640, 360, 0xc2))).toEqual({ width: 640, height: 360 })
    expect(jpegSize('not base64 !!')).toBeNull()
    expect(jpegSize(btoa('plain text, not an image'))).toBeNull()
  })

  it('accepts real screen sizes and refuses tiny or corrupt frames', () => {
    expect(isUsableFrame(fakeJpeg(1280, 720))).toBe(true)
    expect(isUsableFrame(fakeJpeg(1, 1, 0xc2))).toBe(false)
    expect(isUsableFrame(fakeJpeg(1280, 8))).toBe(false)
    expect(isUsableFrame('')).toBe(false)
    // The exact 1x1 progressive JPEG from the mock capture.
    expect(isUsableFrame('/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA=')).toBe(false)
  })

  it('FrameLoop never sends an unusable frame and reports it once', async () => {
    const sent: string[] = []
    const errors: unknown[] = []
    const loop = new FrameLoop({ grab: async () => ({ jpegBase64: fakeJpeg(1, 1), changeScore: 1 }), send: (j) => sent.push(j), onError: (e) => errors.push(e) })
    await loop.tick()
    await loop.tick()
    expect(sent).toEqual([])
    expect(errors).toHaveLength(1)
    expect(loop.stats.rejected).toBe(2)
  })
})
