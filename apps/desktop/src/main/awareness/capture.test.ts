import fs from 'node:fs'
import { describe, expect, it, vi, afterEach } from 'vitest'
import { CaptureError, FRAME_JPEG_QUALITY, FRAME_MAX_EDGE, SCREEN_PERMISSION_INSTRUCTION, captureFrame, createDesktopFrameSource, encodeFrame, scaleToLongEdge, sha256Prefix } from './capture'
import { FakeImage, createFakeFrameSource, makePng, pngSize } from './capture-fake'

afterEach(() => vi.restoreAllMocks())

describe('scaleToLongEdge', () => {
  it('limits the long edge to 1280 and keeps the aspect ratio; never upscales', () => {
    expect(scaleToLongEdge(2880, 1800)).toEqual({ width: 1280, height: 800 })
    expect(scaleToLongEdge(1800, 2880)).toEqual({ width: 800, height: 1280 })
    expect(scaleToLongEdge(1280, 720)).toEqual({ width: 1280, height: 720 })
    expect(scaleToLongEdge(800, 600)).toEqual({ width: 800, height: 600 })
    expect(scaleToLongEdge(1, 5000)).toEqual({ width: 1, height: 1280 })
    expect(scaleToLongEdge(0, 0)).toEqual({ width: 1, height: 1 })
  })
})

describe('the PNG fixture and the fake source', () => {
  it('makePng is a real PNG header with the requested size', () => {
    const png = makePng(320, 200)
    expect([...png.subarray(0, 8)]).toEqual([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])
    expect(pngSize(png)).toEqual({ width: 320, height: 200 })
    expect(() => pngSize(Buffer.from('nope'))).toThrow()
  })

  it('encodeFrame downsizes a retina frame to 1280 on the long edge and encodes JPEG at quality 70', async () => {
    const src = createFakeFrameSource({ width: 2880, height: 1800 })
    const frame = await captureFrame(src)
    expect({ w: frame.width, h: frame.height }).toEqual({ w: 1280, h: 800 })
    expect(src.images[0].resizes).toEqual([{ width: 1280, height: 800 }])
    expect(src.images[0].qualities).toEqual([FRAME_JPEG_QUALITY])
    expect(FRAME_JPEG_QUALITY).toBe(70)
    expect(FRAME_MAX_EDGE).toBe(1280)
    expect(frame.jpeg[0]).toBe(0xff)
    expect(frame.jpeg[1]).toBe(0xd8)
    expect(frame.bytes).toBe(frame.jpeg.length)
    expect(frame.sha256_prefix).toMatch(/^[0-9a-f]{12}$/)
    expect(frame.sha256_prefix).toBe(sha256Prefix(frame.jpeg))
    frame.release()
  })

  it('the fake JPEG carries its real size in a baseline SOF segment, so the engine header check accepts it', async () => {
    const frame = await captureFrame(createFakeFrameSource({ width: 2880, height: 1800 }))
    const j = frame.jpeg
    const i = j.indexOf(Buffer.from([0xff, 0xc0]))
    expect(i).toBeGreaterThan(2)
    expect({ h: j.readUInt16BE(i + 5), w: j.readUInt16BE(i + 7) }).toEqual({ h: frame.height, w: frame.width })
    frame.release()
  })

  it('a small frame is not resized', async () => {
    const src = createFakeFrameSource({ width: 800, height: 500 })
    const frame = await captureFrame(src)
    expect(src.images[0].resizes).toEqual([])
    expect({ w: frame.width, h: frame.height }).toEqual({ w: 800, h: 500 })
    frame.release()
  })

  it('release zeroes the JPEG and is safe to call twice', async () => {
    const frame = await captureFrame(createFakeFrameSource({ width: 640, height: 400 }))
    const view = frame.jpeg
    expect(view.some((b) => b !== 0)).toBe(true)
    frame.release()
    expect(frame.released()).toBe(true)
    expect(view.every((b) => b === 0)).toBe(true)
    expect(() => frame.release()).not.toThrow()
  })

  it('an empty image or a failing source is a CaptureError, not a frame', async () => {
    expect(() => encodeFrame(new FakeImage(makePng(1, 1), { width: 0, height: 0 }))).toThrow(CaptureError)
    await expect(captureFrame(createFakeFrameSource({ failWith: new CaptureError('nope', 'no-source') }))).rejects.toBeInstanceOf(CaptureError)
  })
})

describe('no capture call writes to disk', () => {
  it('spies on every fs write path during a capture and an encode', async () => {
    const spies = [
      vi.spyOn(fs, 'writeFile'),
      vi.spyOn(fs, 'writeFileSync'),
      vi.spyOn(fs, 'appendFile'),
      vi.spyOn(fs, 'appendFileSync'),
      vi.spyOn(fs, 'createWriteStream'),
      vi.spyOn(fs, 'writeSync'),
      vi.spyOn(fs, 'mkdirSync'),
      vi.spyOn(fs.promises, 'writeFile'),
      vi.spyOn(fs.promises, 'appendFile'),
    ]
    const frame = await captureFrame(createFakeFrameSource({ width: 2880, height: 1800 }))
    frame.release()
    for (const s of spies) expect(s).not.toHaveBeenCalled()
  })
})

describe('the real source (logic only; the build agent never reads a real screen)', () => {
  it('refuses without asking when Screen Recording is not granted, and never touches the capture function', async () => {
    for (const status of ['denied', 'restricted', 'not-determined', 'unknown'] as const) {
      const capture = vi.fn()
      const src = createDesktopFrameSource({ screenStatus: async () => status, getDisplay: async () => ({ id: 1, size: { width: 1440, height: 900 }, scaleFactor: 2 }), capture })
      await expect(src.grab()).rejects.toMatchObject({ code: 'permission', message: SCREEN_PERMISSION_INSTRUCTION })
      expect(capture).not.toHaveBeenCalled()
    }
  })

  it('when granted, asks for the final size straight away (long edge at most 1280), on the display it was given', async () => {
    const sizes: Array<{ width: number; height: number }> = []
    const src = createDesktopFrameSource({
      screenStatus: async () => 'granted',
      getDisplay: async () => ({ id: 7, size: { width: 1440, height: 900 }, scaleFactor: 2 }),
      capture: async (display, size) => {
        sizes.push(size)
        expect(display.id).toBe(7)
        return new FakeImage(makePng(size.width, size.height), size)
      },
    })
    expect(src.kind).toBe('desktop')
    const frame = await captureFrame(src)
    expect(sizes).toEqual([{ width: 1280, height: 800 }])
    expect(frame.width).toBeLessThanOrEqual(1280)
    frame.release()
  })
})
