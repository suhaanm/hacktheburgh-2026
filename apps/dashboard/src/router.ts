import { useEffect, useState } from "react";
import { getViewRole } from "./components/home/viewAs";
import { hashOf, normalisePath, redirectFor } from "./routeRedirects";

export interface Route {
  path: string;
  query: URLSearchParams;
}

/**
 * The route ids: the first path segment of the address (`#/needs-you`, `#/roles`). A worker has five destinations (home, needs-you, routines,
 * growth, your-data); an admin has eight (firm, brief, forecasts, roles, people, onboarding, automation, risk) and three more behind More
 * (models, evidence, agents); first-run and setup have no sidebar; today (the live coach) has none either: it is unlisted, and Home opens it from one quiet
 * row while a coach step is active. Every older id (queue, briefing, repeats, privacy, memory, notices, predictions, week, presence, genome, graph, git,
 * and the /firm/<view> forms) is not a screen any more: routeRedirects.ts sends it to the new one
 * before anything renders (docs/knack-ux/views.md).
 */
export const SCREENS = [
  "home", "needs-you", "routines", "growth", "your-data",
  "firm", "brief", "forecasts", "roles", "people", "onboarding", "automation", "risk",
  "models", "evidence", "agents",
  "today",
  "first-run", "setup",
] as const;
export type Screen = (typeof SCREENS)[number];

/** Where the address lands when it names no screen. An admin lands on Firm instead (App.tsx). */
export const DEFAULT_SCREEN: Screen = "home";

/** Reads the hash, applies the old-route redirects (and rewrites the address, so a bookmark heals itself), and returns the canonical route. */
function read(): Route {
  const raw = window.location.hash.replace(/^#/, "") || `/${DEFAULT_SCREEN}`;
  const [p, q = ""] = raw.split("?");
  const path = normalisePath(p);
  const query = new URLSearchParams(q);
  const to = redirectFor(path, query, getViewRole());
  if (to) {
    try { window.history.replaceState(null, "", `#${hashOf(to)}`); } catch { /* a sandboxed frame cannot rewrite its address; the route is still right */ }
    return to;
  }
  return { path, query };
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(read);
  useEffect(() => {
    const on = () => setRoute(read());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return route;
}

export function navigate(path: string): void {
  window.location.hash = path.startsWith("/") ? path : `/${path}`;
}

export function screenOf(route: Route): Screen | "unknown" {
  const s = route.path.split("/")[1] as Screen;
  return (SCREENS as readonly string[]).includes(s) ? s : "unknown";
}
