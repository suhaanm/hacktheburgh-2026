// Public surface of the model port. Everything that needs a model imports from here.
import { wantsMock, type Env } from './env'
import { createMockProvider } from './mock'
import { createOpenAiProvider } from './openai'
import { createModelPort } from './port'
import type { BootReport, Log, ModelPort } from './types'

export * from './types'
export { ModelPortError, plainByCode, plainFailure, isEnvironmental } from './errors'
export type { ModelErrorCode } from './errors'
export { clamp01, parseModelJson, parseLooseJson, strictify } from './json'
export { redactText, redactArg, redactingLog } from './redact'
export { createModelPort } from './port'
export { createMockProvider, MOCK_IDS } from './mock'
export { createOpenAiProvider, usableModelIds, OPENAI_BASE_URL } from './openai'
export { modelIdsFromEnv, wantsMock, hasKey, ENV_VAR } from './env'

/** The one place a port is chosen: the mock when a mock flag is set, otherwise OpenAI (key and model IDs from the environment). */
export function createModelPortFromEnv(opts: { env?: Env; log?: Log } = {}): ModelPort {
  const env = opts.env ?? process.env
  const provider = wantsMock(env) ? createMockProvider() : createOpenAiProvider({ env, log: opts.log })
  return createModelPort(provider, { log: opts.log })
}

let boot: { at: number; report: BootReport } | null = null

/** Runs the boot check once (cached). Logs the verdict and, when not ok, the usable model IDs and what to do. Never throws. */
export async function runBootCheck(port: ModelPort, log: Log, force = false): Promise<BootReport> {
  if (boot && !force) return boot.report
  const report = await port.bootCheck()
  boot = { at: Date.now(), report }
  if (report.ok) log('model-port', `boot ok provider=${report.provider} planner=${report.configured.planner} fast=${report.configured.fast} computer_use=${report.configured.computer_use}`)
  else log('model-port', `boot check FAILED provider=${report.provider}: ${report.problem ?? 'unknown problem'}`)
  return report
}

export const lastBootReport = (): BootReport | null => boot?.report ?? null
