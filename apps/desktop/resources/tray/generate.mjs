// Regenerates the menu-bar template icons (`node resources/tray/generate.mjs`). No dependencies.
// macOS "template" images are black + alpha only; the system tints them for light and dark menu bars.
// Each icon is drawn from distance functions at 6x supersampling, so edges stay crisp at 22 px and 44 px (@2x).
import { deflateSync } from 'node:zlib'
import { writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const SIZE = 22 // points; the @2x file is 44 px
const SS = 6

const ring = (d, r, w) => Math.abs(d - r) - w / 2 // signed distance to a ring of radius r and stroke w (<0 inside)
const segment = (px, py, ax, ay, bx, by) => {
  const abx = bx - ax
  const aby = by - ay
  const t = Math.max(0, Math.min(1, ((px - ax) * abx + (py - ay) * aby) / (abx * abx + aby * aby)))
  return Math.hypot(px - (ax + t * abx), py - (ay + t * aby))
}

// Returns 0..1 coverage at a point in points (origin top-left).
// The mark is a ring with a small orb beside it: a companion alongside you.
const CX = 9.6
const CY = 12
const orb = (x, y, r = 2.7) => Math.hypot(x - 17.4, y - 6.2) - r
const SHAPES = {
  // Resting: open ring, small orb; a thin gap keeps the orb from touching the ring.
  idle: (x, y) => {
    const d = Math.hypot(x - CX, y - CY)
    if (orb(x, y) < 0) return 1
    if (orb(x, y, 4.1) < 0) return 0
    return ring(d, 6.9, 1.9) < 0 ? 1 : 0
  },
  // Listening or talking: the ring fills in.
  live: (x, y) => {
    const d = Math.hypot(x - CX, y - CY)
    if (orb(x, y) < 0) return 1
    if (orb(x, y, 4.1) < 0) return 0
    return d - 7.8 < 0 ? 1 : 0
  },
  // Microphone muted: the ring with a slash through it, no orb.
  muted: (x, y) => {
    const d = Math.hypot(x - CX, y - CY)
    const slash = segment(x, y, 3.6, 5.6, 15.6, 18.4)
    if (slash < 1.0) return 1
    if (slash < 2.4) return 0
    return ring(d, 6.9, 1.9) < 0 ? 1 : 0
  },
}

function crc32(buf) {
  let c
  const table = []
  for (let n = 0; n < 256; n++) {
    c = n
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    table[n] = c >>> 0
  }
  let crc = 0xffffffff
  for (const b of buf) crc = table[(crc ^ b) & 0xff] ^ (crc >>> 8)
  return (crc ^ 0xffffffff) >>> 0
}

function chunk(type, data) {
  const out = Buffer.alloc(12 + data.length)
  out.writeUInt32BE(data.length, 0)
  out.write(type, 4, 'ascii')
  data.copy(out, 8)
  out.writeUInt32BE(crc32(out.subarray(4, 8 + data.length)), 8 + data.length)
  return out
}

function png(width, height, rgba) {
  const header = Buffer.alloc(13)
  header.writeUInt32BE(width, 0)
  header.writeUInt32BE(height, 4)
  header[8] = 8
  header[9] = 6 // RGBA
  const rows = Buffer.alloc((width * 4 + 1) * height)
  for (let y = 0; y < height; y++) {
    rows[y * (width * 4 + 1)] = 0
    rgba.copy(rows, y * (width * 4 + 1) + 1, y * width * 4, (y + 1) * width * 4)
  }
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk('IHDR', header), chunk('IDAT', deflateSync(rows, { level: 9 })), chunk('IEND', Buffer.alloc(0))])
}

function render(shape, scale) {
  const px = SIZE * scale
  const rgba = Buffer.alloc(px * px * 4)
  for (let y = 0; y < px; y++) {
    for (let x = 0; x < px; x++) {
      let hit = 0
      for (let sy = 0; sy < SS; sy++) {
        for (let sx = 0; sx < SS; sx++) hit += shape((x + (sx + 0.5) / SS) / scale, (y + (sy + 0.5) / SS) / scale)
      }
      const o = (y * px + x) * 4
      rgba[o + 3] = Math.round((hit / (SS * SS)) * 255) // black, alpha only
    }
  }
  return { px, rgba }
}

const names = { idle: 'trayTemplate', live: 'trayLiveTemplate', muted: 'trayMutedTemplate' }
for (const [key, shape] of Object.entries(SHAPES)) {
  for (const scale of [1, 2]) {
    const { px, rgba } = render(shape, scale)
    writeFileSync(join(HERE, `${names[key]}${scale === 2 ? '@2x' : ''}.png`), png(px, px, rgba))
  }
}

// Optional preview: `node generate.mjs preview out.png` composites each icon at 8x on a light and a dark bar.
if (process.argv[2] === 'preview' && process.argv[3]) {
  const keys = Object.keys(SHAPES)
  const cell = 22 * 8
  const w = cell * keys.length
  const h = cell * 2
  const buf = Buffer.alloc(w * h * 4)
  keys.forEach((key, i) => {
    const { px, rgba } = render(SHAPES[key], 8)
    for (let y = 0; y < px; y++) {
      for (let x = 0; x < px; x++) {
        const a = rgba[(y * px + x) * 4 + 3] / 255
        for (const [row, bg, fg] of [[0, 236, 20], [1, 40, 240]]) {
          const v = Math.round(bg * (1 - a) + fg * a)
          const o = ((row * cell + y) * w + i * cell + x) * 4
          buf[o] = buf[o + 1] = buf[o + 2] = v
          buf[o + 3] = 255
        }
      }
    }
  })
  writeFileSync(process.argv[3], png(w, h, buf))
}
