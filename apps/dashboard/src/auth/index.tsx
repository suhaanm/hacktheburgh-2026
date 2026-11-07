import { createContext, useContext, useEffect, useReducer, type ReactNode } from "react";
import { Auth0Auth } from "./Auth0Auth";
import { LocalAuth } from "./LocalAuth";
import type { AuthProvider } from "./types";

export type { ApprovalAuth, AuthProvider, AuthStatus, AuthUser, StepUpResult } from "./types";
export { authForApproval, needsStepUp, stepUpNotice } from "./gate";

/** Auth0 is on only when both public values are set (in apps/dashboard/.env.local, which git ignores). */
export function createAuth(env: Record<string, string | undefined> = import.meta.env as Record<string, string | undefined>): AuthProvider {
  const domain = env.VITE_AUTH0_DOMAIN?.trim();
  const clientId = env.VITE_AUTH0_CLIENT_ID?.trim();
  if (domain && clientId) return new Auth0Auth({ domain, clientId });
  return new LocalAuth();
}

const Ctx = createContext<AuthProvider>(new LocalAuth());

export function AuthContextProvider({ provider, children }: { provider: AuthProvider; children: ReactNode }) {
  return <Ctx.Provider value={provider}>{children}</Ctx.Provider>;
}

/** The provider, re-rendering the caller when the sign-in state changes. */
export function useAuth(): AuthProvider {
  const p = useContext(Ctx);
  const [, bump] = useReducer((n: number) => n + 1, 0);
  useEffect(() => p.subscribe?.(bump), [p]);
  return p;
}
