// Verifier: "did the learner do the step?" from a FRESH screenshot + the step's expected outcome.
// Tiering (cheapest first, escalate only on low-confidence disputes):
//   1) gemini-3.5-flash-lite (thinking low, ~1s)  2) gemini-3.8-flash  3) gemini-4-argon (thinking low, hard-capped)
// Honest by construction: an unsure answer is { completed:false, uncertain:true }, never a tick.
import { z } from 'zod'
import type { Verifier, VerifyRequest } from '../../shared/contracts'
import { truncateWords, type Verdict } from '../../shared/protocol'
import {
  callModel,
  clamp01,
  GeminiError,
  imageInput,
  isEnvironmental,
  jsonFormat,
  parseModelJson,
  plainFailure,
  withSafeLog,
  type GeminiDeps,
} from './client'
import { INJECTION_GUARD, STYLE_RULES } from './prompts'

export interface VerifierConfig {
  confident?: number // accept a tier's answer at or above this confidence
  liteTimeoutMs?: number
  flashTimeoutMs?: number
  argonTimeoutMs?: number
  useArgon?: boolean
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

export function createVerifier(rawDeps: GeminiDeps, config: VerifierConfig = {}): Verifier {
  const deps = withSafeLog(rawDeps)
  const confident = config.confident ?? 0.8
  const liteMs = config.liteTimeoutMs ?? 6000
  const flashMs = config.flashTimeoutMs ?? 9000
  const argonMs = config.argonTimeoutMs ?? 14000
  const useArgon = config.useArgon ?? true

  async function tier(name: string, model: string, thinking: string, timeoutMs: number, shot: Parameters<typeof imageInput>[0], text: string): Promise<Verdict> {
    const call = await callModel(deps, {
      name: `verifier.${name}`,
      model,
      timeoutMs,
      retries: 0,
      params: {
        input: [{ type: 'text', text }, imageInput(shot, 'high')],
        generation_config: { thinking_level: thinking },
        response_format: jsonFormat(VERDICT_SCHEMA),
      },
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
      const plan: Array<[string, string, string, number]> = [
        ['lite', deps.models.lite, 'low', liteMs],
        ['flash', deps.models.flash, 'low', flashMs],
      ]
      if (useArgon) plan.push(['argon', deps.models.argon, 'low', argonMs])
      for (const [name, model, thinking, timeout] of plan) {
        try {
          const v = await tier(name, model, thinking, timeout, shot, text)
          best = v
          if (decisive(v)) return v
          deps.log('verifier', `${name} not decisive (completed=${v.completed} conf=${v.confidence.toFixed(2)} uncertain=${v.uncertain}); escalating`)
        } catch (e) {
          lastError = e
          deps.log('verifier', `${name} failed: ${e instanceof GeminiError ? e.code : 'error'}`)
        }
      }
      if (best) return { ...best, completed: false, uncertain: true } // nobody was sure: say so
      const why = isEnvironmental(lastError) ? `${plainFailure(lastError)} So I couldn't check the screen.` : "I couldn't check the screen just now."
      return { completed: false, confidence: 0, evidence: why, uncertain: true }
    },
  }
}
