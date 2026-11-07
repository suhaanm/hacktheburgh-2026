// The attention layer is off unless UNDERSTUDY_X_ATTENTION=1 or the master UNDERSTUDY_X=1 (the engine reads the same two). Off: nothing is created,
// no timer runs and no request is made, so the P0 demo path is untouched.
const TRUE = new Set(['1', 'true', 'yes', 'on'])
const on = (v: string | undefined): boolean => TRUE.has((v ?? '').trim().toLowerCase())

export function attentionEnabled(env: Record<string, string | undefined> = process.env): boolean {
  return on(env.UNDERSTUDY_X) || on(env.UNDERSTUDY_X_ATTENTION)
}
