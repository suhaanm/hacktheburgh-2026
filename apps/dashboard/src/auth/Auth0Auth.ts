import type { Auth0Client } from "@auth0/auth0-spa-js";
import { hashSub, isFresh, nowSec } from "./fresh";
import type { AuthProvider, AuthStatus, AuthUser, StepUpResult } from "./types";

export interface Auth0Config {
  domain: string;
  clientId: string;
}

/**
 * Auth0 with Authorization Code + PKCE in a popup, Google connection, tokens held in memory only.
 * There is no client secret anywhere. Only the name, the picture and a hash of the subject are kept;
 * the email and the tokens are never read out of the SDK. The library loads only when this class is built,
 * which happens only when both VITE_AUTH0_DOMAIN and VITE_AUTH0_CLIENT_ID are set.
 */
export class Auth0Auth implements AuthProvider {
  readonly kind = "auth0" as const;
  readonly enabled = true;
  private ready: Promise<Auth0Client>;
  private current: AuthUser | null = null;
  private busy = false;
  private listeners = new Set<() => void>();

  constructor(cfg: Auth0Config) {
    this.ready = import("@auth0/auth0-spa-js").then(
      ({ Auth0Client: Client }) =>
        new Client({
          domain: cfg.domain,
          clientId: cfg.clientId,
          cacheLocation: "memory",
          useRefreshTokens: false,
          authorizationParams: { redirect_uri: window.location.origin, scope: "openid profile" },
        }),
    );
    // Do not let a failed library load become an unhandled rejection; it surfaces when the person tries to sign in.
    this.ready.catch(() => undefined);
  }

  status(): AuthStatus { return this.busy ? "loading" : this.current ? "signed_in" : "signed_out"; }
  user(): AuthUser | null { return this.current; }
  subscribe(l: () => void): () => void { this.listeners.add(l); return () => this.listeners.delete(l); }
  private emit() { this.listeners.forEach((l) => l()); }

  private async readUser(c: Auth0Client): Promise<AuthUser> {
    const [claims, u] = await Promise.all([c.getIdTokenClaims(), c.getUser()]);
    const sub = claims?.sub ?? u?.sub ?? "";
    return { name: u?.name ?? u?.nickname ?? "Signed in", picture: u?.picture, subHash: await hashSub(sub) };
  }

  async signIn(): Promise<void> {
    this.busy = true; this.emit();
    try {
      const c = await this.ready;
      await c.loginWithPopup({ authorizationParams: { connection: "google-oauth2" } });
      this.current = await this.readUser(c);
    } finally { this.busy = false; this.emit(); }
  }

  async signOut(): Promise<void> {
    const c = await this.ready;
    // Local sign-out only: clears the in-memory session. It does not open the identity provider.
    await c.logout({ openUrl: false });
    this.current = null;
    this.emit();
  }

  /** A fresh login in a popup. The ID token's auth_time must be within 120 s, and it must be the same account. */
  async stepUp(): Promise<StepUpResult> {
    const fail = (reason: NonNullable<StepUpResult["reason"]>): StepUpResult => ({ ok: false, method: "auth0_stepup", reason });
    try {
      const c = await this.ready;
      await c.loginWithPopup({ authorizationParams: { prompt: "login", max_age: 0 } });
      const claims = await c.getIdTokenClaims();
      if (!isFresh(typeof claims?.auth_time === "number" ? claims.auth_time : null, nowSec())) return fail("stale");
      const next = await this.readUser(c);
      if (this.current && this.current.subHash !== next.subHash) return fail("different_account");
      this.current = next;
      this.emit();
      return { ok: true, method: "auth0_stepup", subHash: next.subHash };
    } catch (e) {
      const name = e instanceof Error ? e.name : "";
      return fail(/Popup(Cancelled|Timeout)Error/.test(name) || /closed|cancel/i.test(String(e)) ? "cancelled" : "error");
    }
  }
}
