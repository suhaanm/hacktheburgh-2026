// The offline measurement of the wake phrase matcher: the false-accept rate over ordinary sentences and the miss rate over accepted variants,
// each with a Wilson interval. Text in, numbers out. It says how the MATCHING LOGIC behaves on these strings; it does not say how often a real
// microphone and recogniser trigger it (see corpus-dev.ts).
import { matchWake } from './matching'
import { describeProportion, wilson, type Proportion } from './stats'

export interface Measurement {
  falseAccept: Proportion
  miss: Proportion
  falseAccepts: string[]
  misses: string[]
}

/** A negative is a false accept if it is accepted when settled, or accepted while the utterance is still growing (a partial result). */
export function isAccepted(text: string): boolean {
  return matchWake(text, { settled: true }).verdict === 'accept' || matchWake(text, { settled: false }).verdict === 'accept'
}

export function measure(negatives: readonly string[], positives: readonly string[]): Measurement {
  const falseAccepts = negatives.filter((s) => isAccepted(s))
  const misses = positives.filter((s) => matchWake(s, { settled: true }).verdict !== 'accept')
  return { falseAccept: wilson(falseAccepts.length, negatives.length), miss: wilson(misses.length, positives.length), falseAccepts, misses }
}

export const report = (name: string, m: Measurement): string =>
  `${name}: false accepts ${describeProportion(m.falseAccept)}; misses ${describeProportion(m.miss)}`
