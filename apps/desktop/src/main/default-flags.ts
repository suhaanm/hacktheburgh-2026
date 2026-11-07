// D48 (owner, 7 Nov 2026): the product runs with its voice and extension layers on without any environment variable. This runs FIRST in the
// main process, right AFTER dotenv has loaded .env (index.ts calls applyDesktopDefaultFlags): an unset or empty variable becomes '1'; an explicit '0', in the shell or in .env, wins. Not defaulted, on purpose:
// the real-desktop arm switches (UNDERSTUDY_REAL_ACTUATOR, ALONGSIDE_AGENCY_LOOP, UNDERSTUDY_JXA_CLICK), UNDERSTUDY_LEGACY_REMOTE, the old
// wake, scam and files flags, and the debug and held-out guards. See docs/FLAGS.md.
export const DESKTOP_DEFAULT_ON = ['UNDERSTUDY_X', 'UNDERSTUDY_VOICE', 'UNDERSTUDY_FLAG_VOICE', 'UNDERSTUDY_X_CUE', 'UNDERSTUDY_X_AWARENESS', 'UNDERSTUDY_X_GEMINI', 'UNDERSTUDY_X_LIVE'] as const

export function applyDesktopDefaultFlags(env: Record<string, string | undefined> = process.env): string[] {
  const set: string[] = []
  for (const name of DESKTOP_DEFAULT_ON) {
    if (env[name] === undefined || env[name]?.trim() === '') {
      env[name] = '1'
      set.push(name)
    }
  }
  return set
}
