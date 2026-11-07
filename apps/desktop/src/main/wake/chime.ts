// A soft two-note chime, synthesised in memory as a 16-bit mono WAV (no asset file, nothing downloaded). Quiet by design: low amplitude, a
// short fade in and out, 180 ms in all. It says "I heard you" before the model speaks. The visual cue (the pill says Listening) always shows too.
export const CHIME_RATE = 22050

export function makeChimeWav(opts: { amplitude?: number } = {}): Uint8Array {
  const amp = Math.min(0.25, Math.max(0, opts.amplitude ?? 0.12))
  const notes: Array<{ hz: number; ms: number }> = [{ hz: 784, ms: 80 }, { hz: 1175, ms: 100 }]
  const samples: number[] = []
  for (const n of notes) {
    const len = Math.floor((CHIME_RATE * n.ms) / 1000)
    for (let i = 0; i < len; i++) {
      const edge = Math.min(i, len - 1 - i) / (CHIME_RATE * 0.012) // 12 ms fades
      const env = Math.min(1, edge) * (1 - i / (len * 1.4))
      samples.push(Math.round(Math.sin((2 * Math.PI * n.hz * i) / CHIME_RATE) * amp * env * 32767))
    }
  }
  const dataBytes = samples.length * 2
  const out = new Uint8Array(44 + dataBytes)
  const v = new DataView(out.buffer)
  const str = (o: number, s: string): void => void [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)))
  str(0, 'RIFF')
  v.setUint32(4, 36 + dataBytes, true)
  str(8, 'WAVE')
  str(12, 'fmt ')
  v.setUint32(16, 16, true)
  v.setUint16(20, 1, true) // PCM
  v.setUint16(22, 1, true) // mono
  v.setUint32(24, CHIME_RATE, true)
  v.setUint32(28, CHIME_RATE * 2, true)
  v.setUint16(32, 2, true)
  v.setUint16(34, 16, true)
  str(36, 'data')
  v.setUint32(40, dataBytes, true)
  samples.forEach((s, i) => v.setInt16(44 + i * 2, s, true))
  return out
}
