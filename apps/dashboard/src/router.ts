import { useEffect, useState } from "react";

export interface Route {
  path: string;
  query: URLSearchParams;
}

export const SCREENS = ["genome", "presence", "week", "routines", "briefing", "queue", "agents", "graph", "today", "memory", "privacy", "evidence", "onboarding", "growth", "models", "git", "notices", "home", "firm", "predictions", "repeats"] as const;
export type Screen = (typeof SCREENS)[number];

/** Where the address lands when it names no screen. The lead can flip this to "genome" for a demo script that opens on the work ribbon. */
export const DEFAULT_SCREEN: Screen = "home";

function read(): Route {
  const raw = window.location.hash.replace(/^#/, "") || `/${DEFAULT_SCREEN}`;
  const [p, q = ""] = raw.split("?");
  const path = p.startsWith("/") ? p : `/${p}`;
  return { path, query: new URLSearchParams(q) };
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
