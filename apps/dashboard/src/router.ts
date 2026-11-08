import { useEffect, useState } from "react";
import { getViewRole } from "./components/home/viewAs";
import { hashOf, normalisePath, redirectFor } from "./routeRedirects";

export interface Route {
  path: string;
  query: URLSearchParams;
}

/**
 * The route ids: the first path segment of the address (`#/needs-you`, `#/firm/people`). Knack has five worker destinations
 * (home, needs-you, routines, growth, your-data), three admin ones (firm, roles, onboarding), the screens under More, and two
 * screens without a sidebar (first-run, setup). Old ids (queue, briefing, repeats, privacy, memory, notices, predictions) are not
 * screens any more: routeRedirects.ts sends them to the new ones before anything renders.
 */
export const SCREENS = [
  "home", "needs-you", "routines", "growth", "your-data",
  "firm", "roles", "onboarding",
  "genome", "presence", "graph", "week", "git", "forecasts", "agents", "models", "today", "evidence",
  "first-run", "setup",
] as const;
export type Screen = (typeof SCREENS)[number];

/** Where the address lands when it names no screen. The lead can flip this to "genome" for a walk-through that opens on the work ribbon. */
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
