// Bundled by smoke tests: builds the REAL Teaching system instruction (src/main/teaching/prompts.ts) for a fresh learner.
import { PERSONAS } from '../../src/shared/personas'
import { DEFAULT_SETTINGS } from '../../src/shared/settings'
import { buildSystemInstruction } from '../../src/main/teaching/prompts'
import type { LearnerSnapshot } from '../../src/shared/protocol'

const fresh = { level: 1, streakClean: 0, lastSeen: null, nextReview: null } as const
export function realSystemInstruction(persona: 'marcus' | 'amelia' = 'marcus'): string {
  const learner = { skills: { video_call: { ...fresh }, spot_scam: { ...fresh }, bigger_text: { ...fresh } }, confidenceLog: [], attempts: [], whatWorks: [], avoidJargon: [] } as unknown as LearnerSnapshot
  return buildSystemInstruction({ persona: PERSONAS[persona], settings: DEFAULT_SETTINGS, learner, level: 2, now: Date.now() })
}
