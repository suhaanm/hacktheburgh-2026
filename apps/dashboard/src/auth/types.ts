/** Thin, optional sign-in (decision D22). The dashboard works fully signed out and offline. */

export type AuthStatus = "local" | "loading" | "signed_out" | "signed_in";

/** Only these fields ever exist client-side. Email and tokens are never read, kept or sent. */
export interface AuthUser {
  name: string;
  picture?: string;
  /** First 12 hex characters of SHA-256 of the Auth0 `sub`. The only identifier that may leave the browser. */
  subHash: string;
}

export type StepUpFailure = "cancelled" | "stale" | "different_account" | "error";

export interface StepUpResult {
  ok: boolean;
  method: "auth0_stepup" | "local";
  /** Present on success of an Auth0 step-up. */
  subHash?: string;
  reason?: StepUpFailure;
}

export interface AuthProvider {
  readonly kind: "local" | "auth0" | "fake";
  /** True only when Auth0 is configured. Local mode never asks anyone to sign in. */
  readonly enabled: boolean;
  status(): AuthStatus;
  signIn(): Promise<void>;
  signOut(): Promise<void>;
  /** A fresh re-authentication, for approvals that cannot be undone. Local mode resolves at once. */
  stepUp(): Promise<StepUpResult>;
  user(): AuthUser | null;
  /** Optional: notify the UI when status or user change. Returns an unsubscribe function. */
  subscribe?(listener: () => void): () => void;
}

/** What the engine receives with an approval. Additive: it ignores bodies it does not know. */
export interface ApprovalAuth {
  method: "auth0_stepup" | "local";
  sub_hash?: string;
}
