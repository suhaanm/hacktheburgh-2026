import { isFresh, nowSec } from "./fresh";
import type { AuthProvider, AuthStatus, AuthUser, StepUpFailure, StepUpResult } from "./types";

export interface FakeAuthOptions {
  /** Pretend Auth0 is configured. Default true. */
  enabled?: boolean;
  /** How old the re-authentication is when step-up returns, in seconds. Default 5. */
  authAgeSec?: number;
  /** The person closes the popup. */
  cancel?: boolean;
  /** The person signs in as someone else. */
  otherAccount?: boolean;
  subHash?: string;
}

/** For tests. Applies the same freshness rule as the real provider and counts how often step-up ran. */
export class FakeAuth implements AuthProvider {
  readonly kind = "fake" as const;
  readonly enabled: boolean;
  stepUpCalls = 0;
  signInCalls = 0;
  private signedIn = false;
  constructor(private opts: FakeAuthOptions = {}) { this.enabled = opts.enabled ?? true; }
  status(): AuthStatus { return !this.enabled ? "local" : this.signedIn ? "signed_in" : "signed_out"; }
  async signIn(): Promise<void> { this.signInCalls++; this.signedIn = true; }
  async signOut(): Promise<void> { this.signedIn = false; }
  user(): AuthUser | null { return this.signedIn ? { name: "Test Worker", subHash: this.opts.subHash ?? "abcdef012345" } : null; }
  async stepUp(): Promise<StepUpResult> {
    this.stepUpCalls++;
    if (!this.enabled) return { ok: true, method: "local" };
    const fail = (reason: StepUpFailure): StepUpResult => ({ ok: false, method: "auth0_stepup", reason });
    if (this.opts.cancel) return fail("cancelled");
    if (this.opts.otherAccount) return fail("different_account");
    const now = nowSec();
    if (!isFresh(now - (this.opts.authAgeSec ?? 5), now)) return fail("stale");
    this.signedIn = true;
    return { ok: true, method: "auth0_stepup", subHash: this.opts.subHash ?? "abcdef012345" };
  }
}
