import { useEffect, useState } from "react";

export interface Route {
  path: string;
  query: URLSearchParams;
}

export const SCREENS = ["genome", "presence", "routines", "queue", "graph", "today", "memory", "evidence", "onboarding"] as const;
export type Screen = (typeof SCREENS)[number];

function read(): Route {
  const raw = window.location.hash.replace(/^#/, "") || "/genome";
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
