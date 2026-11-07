/**
 * Request headers for the dashboard's calls to the engine and the agent service. Pure, so it can be tested.
 *
 * Every write (anything but GET or HEAD) sends `Content-Type: application/json` and `X-Understudy-Actor`. The services refuse a
 * browser write without the explicit actor header and refuse a body that is not JSON. The default actor is `worker`, the
 * person at the keyboard; `worker_approval` is for the buttons whose whole job is to approve something. The page never names
 * any other actor, so a script on a web page cannot pose as the agent or a model through this client.
 */
export type Actor = "worker" | "worker_approval";

const SAFE = new Set(["GET", "HEAD", "OPTIONS"]);
export const isWrite = (method: string): boolean => !SAFE.has(method.toUpperCase());

export function requestHeaders(method: string, actor?: Actor): Record<string, string> | undefined {
  if (!isWrite(method)) return undefined;
  return { "Content-Type": "application/json", "X-Understudy-Actor": actor ?? "worker" };
}

/** A write always carries a JSON body, an empty object when there is nothing to say. */
export function requestBody(method: string, payload: unknown): string | undefined {
  if (!isWrite(method)) return undefined;
  return JSON.stringify(payload === undefined ? {} : payload);
}

/** The response header the dev server sets when it had no per-boot token to add (see vite.proxy.ts). */
export const MISSING_HEADER = "x-understudy-proxy-token";

/**
 * A refused release action, in plain words. The services answer 403 with a token-related code when the per-boot token is absent
 * or wrong; the dev server flags the absent case itself. Either way the fix is the same: start everything again.
 * Returns null for any other refusal, which keeps its own message.
 */
export function notReadyReason(status: number, code: string | undefined, tokenMissing: boolean): string | null {
  if (status !== 403) return null;
  if (!tokenMissing && !(code && /token|not_ready|boot/i.test(code))) return null;
  return "The engine is not ready for this: it has not issued its start-up token to this page. Restart everything with `make dev`, wait for it to say it is running, then try again. Nothing was changed.";
}
