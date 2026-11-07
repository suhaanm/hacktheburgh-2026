import type { ApprovalAuth, AuthProvider, StepUpFailure } from "./types";

/** Items that cannot be undone, or that reach outside this machine, need a fresh sign-in when Auth0 is on. */
export const needsStepUp = (riskClass: string): boolean => riskClass === "irreversible" || riskClass === "outward";

export type Gate = { allowed: true; auth: ApprovalAuth } | { allowed: false; message: string };

const MESSAGE: Record<StepUpFailure, string> = {
  cancelled: "The sign-in was closed, so nothing was approved. The item is still waiting for you.",
  stale: "That sign-in was not recent enough, so nothing was approved. Sign in again to continue.",
  different_account: "You signed in with a different account from the one you started with, so nothing was approved.",
  error: "We could not complete the sign-in, so nothing was approved. The item is still waiting for you.",
};

/** The reason shown above the approve button when a fresh sign-in will be asked for. */
export function stepUpNotice(riskClass: string): string {
  return riskClass === "irreversible"
    ? "Approving this cannot be undone, so we ask you to sign in again."
    : "Approving this sends something outside your machine, so we ask you to sign in again.";
}

/**
 * Decide whether an approval may go to the engine, and with what proof.
 * Auth off: approve as before, saying "local". Auth on and the item is risky: a fresh sign-in is required.
 * Only a hash of the subject is ever returned.
 */
export async function authForApproval(auth: AuthProvider, riskClass: string): Promise<Gate> {
  if (!auth.enabled || !needsStepUp(riskClass)) return { allowed: true, auth: { method: "local" } };
  const r = await auth.stepUp();
  const subHash = r.subHash ?? auth.user()?.subHash;
  if (r.ok && r.method === "auth0_stepup" && subHash) return { allowed: true, auth: { method: "auth0_stepup", sub_hash: subHash } };
  return { allowed: false, message: MESSAGE[r.reason ?? "error"] };
}
