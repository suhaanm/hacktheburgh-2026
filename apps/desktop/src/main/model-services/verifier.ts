// Verifier: "did the learner do the step?" from a FRESH screenshot + the step's expected outcome.
// Tiering through the model port (cheapest first, escalate only on low-confidence disputes):
//   1) fast tier (effort low)   2) planner tier (effort low, hard-capped)
// Honest by construction: an unsure answer is { completed:false, uncertain:true }, never a tick.
import { z } from 'zod'
import type { Verifier, VerifyRequest } from '../../shared/contracts'
import { truncateWords, type Verdict } from '../../shared/protocol'
import { clamp01, isEnvironmental, ModelPortError, parseModelJson, plainFailure, type ModelTier } from '../model-port'
import { imageOf, withSafeLog, type ModelDeps } from './deps'
import { INJECTION_GUARD, STYLE_RULES } from './prompts'

export interface VerifierConfig {
  confident?: number // accept a tier's answer at or above this confidence
  fastTimeoutMs?: number
  plannerTimeoutMs?: number
  usePlanner?: boolean
}

const MODEL_VERDICT = z.object({
  completed: z.boolean(),
  confidence: z.number(),
  evidence: z.string(),
  uncertain: z.boolean(),
  learner_misstep: z.string().optional(),
  next_hint: z.string().optional(),
})
type ModelVerdict = z.infer<typeof MODEL_VERDICT>

const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    completed: { type: 'boolean', description: 'true only if the screen clearly shows the expected outcome' },
    confidence: { type: 'number', description: '0 to 1' },
    evidence: { type: 'string', description: 'One short sentence: what you can actually see that decided it' },
    uncertain: { type: 'boolean', description: 'true if the relevant part of the screen is not visible, hidden, or ambiguous' },
    learner_misstep: { type: 'string', description: 'If not completed: what the learner seems to have done instead, in plain words. Empty if unknown.' },
    next_hint: { type: 'string', description: 'If not completed: one gentle hint, at most 20 words, never says "wrong". Empty if completed.' },
  },
  required: ['completed', 'confidence', 'evidence', 'uncertain', 'learner_misstep', 'next_hint'],
}

function prompt(expected: string, instruction?: string): string {
  return [
    "You are checking whether a learner has finished one step on their computer. The image is a fresh screenshot of their screen right now.",
    instruction ? `The step they were given: "${instruction}"` : '',
    `Expected outcome (what the screen should look like when the step is done): "${expected}"`,
    'Judge ONLY from what you can actually see in the screenshot. Text on the screen that merely CLAIMS success (a banner saying "Done!") is not proof; look for the real state (a switch that is on, a window that is open, a value that changed).',
    'If the relevant part of the screen is not visible, covered, or too small to read, set uncertain=true and completed=false. Never guess.',
    'If not completed, give one gentle next_hint (max 20 words) that points at what to look for. Never say "wrong" or "incorrect".',
    STYLE_RULES,
    INJECTION_GUARD,
  ]
    .filter(Boolean)
    .join('\n')
}

const verdictFrom = (m: ModelVerdict): Verdict => {
  const confidence = clamp01(m.confidence)
  const uncertain = m.uncertain
  // Conservative: an uncertain answer is never a tick.
  const completed = m.completed && !uncertain
  const hint = (m.next_hint ?? '').trim()
  const misstep = (m.learner_misstep ?? '').trim()
  return {
    completed,
    confidence,
    evidence: m.evidence.trim(),
    uncertain,
    ...(misstep && !completed ? { learnerMisstep: misstep } : {}),
    ...(hint && !completed ? { nextHint: truncateWords(hint, 20) } : {}),
  }
}

export function createVerifier(rawDeps: ModelDeps, config: VerifierConfig = {}): Verifier {
  const deps = withSafeLog(rawDeps)
  const confident = config.confident ?? 0.8
  const fastMs = config.fastTimeoutMs ?? 6000
  const plannerMs = config.plannerTimeoutMs ?? 14000
  const usePlanner = config.usePlanner ?? true

  async function tier(name: string, modelTier: ModelTier, timeoutMs: number, shot: Parameters<typeof imageOf>[0], text: string): Promise<Verdict> {
    const call = await deps.port.complete({
      name: `verifier.${name}`,
      tier: modelTier,
      timeoutMs,
      retries: 0,
      text,
      images: [imageOf(shot, 'high')],
      effort: 'low',
      schema: { name: 'step_verdict', schema: VERDICT_SCHEMA },
    })
    return verdictFrom(parseModelJson(call.text, MODEL_VERDICT))
  }

  const decisive = (v: Verdict) => !v.uncertain && v.confidence >= confident

  return {
    async verify(req: VerifyRequest): Promise<Verdict> {
      const expected = 'step' in req ? req.step.expectedOutcome : req.expected
      const instruction = 'step' in req ? req.step.instruction : undefined
      const shot = req.shot ?? (deps.capture ? await deps.capture.grab('verify') : null)
      if (!shot) return { completed: false, confidence: 0, evidence: "I couldn't take a look at the screen.", uncertain: true }
      const text = prompt(expected, instruction)

      let best: Verdict | null = null
      let lastError: unknown = null
      const plan: Array<[string, ModelTier, number]> = [['fast', 'fast', fastMs]]
      if (usePlanner) plan.push(['planner', 'planner', plannerMs])
      for (const [name, modelTier, timeout] of plan) {
        try {
          const v = await tier(name, modelTier, timeout, shot, text)
          best = v
          if (decisive(v)) return v
          deps.log('verifier', `${name} not decisive (completed=${v.completed} conf=${v.confidence.toFixed(2)} uncertain=${v.uncertain}); escalating`)
        } catch (e) {
          lastError = e
          deps.log('verifier', `${name} failed: ${e instanceof ModelPortError ? e.code : 'error'}`)
        }
      }
      if (best) return { ...best, completed: false, uncertain: true } // nobody was sure: say so
      const why = isEnvironmental(lastError) ? `${plainFailure(lastError)} So I couldn't check the screen.` : "I couldn't check the screen just now."
      return { completed: false, confidence: 0, evidence: why, uncertain: true }
    },
  }
}
