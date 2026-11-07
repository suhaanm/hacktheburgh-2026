// Pre-rendered narration clips: assets/showtime/clips/<id>.wav plus manifest.json (written by scripts/showtime-render.mjs).
// A missing or stale clip (the text changed since it was rendered) means captions only, never a wrong voice line.
import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

export interface ClipManifest {
  generatedAt: string
  model: string
  lines: Record<string, { file: string; persona: string; voice: string; textHash: string; durationMs: number }>
}

export const textHash = (text: string): string => createHash('sha1').update(text).digest('hex').slice(0, 16)

export interface Narrator {
  // base64 WAV for a line, or null (no clip, stale clip, unreadable).
  clip(id: string, resolvedText: string): Promise<{ base64: string; mime: string } | null>
  available(): Promise<number>
}

export function createNarrator(dir: string, log: (msg: string) => void = () => undefined): Narrator {
  let manifest: ClipManifest | null | undefined
  const load = async (): Promise<ClipManifest | null> => {
    if (manifest !== undefined) return manifest
    try {
      manifest = JSON.parse(await readFile(path.join(dir, 'manifest.json'), 'utf8')) as ClipManifest
    } catch {
      manifest = null
    }
    return manifest
  }
  return {
    async clip(id, resolvedText) {
      const m = await load()
      const entry = m?.lines[id]
      if (!entry) return null
      if (entry.textHash !== textHash(resolvedText)) {
        log(`clip ${id} is stale (text changed since it was rendered): captions only. Run npm run showtime:render`)
        return null
      }
      try {
        const data = await readFile(path.join(dir, entry.file))
        return { base64: data.toString('base64'), mime: 'audio/wav' }
      } catch {
        return null
      }
    },
    async available() {
      return Object.keys((await load())?.lines ?? {}).length
    },
  }
}
