// Rolling PCM16 buffer so the words said in the same breath as the name ("Hey Marcus, make the text bigger")
// are not lost while the Live session connects.

export const PCM_SAMPLE_RATE = 16000

export class PrerollBuffer {
  private readonly chunks: Int16Array[] = []
  private samples = 0
  private readonly capacity: number

  constructor(
    private readonly maxMs = 3000,
    sampleRate = PCM_SAMPLE_RATE,
  ) {
    this.capacity = Math.round((maxMs / 1000) * sampleRate)
  }

  push(chunk: Int16Array): void {
    if (!chunk.length) return
    this.chunks.push(chunk)
    this.samples += chunk.length
    while (this.samples - this.chunks[0]!.length >= this.capacity) {
      this.samples -= this.chunks.shift()!.length
    }
  }

  get lengthMs(): number {
    return Math.min(this.samples, this.capacity) / (this.capacity / this.maxMs)
  }

  // Copy of the most recent audio (at most maxMs), oldest first. Does not clear.
  snapshot(): Int16Array {
    const total = Math.min(this.samples, this.capacity)
    const out = new Int16Array(total)
    let pos = total
    for (let i = this.chunks.length - 1; i >= 0 && pos > 0; i--) {
      const c = this.chunks[i]!
      const take = Math.min(c.length, pos)
      out.set(c.subarray(c.length - take), pos - take)
      pos -= take
    }
    return out
  }

  clear(): void {
    this.chunks.length = 0
    this.samples = 0
  }
}

export function floatToPcm16(input: Float32Array): Int16Array {
  const out = new Int16Array(input.length)
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]!))
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff
  }
  return out
}

export function pcm16ToBase64(pcm: Int16Array): string {
  const bytes = new Uint8Array(pcm.buffer, pcm.byteOffset, pcm.byteLength)
  let bin = ''
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000))
  return btoa(bin)
}
