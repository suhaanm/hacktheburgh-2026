// Cheap "did the screen change?" signal: downsample to 32x18 grayscale and take the mean absolute difference.
// Pure functions over raw pixel buffers so they are unit-testable without Electron.
export const GRID_W = 32
export const GRID_H = 18
export type PixelOrder = 'bgra' | 'rgba'

// Box-average the image into a GRID_W x GRID_H luma grid (Rec. 601). Samples at most ~6x6 pixels per cell.
export function grayGrid(pixels: Uint8Array, width: number, height: number, order: PixelOrder = 'bgra'): Uint8Array {
  const grid = new Uint8Array(GRID_W * GRID_H)
  const rIdx = order === 'bgra' ? 2 : 0
  const bIdx = order === 'bgra' ? 0 : 2
  for (let gy = 0; gy < GRID_H; gy++) {
    const y0 = Math.floor((gy * height) / GRID_H)
    const y1 = Math.max(y0 + 1, Math.floor(((gy + 1) * height) / GRID_H))
    const ys = Math.max(1, Math.floor((y1 - y0) / 6))
    for (let gx = 0; gx < GRID_W; gx++) {
      const x0 = Math.floor((gx * width) / GRID_W)
      const x1 = Math.max(x0 + 1, Math.floor(((gx + 1) * width) / GRID_W))
      const xs = Math.max(1, Math.floor((x1 - x0) / 6))
      let sum = 0
      let n = 0
      for (let y = y0; y < y1; y += ys) {
        for (let x = x0; x < x1; x += xs) {
          const i = (y * width + x) * 4
          sum += 0.299 * pixels[i + rIdx] + 0.587 * pixels[i + 1] + 0.114 * pixels[i + bIdx]
          n++
        }
      }
      grid[gy * GRID_W + gx] = Math.round(sum / n)
    }
  }
  return grid
}

// Mean absolute difference of two grids, 0 (identical) .. 1 (black vs white).
export function changeScore(a: Uint8Array, b: Uint8Array): number {
  if (a.length !== b.length || a.length === 0) return 1
  let total = 0
  for (let i = 0; i < a.length; i++) total += Math.abs(a[i] - b[i])
  return total / (a.length * 255)
}
