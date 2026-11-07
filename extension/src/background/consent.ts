// L1 consent: which routines has the worker opted in? Read from the engine's GET /routines (spec 6.5 Routine
// objects). A routine is recording-enabled when its consent mode is shadow, approval or unattended and its
// status is not declined or never. Anything else records nothing at L1.
import { ACTOR, ACTOR_HEADER } from "../shared/actor";

export interface RoutineLike {
  id?: unknown;
  status?: unknown;
  consent?: { mode?: unknown } | null;
}

const OPTED_IN = new Set(["shadow", "approval", "unattended"]);
const ID_RE = /^[a-z][a-z0-9-]{2,40}$/;

export function l1Targets(payload: unknown): string[] {
  const list = Array.isArray(payload)
    ? payload
    : (typeof payload === "object" && payload !== null && Array.isArray((payload as { data?: unknown }).data))
      ? ((payload as { data: unknown[] }).data)
      : [];
  const out: string[] = [];
  for (const r of list as RoutineLike[]) {
    if (typeof r !== "object" || r === null) continue;
    const id = typeof r.id === "string" && ID_RE.test(r.id) ? r.id : null;
    const mode = r.consent && typeof r.consent === "object" ? r.consent.mode : undefined;
    const status = typeof r.status === "string" ? r.status : "";
    if (id && typeof mode === "string" && OPTED_IN.has(mode) && status !== "declined" && status !== "never") out.push(id);
  }
  return [...new Set(out)].sort();
}

/** Returns the target ids, or null when the engine could not be reached (keep the previous answer). */
export async function pollConsent(fetchFn: typeof fetch, engineUrl: string): Promise<string[] | null> {
  try {
    const res = await fetchFn(`${engineUrl}/routines`, { method: "GET", headers: { accept: "application/json", [ACTOR_HEADER]: ACTOR } });
    if (!res.ok) return null;
    return l1Targets(await res.json());
  } catch {
    return null;
  }
}
