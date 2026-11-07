// Grounder: "where is <natural-language target> on this screenshot?", through the model port (vision, structured JSON).
//   preset 'fast': fast tier first; if it says not-found, is unsure (confidence < 0.7) or errors, escalate to the planner tier.
//   preset 'accurate' (default, and always for safety-critical steps and scam-phrase highlighting): planner tier only.
// If every box call fails or returns an implausible box, fall back to a computer-tool DRY RUN through the port (a click point
// only; nothing is ever executed). Never fabricates: unsure => found:false with a reason the assistant can say aloud.
// Coordinates: the model returns [x_min, y_min, x_max, y_max] as integers normalised 0-1000; the conversion to our NormBox
// lives in grounding-utils.ts. For browser pages the desktop app grounds from DOM rects instead (see src/main/dom-ground).
import { createHash } from 'node:crypto'
import { z } from 'zod'
import type { Grounder } from '../../shared/contracts'
import type { GroundResult, Shot } from '../../shared/protocol'
import { clamp01, isEnvironmental, ModelPortError, parseModelJson, plainFailure, type ModelTier } from '../model-port'
import { imageOf, withSafeLog, type ModelDeps } from './deps'
import { boxAroundPoint, boxCenter, boxProblem, fromPixelPoint, fromXyxyBox } from './grounding-utils'
import { INJECTION_GUARD } from './prompts'

export type GroundPreset = 'fast' | 'accurate'

export interface GroundConfig {
  preset?: GroundPreset
  detail?: 'low' | 'high' | 'auto' // image detail sent to the model
  timeoutMs?: number // hard budget for one ground() call as seen by the caller
  cacheTtlMs?: number
  lingerMs?: number // a call that outlives timeoutMs keeps running this long, to warm the cache
  escalateBelow?: number // fast preset: escalate when confidence is under this
}

const BOX_RESPONSE = z.object({
  found: z.boolean(),
  box: z.array(z.number()).optional(),
  label: z.string().optional(),
  reason: z.string().optional(),
  confidence: z.number().optional(),
})

const BOX_SCHEMA = {
  type: 'object',
  properties: {
    found: { type: 'boolean', description: 'true only if the described element is clearly visible on screen' },
    label: { type: 'string', description: 'The exact visible text or appearance of the element you matched; empty if not found' },
    box: {
      type: 'array',
      items: { type: 'integer' },
      description: 'Tight bounding box [x_min, y_min, x_max, y_max], integers normalised 0-1000 over the whole screenshot (0,0 is the top-left corner). [0,0,0,0] when found is false.',
    },
    reason: { type: 'string', description: 'Short reason, especially when found is false' },
    confidence: { type: 'number', description: '0 to 1: how sure you are this is exactly the described element' },
  },
  required: ['found', 'label', 'box', 'reason', 'confidence'],
}

export const normaliseTarget = (t: string): string => t.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim()
const hashShot = (s: Shot): string => createHash('sha1').update(s.jpegBase64).digest('hex')

function groundPrompt(target: string, hint?: string): string {
  return [
    "You are the eyes of an accessibility assistant for people with low digital confidence. The image is a full screenshot of the user's screen.",
    `Find this one element: "${target}".`,
    hint ? `Extra context from the lesson (trusted): ${hint}` : '',
    'Rules: return found=true ONLY if you can see that exact element. A similar element with a different label is NOT a match. If it is not on this screen, return found=false and box [0,0,0,0]. Never guess.',
    'First say in "label" what you actually see there, then give the tight bounding box [x_min, y_min, x_max, y_max], integers normalised to 0-1000 over the whole screenshot.',
    INJECTION_GUARD,
  ]
    .filter(Boolean)
    .join('\n')
}

function cuGoal(target: string): string {
  return `DRY RUN for an accessibility overlay: nothing will actually be clicked. Decide where you would click to select: "${target}". If that exact element is not visible on this screen, propose no action and reply with exactly NOT_FOUND.\n${INJECTION_GUARD}`
}

export type GrounderWithPreset = Grounder & Required<Pick<Grounder, 'prefetch' | 'invalidate'>> & { readonly preset: GroundPreset }

interface Interim {
  current: GroundResult | null
}

/** Reads ALONGSIDE_GROUNDING_PRESET=fast|accurate (anything else -> accurate: planner-first, fewer wrong-button picks). */
export function groundingPresetFromEnv(env: Record<string, string | undefined> = process.env): GroundPreset {
  return env.ALONGSIDE_GROUNDING_PRESET === 'fast' ? 'fast' : 'accurate'
}

/** Short ring label: the model's own words when sensible, else the target phrase trimmed of filler. */
export function shortLabel(label: string | undefined, target: string): string {
  const clean = (s: string) => s.replace(/\s+/g, ' ').trim()
  const words = (s: string, max: number) => clean(s).split(' ').slice(0, max).join(' ')
  const own = label ? clean(label) : ''
  if (own && own.length <= 40) return own
  if (own) return words(own, 5)
  return words(clean(target).replace(/^(the|a|an)\s+/i, ''), 5) || 'Here'
}

export function createGrounder(rawDeps: ModelDeps, config: GroundConfig = {}): GrounderWithPreset {
  const deps = withSafeLog(rawDeps)
  const preset: GroundPreset = config.preset ?? 'fast'
  const detail = config.detail ?? 'high'
  const timeoutMs = config.timeoutMs ?? 6000
  const ttl = config.cacheTtlMs ?? 30_000
  const linger = config.lingerMs ?? 25_000
  const escalateBelow = config.escalateBelow ?? 0.7

  type Mode = 'fast' | 'precise'
  // precise (safety-critical steps, scam highlighting) and the 'accurate' preset both go planner-first, no fast tier.
  const modeFor = (precise?: boolean): Mode => (precise || preset === 'accurate' ? 'precise' : 'fast')

  const cache = new Map<string, { at: number; result: GroundResult }>() // key: shotHash|target|mode
  const inflight = new Map<string, { promise: Promise<GroundResult>; interim: Interim }>()
  // Latest prefetch per target+mode: lets ground({target}) with no shot reuse it (the runner prefetches on screen change).
  const prefetched = new Map<string, { key: string; at: number }>()

  deps.log('grounder', `preset=${preset} (set ALONGSIDE_GROUNDING_PRESET=fast|accurate) fast=fast->planner precise=planner`)

  const notFound = (reason: string, started: number, model: string = deps.port.models().fast): GroundResult => ({
    found: false,
    confidence: 0,
    reason,
    latencyMs: Date.now() - started,
    model,
  })

  async function boxCall(tier: ModelTier, shot: Shot, target: string, hint: string | undefined, started: number): Promise<GroundResult> {
    const call = await deps.port.complete({
      name: `grounder.box.${tier}`,
      tier,
      timeoutMs: linger,
      retries: 0,
      text: groundPrompt(target, hint),
      images: [imageOf(shot, detail)],
      effort: 'low',
      schema: { name: 'ground_box', schema: BOX_SCHEMA },
    })
    const model = call.model
    const parsed = parseModelJson(call.text, BOX_RESPONSE)
    const confidence = clamp01(parsed.confidence ?? 0.8)
    if (!parsed.found) {
      return { found: false, confidence, reason: parsed.reason || "I can't see that on the screen.", label: parsed.label || undefined, latencyMs: Date.now() - started, model }
    }
    const box = fromXyxyBox(parsed.box)
    if (!box) throw new ModelPortError('parse', 'found=true but box is missing or malformed')
    const problem = boxProblem(box)
    if (problem) throw new ModelPortError('parse', problem === 'oversize' ? 'box covers more than half the screen' : 'box is degenerate')
    return {
      found: true,
      box,
      point: boxCenter(box),
      confidence,
      label: shortLabel(parsed.label, target),
      reason: parsed.reason || undefined,
      latencyMs: Date.now() - started,
      model,
    }
  }

  async function cuFallback(shot: Shot, target: string, budgetMs: number, started: number): Promise<GroundResult | null> {
    if (budgetMs < 2500) return null
    try {
      const r = await deps.port.computerStep({
        goal: cuGoal(target),
        history: [],
        screenshot: { jpegBase64: shot.jpegBase64, detail: 'high', widthPx: shot.widthPx, heightPx: shot.heightPx },
        timeoutMs: budgetMs,
      })
      if (r.kind !== 'actions') return null
      const click = r.actions.find((a) => a.type === 'click' || a.type === 'double_click' || a.type === 'move')
      if (!click || !('x' in click)) return null
      const point = fromPixelPoint(click.x, click.y, r.widthPx, r.heightPx)
      if (!point) return null
      return {
        found: true,
        point,
        box: boxAroundPoint(point),
        confidence: 0.5, // a click point only; the box is a nominal square around it
        label: shortLabel(undefined, target),
        reason: 'approximate location (fallback)',
        latencyMs: Date.now() - started,
        model: `${r.model}+computer_use`,
      }
    } catch {
      return null
    }
  }

  async function cascade(shot: Shot, target: string, hint: string | undefined, started: number, interim: Interim, mode: Mode): Promise<GroundResult> {
    const primaryTier: ModelTier = mode === 'fast' ? 'fast' : 'planner'
    const escalateTier: ModelTier | null = mode === 'fast' ? 'planner' : null
    let first: GroundResult | null = null
    let firstError: unknown = null
    try {
      first = await boxCall(primaryTier, shot, target, hint, started)
    } catch (e) {
      if (e instanceof ModelPortError && e.code === 'timeout') return notFound('timeout', started, deps.port.models()[primaryTier])
      firstError = e
    }
    if (first && first.found && first.confidence >= escalateBelow) return first
    if (first) interim.current = first // an honest not-found / low-confidence answer the caller can use if escalation is too slow

    if (escalateTier) {
      try {
        const second = await boxCall(escalateTier, shot, target, hint, started)
        // Escalation is the more accurate model: its answer wins, except it never turns a decisive find into nothing.
        if (second.found || !first?.found) return second
        return first
      } catch (e) {
        deps.log('grounder', `escalation failed (${e instanceof ModelPortError ? e.code : 'error'})`)
      }
    }
    if (first) return first
    deps.log('grounder', `box call failed (${firstError instanceof ModelPortError ? firstError.code : 'error'}); trying computer_use fallback`)
    const remaining = Math.max(0, timeoutMs - (Date.now() - started))
    const fb = await cuFallback(shot, target, remaining, started)
    if (fb) return fb
    // Say what is actually wrong when it is the connection or setup; never invent a location either way.
    const why = isEnvironmental(firstError) ? `${plainFailure(firstError)} So I can't look at the screen.` : 'I could not pin down where that is on the screen.'
    return notFound(why, started, deps.port.models()[primaryTier])
  }

  const keyFor = (shot: Shot, target: string, mode: Mode) => `${hashShot(shot)}|${normaliseTarget(target)}|${mode}`

  function start(shot: Shot, target: string, hint: string | undefined, mode: Mode) {
    const key = keyFor(shot, target, mode)
    // A precise (planner-first) answer is at least as good as a fast one, so it can serve a fast request.
    for (const k of mode === 'fast' ? [key, keyFor(shot, target, 'precise')] : [key]) {
      const hit = cache.get(k)
      if (hit && Date.now() - hit.at < ttl) return { key: k, promise: Promise.resolve({ ...hit.result, latencyMs: 0 }), interim: { current: null } as Interim }
    }
    const existing = inflight.get(key)
    if (existing) return { key, ...existing }
    const started = Date.now()
    const interim: Interim = { current: null }
    const promise = cascade(shot, target, hint, started, interim, mode)
      .then((r) => {
        // Cache decisive answers only; a timeout or "could not pin down" must be retried fresh.
        if (r.found || r.confidence > 0) cache.set(key, { at: Date.now(), result: r })
        return r
      })
      .finally(() => inflight.delete(key))
    inflight.set(key, { promise, interim })
    return { key, promise, interim }
  }

  const withDeadline = (p: Promise<GroundResult>, interim: Interim, started: number): Promise<GroundResult> =>
    Promise.race([
      p,
      new Promise<GroundResult>((resolve) =>
        setTimeout(() => resolve(interim.current ? { ...interim.current, latencyMs: Date.now() - started } : notFound('timeout', started)), timeoutMs),
      ),
    ])

  const shotFor = async (shot?: Shot): Promise<Shot | null> => shot ?? (deps.capture ? deps.capture.grab('ground') : null)
  const prefKey = (norm: string, mode: Mode) => `${norm}|${mode}`

  return {
    preset,

    async ground({ target, shot, hint, precise }) {
      const started = Date.now()
      const norm = normaliseTarget(target)
      const mode = modeFor(precise)
      const finish = (r: GroundResult): GroundResult => {
        deps.log('grounder', `ground target=${norm.length}chars mode=${mode} found=${r.found} conf=${r.confidence.toFixed(2)} model=${r.model} ${r.latencyMs}ms`)
        return r
      }
      if (!norm) return finish(notFound('Nothing to look for.', started))
      if (!shot) {
        // Reuse a prefetch for this target (cached result or in-flight call) before paying for a fresh capture.
        for (const m of mode === 'fast' ? (['fast', 'precise'] as const) : (['precise'] as const)) {
          const pre = prefetched.get(prefKey(norm, m))
          if (!pre || Date.now() - pre.at >= ttl) continue
          const hit = cache.get(pre.key)
          if (hit && Date.now() - hit.at < ttl) return finish({ ...hit.result, latencyMs: Date.now() - started })
          const flying = inflight.get(pre.key)
          if (flying) return finish(await withDeadline(flying.promise, flying.interim, started))
        }
      }
      const s = await shotFor(shot)
      if (!s) return finish(notFound('No screenshot available.', started))
      const { promise, interim } = start(s, target, hint, mode)
      return finish(await withDeadline(promise, interim, started))
    },

    prefetch({ target, shot, precise }) {
      const norm = normaliseTarget(target)
      if (!norm) return
      const mode = modeFor(precise)
      void (async () => {
        try {
          const s = await shotFor(shot)
          if (!s) return
          const { key } = start(s, target, undefined, mode)
          prefetched.set(prefKey(norm, mode), { key, at: Date.now() })
        } catch (e) {
          deps.log('grounder', `prefetch skipped (${e instanceof ModelPortError ? e.code : 'error'})`)
        }
      })()
    },

    invalidate() {
      cache.clear()
      prefetched.clear()
    },
  }
}
