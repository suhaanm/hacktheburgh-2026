import type { Phase } from '../../shared/protocol'

export const PHASE_LABELS: Readonly<Record<Phase, string>> = {
  asleep: 'Resting',
  listening_for_name: 'Listening for my name',
  connecting: 'Getting ready',
  live: 'Listening',
  speaking: 'Speaking',
  thinking: 'Thinking',
  error: 'Something went wrong',
}
