// Switches and first-moment environment for the Knack shell, in plain code. The shell is ON by default; it is off for headless runs and with KNACK_SHELL=0.
import fs from 'node:fs'
import path from 'node:path'
import dotenv from 'dotenv'
import { applyStackEnv, resolveStackConfig, type ConfigInput } from './stack-config'
import type { StackConfig } from './stack'

export const knackShellEnabled = (env: Record<string, string | undefined>, headless: boolean): boolean => !headless && (env.KNACK_SHELL ?? '') !== '0'
/** KNACK_HIDDEN=1: every window exists and works but is never shown, and no Dock icon appears (the hidden check, and only that). */
export const knackHidden = (env: Record<string, string | undefined>): boolean => (env.KNACK_HIDDEN ?? '') === '1'

/**
 * Before anything reads the environment: where the repository is, which ports the services use, and (only when the repo's own .env exists) its keys,
 * loaded into this process the way index.ts already loads the app-level one. Nothing is printed, and a variable that is already set is never overridden.
 */
export function prepareKnackEnv(input: Omit<ConfigInput, 'exists' | 'readFile'> & { exists?: ConfigInput['exists']; readFile?: ConfigInput['readFile'] }): StackConfig {
  const exists = input.exists ?? ((p: string) => fs.existsSync(p))
  const readFile = input.readFile ?? ((p: string) => fs.readFileSync(p, 'utf8'))
  const config = resolveStackConfig({ ...input, exists, readFile })
  applyStackEnv(input.env, config.ports, null)
  if (config.repoRoot) {
    const dotenvFile = path.join(config.repoRoot, '.env')
    if (exists(dotenvFile)) dotenv.config({ path: dotenvFile, quiet: true, processEnv: input.env as NodeJS.ProcessEnv })
  }
  return config
}
