// Live models or models off? Decided once at start, in plain code:
//
//   the worker's switch "Use live models" is on (the default), AND a Gemini key is present in the environment (the repo's own .env is loaded into it), AND the
//   models boot check passes   ->  live: real models, the isolated data/live-home and data/live-data (what `make live` does)
//   anything else              ->  models off: offline models, data/demo-home and data/demo-data (what `make demo` does), with one calm line saying so
//
// The key is only ever tested for being there; its value is never read into a message or a log. The boot check is injected (it lists the models the key
// can use) and has a time limit: a slow or failing check means models off, never a hang.
import type { StackMode } from './stack'

export const MODELS_OFF_NOTICE = 'Models are off'
export const LIVE_NOTICE = 'Live models'

export type ModelReason = 'live' | 'switched_off' | 'no_key' | 'boot_check_failed'

export interface ModelDecision {
  mode: StackMode
  reason: ModelReason
  /** The one line shown with the status dot; null when everything is live and there is nothing to explain. */
  notice: string | null
}

export interface ModelInputs {
  /** The worker's switch (settings.useLiveModels). */
  switchOn: boolean
  /** KNACK_LIVE: '0' forces models off, '1' asks for live (the key and the check still apply). */
  envOverride?: string
  hasKey: boolean
  /** null: the check was not run (no key, or switched off). */
  bootOk: boolean | null
}

/** The wish, before the key and the check: should live even be tried? */
export function wantsLive(i: Pick<ModelInputs, 'switchOn' | 'envOverride'>): boolean {
  if (i.envOverride === '0') return false
  if (i.envOverride === '1') return true
  return i.switchOn
}

export function decideModels(i: ModelInputs): ModelDecision {
  if (!wantsLive(i)) return { mode: 'demo', reason: 'switched_off', notice: MODELS_OFF_NOTICE }
  if (!i.hasKey) return { mode: 'demo', reason: 'no_key', notice: MODELS_OFF_NOTICE }
  if (i.bootOk === false) return { mode: 'demo', reason: 'boot_check_failed', notice: MODELS_OFF_NOTICE }
  return { mode: 'live', reason: 'live', notice: null }
}

/** True when the variable holds anything but whitespace. Never returns, logs or formats the value. */
export const keyPresent = (env: Record<string, string | undefined>, name = 'GEMINI_API_KEY'): boolean => (env[name] ?? '').trim().length > 0

/** Runs the boot check with a time limit; a throw or a timeout counts as failed. */
export async function boundedBootCheck(check: () => Promise<boolean>, limitMs: number, wait: (ms: number) => Promise<void> = (ms) => new Promise((r) => setTimeout(r, ms))): Promise<boolean> {
  try {
    return await Promise.race([check(), wait(limitMs).then(() => false)])
  } catch {
    return false
  }
}

/**
 * The full plan: apply the switch and the key, run the check only when it can matter, and say what happened. `bootCheck` runs only when live is wanted and a key is
 * present, once when it passes. A failed check is tried once more after a short pause, because a busy Mac or a slow first connection must not switch the models
 * off for the whole session (the mode is decided once, at start).
 */
export async function planModels(i: Omit<ModelInputs, 'bootOk'> & { bootCheck: () => Promise<boolean>; limitMs?: number; attempts?: number; pauseMs?: number; wait?: (ms: number) => Promise<void> }): Promise<ModelDecision> {
  const base = { switchOn: i.switchOn, envOverride: i.envOverride, hasKey: i.hasKey }
  if (!wantsLive(base) || !i.hasKey) return decideModels({ ...base, bootOk: null })
  const wait = i.wait ?? ((ms: number) => new Promise<void>((r) => setTimeout(r, ms)))
  const attempts = Math.max(1, Math.min(3, Math.trunc(i.attempts ?? 2)))
  let ok = false
  for (let n = 0; n < attempts && !ok; n += 1) {
    if (n > 0) await wait(i.pauseMs ?? 1000)
    ok = await boundedBootCheck(i.bootCheck, i.limitMs ?? 8000, i.wait)
  }
  return decideModels({ ...base, bootOk: ok })
}

/** The status the person sees next to the dot: what is running, not what was asked for. `mock` is the agent service's own answer (null: unknown). */
export function modelStatus(mock: boolean | null, decision: ModelDecision | null): { live: boolean | null; text: string } {
  if (mock === true) return { live: false, text: MODELS_OFF_NOTICE }
  if (mock === false) return { live: true, text: LIVE_NOTICE }
  if (decision) return { live: decision.mode === 'live', text: decision.mode === 'live' ? LIVE_NOTICE : MODELS_OFF_NOTICE }
  return { live: null, text: '' }
}

/** Whether the Use live models switch may change now, and why not. Pure; the shell asks it before it patches the setting. */
export function canSwitchModels(i: { on: unknown; hasKey: boolean; running: boolean }): { ok: true } | { ok: false; reason: 'no_key' | 'running' | 'bad_request' } {
  if (typeof i.on !== 'boolean') return { ok: false, reason: 'bad_request' }
  if (i.running) return { ok: false, reason: 'running' } // "A job is running. Stop it first."
  if (i.on && !i.hasKey) return { ok: false, reason: 'no_key' } // "No Gemini key found. Add it to .env and reopen Knack."
  return { ok: true }
}
