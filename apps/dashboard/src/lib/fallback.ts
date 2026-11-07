/**
 * Why a screen is showing example data instead of what the engine would send. Pure: no network, no React.
 * The screen prints `message` as plain text and a small "example data" badge; nothing here is ever hidden.
 */
export type FallbackKind = "offline" | "extension_off" | "missing" | "error";

export interface Fallback {
  kind: FallbackKind;
  message: string;
  /** HTTP status when the service answered; 0 when it could not be reached. */
  status: number;
  /** The engine's own error code, when it sent one. */
  code: string | null;
}

/** Error codes the services use for "this optional layer is switched off". */
const OFF_CODES = new Set(["extension_off", "extension_disabled"]);
const OFF_WORDS = /\b(layer|extension|feature)\b.*\b(is off|are off|off)\b|UNDERSTUDY_X/i;

export interface Failure {
  reached: boolean;
  status?: number;
  body?: unknown;
}

function errorOf(body: unknown): { code: string | null; message: string | null } {
  const e = body && typeof body === "object" ? (body as { error?: unknown }).error : null;
  if (e && typeof e === "object") {
    const o = e as { code?: unknown; message?: unknown };
    return { code: typeof o.code === "string" ? o.code : null, message: typeof o.message === "string" ? o.message : null };
  }
  const detail = body && typeof body === "object" ? (body as { detail?: unknown }).detail : null;
  return { code: null, message: typeof detail === "string" ? detail : null };
}

/** The environment variable that turns a layer on, to name in the message. */
export function classify(f: Failure, who: { service: string; flag?: string }): Fallback {
  if (!f.reached) {
    return { kind: "offline", status: 0, code: null, message: `${who.service} is not running, so Knack shows example data.` };
  }
  const status = f.status ?? 0;
  const { code, message } = errorOf(f.body);
  const off = (code != null && OFF_CODES.has(code)) || (status === 404 && message != null && OFF_WORDS.test(message));
  if (off) {
    return {
      kind: "extension_off", status, code,
      message: `This feature is switched off in ${who.service}${who.flag ? `. Start it with ${who.flag}=1 (or UNDERSTUDY_X=1 for every extension) to see your own data` : ""}. Until then Knack shows example data.`,
    };
  }
  if (status === 404 && (!message || message === "Not Found")) {
    return { kind: "missing", status, code, message: `${who.service} does not have this route yet, so Knack shows example data.` };
  }
  if (status === 405 || status === 501) {
    return { kind: "missing", status, code, message: `${who.service} does not support this yet, so Knack shows example data.` };
  }
  return {
    kind: "error", status, code,
    message: message ? `${who.service} said: ${message} Knack shows example data instead.` : `${who.service} answered with status ${status}, so Knack shows example data instead.`,
  };
}

/** A short label for the badge's tooltip. */
export const FALLBACK_LABEL: Record<FallbackKind, string> = {
  offline: "service not running",
  extension_off: "feature switched off",
  missing: "route not available",
  error: "the service reported a problem",
};

/**
 * The one plain line a screen prints when it shows example data. The engine's own sentence (a status, an error, a flag name) is never printed
 * in the page: it waits behind a Hint beside this line, for whoever wants it. Agents and HIT's Repeats screen use the same wording.
 */
export const EXAMPLE_LINE: Record<FallbackKind, string> = {
  offline: "Showing example data: the engine is not answering yet.",
  extension_off: "Showing example data: this feature is switched off in the engine.",
  missing: "Showing example data: the engine does not have this yet.",
  error: "Showing example data: the engine could not answer yet.",
};

/** Should the screen add a visible line under the badge? Offline and off are common and calm; an error must be read. */
export const needsNote = (f: Fallback | null | undefined): boolean => !!f;
