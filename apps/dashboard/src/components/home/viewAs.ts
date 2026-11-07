// The "view as" role: Worker or Admin. It only changes what the screens show; it is not a permission (a real deployment takes the role
// from the identity provider, D42). Knack remembers the choice on this device so the owner's walk-through does not have to repeat it
// (docs/KNACK_UX.md section 3: "View as Admin (remembered)"). The stored value is the word "admin" or nothing; storage can be blocked.
// A tiny external store so any component can read it without a provider.
import { useSyncExternalStore } from "react";

export type ViewRole = "worker" | "admin";

export const VIEW_STORAGE_KEY = "understudy-view-as";

function stored(): ViewRole {
  try { return window.localStorage.getItem(VIEW_STORAGE_KEY) === "admin" ? "admin" : "worker"; } catch { return "worker"; }
}
function remember(v: ViewRole): void {
  try {
    if (v === "admin") window.localStorage.setItem(VIEW_STORAGE_KEY, "admin");
    else window.localStorage.removeItem(VIEW_STORAGE_KEY);
  } catch { /* storage can be blocked: the choice then lasts until reload */ }
}

let current: ViewRole = typeof window === "undefined" ? "worker" : stored();
const listeners = new Set<() => void>();

export const getViewRole = (): ViewRole => current;

export function setViewRole(next: ViewRole): void {
  if (next !== "worker" && next !== "admin") return;
  if (next === current) return;
  current = next;
  remember(next);
  listeners.forEach((l) => l());
}

export function useViewRole(): ViewRole {
  return useSyncExternalStore(
    (cb) => { listeners.add(cb); return () => listeners.delete(cb); },
    () => current,
    () => "worker" as ViewRole,
  );
}

/** For tests: back to the default, and forget the stored choice. */
export function resetViewRole(): void { current = "worker"; remember("worker"); listeners.forEach((l) => l()); }

export const VIEW_LABEL: Record<ViewRole, string> = { worker: "Worker", admin: "Admin" };
/** The marker an admin-audience screen shows. It says the role is a view, so nobody takes it for a permission. */
export const ADMIN_MARKER = "Admin view";
