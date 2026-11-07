// Stage directions the app injects into the Live session ([RUNNER] / [STALL]) and the swappable per-level
// behaviour text. The system instruction tells the model these are authoritative but must be spoken naturally,
// never read out. Keep every directive short: the model reads them mid-conversation.
import type { HelpLevel } from '../../shared/protocol'
import { LEVEL_LABEL } from './levels'

// Per-level behaviour. The system prompt embeds the current level's text; a mid-session change re-sends it.
export const LEVEL_POLICY: Record<HelpLevel, string> = {
  1: 'Show first, then they try. The app moves a ghost cursor to show each step without clicking anything. Narrate slowly in short full sentences with one everyday comparison. Never more than three steps, then ask "Does that make sense?" and wait. Reassure: nothing here can break.',
  2: 'One step at a time. The app draws an arrow, a ring and a number on the next thing to use. Say the instruction using the label on the screen, then wait quietly. The app checks every step; say "that worked" only after you are told the step is verified.',
  3: 'Say only the goal (for example "Let\'s call Lily. Go ahead.") and then stay quiet. Before one consequential step you may ask "What do you think happens if you tap that?". If a [STALL] arrives, give the clue it contains and nothing more.',
  4: 'Stay silent while they work. Speak only to prevent harm (money, passwords, suspicious links) or when they ask. When they say they are done or ask "did I do it right?", call verify_step.',
}

export function levelHeader(level: HelpLevel): string {
  return `${level} "${LEVEL_LABEL[level]}"`
}

export function levelDirective(level: HelpLevel, reason?: string): string {
  const why = reason ? ` (${oneLine(reason)})` : ''
  return `[RUNNER] level=${levelHeader(level)}${why}. From now on: ${LEVEL_POLICY[level]}`
}

export function oneLine(text: string): string {
  return text.replace(/[\r\n]+/g, ' ').replace(/[[\]]/g, '').replace(/\s+/g, ' ').trim()
}

export interface StepDirectiveInput {
  stepNumber: number
  stepCount: number
  level: HelpLevel
  instruction: string
  // Narration for L1 (the ghost cursor is moving while you speak).
  demoNarration?: string
  analogy?: string
  safetyCritical: boolean
  // L1 only: ask "does that make sense?" after this step.
  pauseForCheck: boolean
  lessonStart?: { name: string; goal: string }
  // False when grounding failed: nothing is drawn, so describe where to look in words instead.
  annotated: boolean
}

export function stepDirective(i: StepDirectiveInput): string {
  const head = i.lessonStart ? `[RUNNER] lesson "${oneLine(i.lessonStart.name)}" started for goal "${oneLine(i.lessonStart.goal)}". ` : '[RUNNER] '
  const where = `step ${i.stepNumber} of ${i.stepCount}, level ${levelHeader(i.level)}.`
  const lines: string[] = []
  if (i.level === 1) {
    lines.push(`Narrate this step slowly while the ghost cursor shows it: "${oneLine(i.demoNarration ?? i.instruction)}". The cursor will not click; the learner does the real tap afterwards.`)
    if (i.analogy) lines.push(`One comparison you may use: ${oneLine(i.analogy)}.`)
    if (i.pauseForCheck) lines.push('After this step, ask if that makes sense before going on.')
  } else if (i.level === 2) {
    lines.push(`Tell the learner: "${oneLine(i.instruction)}". ${i.annotated ? 'The app has drawn an arrow and a numbered ring.' : 'Nothing could be drawn, so say where to look in words.'} Then wait.`)
  } else if (i.level === 3) {
    lines.push(i.stepNumber === 1 ? `Say only the goal: "${oneLine(i.lessonStart?.goal ?? i.instruction)}". Then stay quiet.` : 'Stay quiet unless a [STALL] arrives or the learner asks. They know the goal.')
  } else {
    lines.push('Stay silent. The learner is working alone.')
  }
  if (i.safetyCritical) lines.push('This step is safety-critical: explain why in one sentence and make sure the learner is happy to do it. Use ask_user_confirm for anything involving money, passwords or sharing.')
  return `${head}${where} ${lines.join(' ')}`
}

export function verifiedDirective(stepNumber: number, stepCount: number, level: HelpLevel, last: boolean): string {
  const quiet = level >= 3 ? ' Keep it very short or say nothing.' : ''
  return `[RUNNER] step ${stepNumber} of ${stepCount} verified on the screen.${quiet}${last ? ' That was the last step.' : ' The next step is coming.'} Acknowledge once, specifically, without gushing.`
}

export function repairDirective(stepNumber: number, hint: string, misstep?: string): string {
  const what = misstep ? ` What we saw: ${oneLine(misstep)}.` : ''
  return `[RUNNER] step ${stepNumber} did not work.${what} Reassure in one short sentence (everyone does this) and say: "${oneLine(hint)}". The target is highlighted again.`
}

export function uncertainDirective(stepNumber: number): string {
  return `[RUNNER] step ${stepNumber}: the screen check was not certain. Say "I can't quite see that" and ask the learner what they see. Do not guess.`
}

export function stallDirective(level: HelpLevel, rung: 1 | 2 | 3, clue: string, solo: boolean): string {
  if (solo) return '[STALL] The learner went quiet while trying on their own. Gently offer a hint ("Would you like a hint?") but do not give one yet.'
  if (rung === 1) return '[STALL] The learner seems to be waiting. A soft glow marks the area. Say nothing or one calm sentence.'
  if (rung === 2) return `[STALL] Give this clue in your own words, nothing more: "${oneLine(clue)}".`
  return `[STALL] An arrow is now showing. Say: "${oneLine(clue)}". This step has dropped to level ${levelHeader(Math.min(level, 2) as HelpLevel)}.`
}

export function lessonCompleteDirective(opts: { skillName: string; teachBack: boolean; rubric: string[]; retrievalQuestion: string }): string {
  if (!opts.teachBack) {
    return `[RUNNER] lesson "${oneLine(opts.skillName)}" complete. Teach-back is switched off: say well done in one specific sentence, then call end_lesson with a one-sentence summary and no teachBackScore.`
  }
  return `[RUNNER] lesson "${oneLine(opts.skillName)}" complete. Now do the teach-back: (1) ask them to say in their own words how they would do it next time; (2) silently score 0 to 1 against: ${opts.rubric.map(oneLine).join('; ')}; if under 0.67 re-explain the missing part with a different comparison and ask once more; (3) ask: "${oneLine(opts.retrievalQuestion)}"; (4) ask for a confidence number from 1 to 5; (5) call end_lesson with summary, teachBackScore and confidence. If they decline any part, skip it without fuss.`
}

// Sent before a novel goal is planned: keep the assistant talking and honest while the architect works.
export function planningDirective(goal: string): string {
  return `[RUNNER] The learner asked for something new: "${oneLine(goal).slice(0, 160)}". The app is looking at their screen to work out the steps. Say one short natural line such as that you will have a look at the screen and work out the steps. Do not guess any steps yet.`
}

// The architect could not plan in time: say so, and only point.
export function pointerFallbackDirective(): string {
  return '[RUNNER] The detailed plan could not be worked out in time. Be honest in one short sentence: you could not work out all the steps, but you will show them where to look. Do not invent steps.'
}
