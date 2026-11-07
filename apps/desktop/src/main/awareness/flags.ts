// The awareness layer is off unless UNDERSTUDY_X_AWARENESS (or the master UNDERSTUDY_X) is set. Read on every call, never cached.
// Unlike feature-flags.ts there is NO "everything on under vitest" rule: a test turns the flag on by passing an env on purpose.
const TRUE = new Set(['1', 'true', 'yes', 'on'])
const on = (v: string | undefined): boolean => TRUE.has((v ?? '').trim().toLowerCase())

export function awarenessFlagOn(env: Record<string, string | undefined> = process.env): boolean {
  return on(env.UNDERSTUDY_X) || on(env.UNDERSTUDY_X_AWARENESS)
}
