// The demo "view as" role. Worker or Admin. Held in memory only (a page reload goes back to Worker), so nothing about it is ever
// stored, sent or mistaken for a real permission: a real deployment would take the role from the identity provider (D42).
// A tiny external store so any component can read it without a provider.
import { useSyncExternalStore } from "react";

export type ViewRole = "worker" | "admin";

let current: ViewRole = "worker";
const listeners = new Set<() => void>();

export const getViewRole = (): ViewRole => current;

export function setViewRole(next: ViewRole): void {
  if (next !== "worker" && next !== "admin") return;
  if (next === current) return;
  current = next;
  listeners.forEach((l) => l());
}

export function useViewRole(): ViewRole {
  return useSyncExternalStore(
    (cb) => { listeners.add(cb); return () => listeners.delete(cb); },
    () => current,
    () => "worker" as ViewRole,
  );
}

/** For tests: back to the default. */
export function resetViewRole(): void { current = "worker"; listeners.forEach((l) => l()); }

export const VIEW_LABEL: Record<ViewRole, string> = { worker: "Worker", admin: "Admin" };
/** The marker an admin-audience screen shows. It says the role is a demo, so nobody takes it for a permission. */
export const ADMIN_MARKER = "Admin view (demo role)";
