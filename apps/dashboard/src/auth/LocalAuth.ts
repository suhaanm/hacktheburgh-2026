import type { AuthProvider, AuthStatus, AuthUser, StepUpResult } from "./types";

/** Default. A local worker profile: no network, no sign-in, nothing to confirm. */
export class LocalAuth implements AuthProvider {
  readonly kind = "local" as const;
  readonly enabled = false;
  status(): AuthStatus { return "local"; }
  async signIn(): Promise<void> { /* nothing to sign in to */ }
  async signOut(): Promise<void> { /* nothing to sign out of */ }
  async stepUp(): Promise<StepUpResult> { return { ok: true, method: "local" }; }
  user(): AuthUser | null { return null; }
}
