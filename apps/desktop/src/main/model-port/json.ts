// JSON helpers shared by every provider and service: tolerant parsing validated by zod, and strict-schema conversion.
import type { ZodType } from 'zod'
import { ModelPortError } from './errors'

export const clamp01 = (n: number): number => Math.min(1, Math.max(0, n))

/** Parses model JSON (tolerating ``` fences / stray prose) and validates it with zod. */
export function parseModelJson<T>(text: string, schema: ZodType<T>): T {
  const trimmed = text.trim().replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '')
  const attempts = [trimmed]
  const first = trimmed.indexOf('{')
  const lastBrace = trimmed.lastIndexOf('}')
  if (first >= 0 && lastBrace > first) attempts.push(trimmed.slice(first, lastBrace + 1))
  let err: unknown
  for (const candidate of attempts) {
    try {
      return schema.parse(JSON.parse(candidate))
    } catch (e) {
      err = e
    }
  }
  throw new ModelPortError('parse', `model returned invalid JSON: ${String((err as Error | undefined)?.message ?? err).slice(0, 200)}`)
}

/** Parses JSON without a schema (used by the port verbs, which return `unknown`). */
export function parseLooseJson(text: string): unknown {
  const trimmed = text.trim().replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '')
  try {
    return JSON.parse(trimmed)
  } catch {
    const first = trimmed.indexOf('{')
    const last = trimmed.lastIndexOf('}')
    if (first >= 0 && last > first) {
      try {
        return JSON.parse(trimmed.slice(first, last + 1))
      } catch {
        /* fall through */
      }
    }
    throw new ModelPortError('parse', 'model returned text that is not JSON')
  }
}

type Json = Record<string, unknown>
const isObj = (v: unknown): v is Json => typeof v === 'object' && v !== null && !Array.isArray(v)

/** True when every object node lists all of its properties in `required` (what OpenAI strict mode demands). */
export function isStrictCompatible(schema: unknown): boolean {
  if (Array.isArray(schema)) return schema.every(isStrictCompatible)
  if (!isObj(schema)) return true
  if (isObj(schema.properties)) {
    const required = Array.isArray(schema.required) ? (schema.required as string[]) : []
    if (Object.keys(schema.properties).some((p) => !required.includes(p))) return false
  }
  return Object.entries(schema).every(([k, v]) => (k === 'properties' && isObj(v) ? Object.values(v).every(isStrictCompatible) : isStrictCompatible(v)))
}

/**
 * Makes a schema acceptable to OpenAI strict structured outputs: every object gets additionalProperties:false.
 * When a schema has optional properties we cannot make it strict without changing its meaning, so it is returned unchanged
 * with strict:false and the provider sends it as a best-effort (non-strict) schema.
 */
export function strictify(schema: Json): { schema: Json; strict: boolean } {
  if (!isStrictCompatible(schema)) return { schema, strict: false }
  const walk = (node: unknown): unknown => {
    if (Array.isArray(node)) return node.map(walk)
    if (!isObj(node)) return node
    const out: Json = {}
    for (const [k, v] of Object.entries(node)) out[k] = k === 'properties' && isObj(v) ? Object.fromEntries(Object.entries(v).map(([pk, pv]) => [pk, walk(pv)])) : walk(v)
    if (out.type === 'object' || isObj(out.properties)) out.additionalProperties = false
    return out
  }
  return { schema: walk(schema) as Json, strict: true }
}
