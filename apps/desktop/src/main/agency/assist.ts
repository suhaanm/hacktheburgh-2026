// Auto-assist hook: lets the lesson runner reach the EXISTING do_it_for_me flow (src/main/actuator/flow.ts, built in the
// dispatcher) without a parallel mechanism. The flow keeps every guard: real-click confirmation, denylist, scam/safety
// refusals, audit, Stop. Off unless ALONGSIDE_AUTO_ASSIST=1 (see teaching/index.ts) and settings.agency !== 'off'.
import type { DoItForMeResult } from '../../shared/protocol'

export type AssistFn = (args: { target: string }) => Promise<DoItForMeResult>

let current: AssistFn | null = null
export const setAssist = (fn: AssistFn | null): void => {
  current = fn
}
export const getAssist = (): AssistFn | null => current
export const autoAssistEnabled = (): boolean => process.env.ALONGSIDE_AUTO_ASSIST === '1'
