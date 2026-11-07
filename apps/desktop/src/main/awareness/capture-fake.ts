// A fake FrameSource for tests and mock mode: a PNG fixture built in memory (no file is read or written), wrapped in an ImageLike that
// reports the PNG's own size, "resizes" by recording the requested size, and "encodes" to deterministic JPEG-looking bytes. No Electron.
import { createHash } from 'node:crypto'
import { deflateSync } from 'node:zlib'
import type { FrameSource, ImageLike } from './capture'

const crcTable = (() => {
  const t = new Uint32Array(256)
  for (let n = 0; n < 256; n++) {
    let c = n
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    t[n] = c >>> 0
  }
  return t
})()

function crc32(buf: Buffer): number {
  let c = 0xffffffff
  for (const b of buf) c = crcTable[(c ^ b) & 0xff] ^ (c >>> 8)
  return (c ^ 0xffffffff) >>> 0
}

function chunk(type: string, data: Buffer): Buffer {
  const len = Buffer.alloc(4)
  len.writeUInt32BE(data.length)
  const body = Buffer.concat([Buffer.from(type, 'ascii'), data])
  const crc = Buffer.alloc(4)
  crc.writeUInt32BE(crc32(body))
  return Buffer.concat([len, body, crc])
}

/** A solid grey 8-bit PNG of the given size (valid file; small once compressed). */
export function makePng(width: number, height: number, grey = 200): Buffer {
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(width, 0)
  ihdr.writeUInt32BE(height, 4)
  ihdr[8] = 8 // bit depth
  ihdr[9] = 0 // grey
  const row = Buffer.alloc(width + 1, grey)
  row[0] = 0 // filter: none
  const raw = Buffer.alloc((width + 1) * height)
  for (let y = 0; y < height; y++) row.copy(raw, y * (width + 1))
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk('IHDR', ihdr), chunk('IDAT', deflateSync(raw)), chunk('IEND', Buffer.alloc(0))])
}

export function pngSize(png: Buffer): { width: number; height: number } {
  if (png.length < 24 || png.toString('ascii', 12, 16) !== 'IHDR') throw new Error('not a PNG')
  return { width: png.readUInt32BE(16), height: png.readUInt32BE(20) }
}

export class FakeImage implements ImageLike {
  readonly resizes: Array<{ width: number; height: number }> = []
  readonly qualities: number[] = []

  constructor(
    private readonly png: Buffer,
    private size = pngSize(png),
    private readonly parent: FakeImage | null = null,
  ) {}

  isEmpty(): boolean {
    return this.size.width === 0 || this.size.height === 0
  }

  getSize(): { width: number; height: number } {
    return { ...this.size }
  }

  resize(opts: { width: number; height: number }): ImageLike {
    const child = new FakeImage(this.png, { width: opts.width, height: opts.height }, this)
    this.resizes.push({ width: opts.width, height: opts.height })
    return child
  }

  toJPEG(quality: number): Buffer {
    ;(this.parent ?? this).qualities.push(quality)
    const h = createHash('sha256').update(this.png).update(`${this.size.width}x${this.size.height}q${quality}`).digest()
    // SOI, APP0 "JFIF", a body whose length follows the pixel count a little (so a smaller frame is smaller), EOI.
    const body = Buffer.alloc(Math.max(64, Math.round((this.size.width * this.size.height) / 400)))
    h.copy(body)
    return Buffer.concat([Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10, 0x4a, 0x46, 0x49, 0x46, 0x00]), body, Buffer.from([0xff, 0xd9])])
  }
}

export interface FakeFrameSource extends FrameSource {
  readonly grabs: () => number
  /** The images handed out so far (to inspect the requested resize and JPEG quality). */
  readonly images: FakeImage[]
}

export function createFakeFrameSource(opts: { png?: Buffer; width?: number; height?: number; failWith?: Error } = {}): FakeFrameSource {
  const png = opts.png ?? makePng(opts.width ?? 2880, opts.height ?? 1800)
  const images: FakeImage[] = []
  let n = 0
  return {
    kind: 'fake',
    grabs: () => n,
    images,
    async grab() {
      n++
      if (opts.failWith) throw opts.failWith
      const img = new FakeImage(png)
      images.push(img)
      return img
    },
  }
}
