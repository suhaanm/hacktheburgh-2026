/** How recently the person must have typed their credentials for an irreversible approval (seconds). */
export const MAX_AUTH_AGE_S = 120;

/** `auth_time` is seconds since the epoch, set by the identity provider. Missing means not fresh. */
export function isFresh(authTime: number | null | undefined, nowSec: number, maxAgeS = MAX_AUTH_AGE_S): boolean {
  if (typeof authTime !== "number" || !Number.isFinite(authTime)) return false;
  const age = nowSec - authTime;
  // A time in the future beyond clock skew is not trusted either.
  return age >= -maxAgeS && age <= maxAgeS;
}

/** First 12 hex characters of SHA-256 of the subject. The raw `sub` never leaves this function. */
export async function hashSub(sub: string): Promise<string> {
  const bytes = new TextEncoder().encode(sub);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest)).map((b) => b.toString(16).padStart(2, "0")).join("").slice(0, 12);
}

export const nowSec = (): number => Math.floor(Date.now() / 1000);
