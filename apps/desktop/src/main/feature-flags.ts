// Feature flags for the parts of Alongside that Understudy keeps but does not ship switched on: voice (the Live session),
// the wake word, scam analysis and files search. They are OFF unless the matching environment variable is '1':
//   UNDERSTUDY_FLAG_VOICE=1  UNDERSTUDY_FLAG_WAKE=1  UNDERSTUDY_FLAG_SCAM=1  UNDERSTUDY_FLAG_FILES=1
// Voice and the wake word still need the Gemini key (src/main/live-auth.ts, src/renderer/live, src/renderer/wake); nothing in
// the OpenAI model port provides them. Under vitest (VITEST set) every flag is on unless set to '0', so the kept code stays tested.
export type Feature = 'voice' | 'wake' | 'scam' | 'files'

export const FEATURES: readonly Feature[] = ['voice', 'wake', 'scam', 'files']

export const flagVar = (f: Feature): string => `UNDERSTUDY_FLAG_${f.toUpperCase()}`

export function featureOn(f: Feature, env: Record<string, string | undefined> = process.env): boolean {
  const v = env[flagVar(f)]
  if (v === '1') return true
  if (v === '0') return false
  return env.VITEST !== undefined && env.VITEST !== ''
}

export function offMessage(f: Feature): string {
  const what: Record<Feature, string> = {
    voice: 'Voice is switched off in this build.',
    wake: 'The wake word is switched off in this build.',
    scam: 'Scam checking is switched off in this build.',
    files: 'File search is switched off in this build.',
  }
  return what[f]
}

/** Settings pinned by the flags: a switched-off feature cannot be enabled from the settings UI or by a patch. */
export function forcedSettings(env: Record<string, string | undefined> = process.env): { wakeEnabled?: false; filesEnabled?: false } {
  return { ...(featureOn('wake', env) ? {} : { wakeEnabled: false as const }), ...(featureOn('files', env) ? {} : { filesEnabled: false as const }) }
}
