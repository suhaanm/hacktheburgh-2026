// Environment access for the model port. This and openai.ts are the only files that read OPENAI_*.
// Model IDs are NEVER defaulted here: an unset ID is an error the boot check reports in plain English.
import type { ModelIds, ModelTier } from './types'

export type Env = Record<string, string | undefined>

export const ENV_VAR: Record<ModelTier, string> = {
  planner: 'OPENAI_MODEL_PLANNER',
  fast: 'OPENAI_MODEL_FAST',
  computer_use: 'OPENAI_MODEL_COMPUTER_USE',
}

const clean = (v: string | undefined): string => (typeof v === 'string' ? v.trim() : '')

export function modelIdsFromEnv(env: Env = process.env): ModelIds {
  return {
    planner: clean(env[ENV_VAR.planner]),
    fast: clean(env[ENV_VAR.fast]),
    computer_use: clean(env[ENV_VAR.computer_use]),
  }
}

export const hasKey = (env: Env = process.env): boolean => clean(env.OPENAI_API_KEY).length > 0

/** The mock provider runs when either mock flag is set (Alongside's or ours), or when there is no key at all. */
export function wantsMock(env: Env = process.env): boolean {
  return env.UNDERSTUDY_MOCK === '1' || env.ALONGSIDE_MOCK === '1'
}
