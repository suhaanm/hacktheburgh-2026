// Narration script: assets/showtime/script.json (persona, text, timing) validated with zod and bundled into main.
import { z } from 'zod'
import { PERSONAS } from '../../shared/personas'
import { PersonaIdSchema } from '../../shared/protocol'
import raw from '../../../assets/showtime/script.json'
import type { ScriptLine } from './types'

const LineSchema = z.object({
  id: z.string().min(1),
  chapter: z.string().min(1),
  persona: PersonaIdSchema,
  text: z.string().min(1),
  durationMs: z.number().int().min(500).max(20_000),
  full: z.boolean().optional(),
})
const ScriptSchema = z.object({ version: z.literal(1), lines: z.array(LineSchema).min(1) })

export function parseScript(input: unknown): Map<string, ScriptLine> {
  const parsed = ScriptSchema.parse(input)
  const map = new Map<string, ScriptLine>()
  for (const l of parsed.lines) {
    if (map.has(l.id)) throw new Error(`duplicate narration line id: ${l.id}`)
    map.set(l.id, l)
  }
  return map
}

export const SCRIPT_LINES: Map<string, ScriptLine> = parseScript(raw)

export function line(id: string, lines: Map<string, ScriptLine> = SCRIPT_LINES): ScriptLine {
  const l = lines.get(id)
  if (!l) throw new Error(`unknown narration line: ${id}`)
  return l
}

// "{name}" in narration text is the speaking persona's display name, so renaming personas needs no script edit.
export function resolveText(l: ScriptLine): string {
  return l.text.replace(/\{name\}/g, PERSONAS[l.persona].displayName)
}
