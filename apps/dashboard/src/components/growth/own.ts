import { ApiError } from "../../api";
import { useAppState } from "../../store";
import type { LoadState } from "../../hooks";

/**
 * Whose data a worker's section may ask for. A worker's screen draws their own work and nobody else's (docs/knack-ux/views.md), so a request never goes out
 * for "the default person" of a live engine: that would be somebody's week or somebody's case.
 *  - ready:   the engine has been asked who the worker is (or did not answer); until then a section waits.
 *  - blocked: the engine is live, is not in mock mode and does not know the worker yet: nothing is requested, and the section says nothing is recorded yet.
 *  - person:  the worker's own id; before they are known, the built-in example person when the screen shows example data (the engine is down or in mock mode).
 */
export function useOwnPerson(example?: string): { ready: boolean; blocked: boolean; person: string | undefined } {
  const app = useAppState();
  // Only an engine that says it is in mock mode (or none at all) may stand in with the built-in example person; an engine that does not say is treated as live.
  const live = app.engineUp === true && app.mock !== true;
  return { ready: app.extReady, blocked: app.extReady && live && !app.person, person: app.person ?? (live ? undefined : example) };
}

/** What a section's loader returns when the worker is not known: the same "nothing recorded" answer an unknown id gets. */
export const notKnown = <T,>(): Promise<T> => Promise.reject(new ApiError(404, "unknown_person", "No worker is known yet."));

/**
 * A live engine that answers "no such worker" (404 or 422) for the worker's own id has nothing recorded for them yet. The loader falls back to the built-in
 * example in that case; a worker's screen must not show it (it would be somebody else's week or case under an example tag), so it reads as an error the
 * section turns into "Nothing has been recorded for you yet". An engine that cannot be reached (status 0) still shows the example, under the example pill.
 */
export function unknownAsError<T>(s: LoadState<T>): LoadState<T> {
  const st = s.why?.status;
  if (st === 404 || st === 422) {
    return { ...s, data: null, meta: null, why: null, status: "error", error: new ApiError(st, s.why?.code ?? "unknown_person", "No data for this worker yet.") } as LoadState<T>;
  }
  return s;
}
