// Guards the rendered narration (scripts/showtime-render.mjs): every script line must resolve to a readable WAV through the real
// loader. After editing assets/showtime/script.json or personas.ts, run `npm run showtime:render` (it only redoes changed lines).
import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { createNarrator, textHash, type ClipManifest } from './narration'
import { SCRIPT_LINES, resolveText } from './script'

const dir = path.join(process.cwd(), 'assets/showtime/clips')

describe('rendered narration clips', () => {
  it('resolves every script line to a clip with a matching hash', async () => {
    const narrator = createNarrator(dir)
    const missing: string[] = []
    for (const l of SCRIPT_LINES.values()) {
      const clip = await narrator.clip(l.id, resolveText(l))
      if (!clip) missing.push(l.id)
    }
    expect(missing, 'missing or stale clips: run npm run showtime:render').toEqual([])
    expect(await narrator.available()).toBeGreaterThanOrEqual(SCRIPT_LINES.size)
  })

  it('rejects a clip when the text has changed', async () => {
    const first = [...SCRIPT_LINES.values()][0]
    expect(await createNarrator(dir).clip(first.id, `${resolveText(first)} (edited)`)).toBeNull()
  })

  it('writes mono 16-bit 24 kHz WAV files whose length matches the manifest', async () => {
    const manifest = JSON.parse(await readFile(path.join(dir, 'manifest.json'), 'utf8')) as ClipManifest
    for (const l of SCRIPT_LINES.values()) {
      const entry = manifest.lines[l.id]
      expect(entry, l.id).toBeDefined()
      expect(entry.textHash).toBe(textHash(resolveText(l)))
      const buf = await readFile(path.join(dir, entry.file))
      expect(buf.toString('ascii', 0, 4), l.id).toBe('RIFF')
      expect(buf.toString('ascii', 8, 12)).toBe('WAVE')
      expect(buf.readUInt16LE(20)).toBe(1) // PCM
      expect(buf.readUInt16LE(22)).toBe(1) // mono
      expect(buf.readUInt32LE(24)).toBe(24_000)
      expect(buf.readUInt16LE(34)).toBe(16)
      const dataBytes = buf.readUInt32LE(40)
      expect(buf.length).toBe(44 + dataBytes)
      expect(Math.abs((dataBytes / 2 / 24_000) * 1000 - entry.durationMs)).toBeLessThan(2)
    }
  })
})
