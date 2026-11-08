// Every old route and where it lands now, so no deep link, bookmark, palette row, tour step or desktop link breaks (docs/KNACK_UX.md section 3,
// docs/knack-ux/views.md). Pure: no React, no window. router.ts applies it when the hash is read; the tests walk every old id.

export interface RouteTarget { path: string; query: URLSearchParams }

/** The first path segment of every route the app has had (21 before Knack, plus the Firm views that moved). Each one lands on a current address (routeRedirects.test.ts walks them). */
export const OLD_ROUTES = [
  "genome", "presence", "week", "routines", "briefing", "queue", "agents", "graph", "today", "memory", "privacy", "evidence", "onboarding",
  "growth", "models", "git", "notices", "home", "firm", "predictions", "repeats",
] as const;

/**
 * Old path (exact) to the new one, with the query it should carry. The old query is kept and wins over the target's, so `?person=`, `?story=` and an explicit `?section=` survive.
 * Section ids for Your data, Settings and Growth are the contract with the screens that draw them:
 *   Your data:  remembers, measured, sent, admin-sees, switches
 *   Settings:   live-models, interruptions, coaching, move-aside, open-at-login, appearance, models, views, about
 *   Growth:     progress, time, steps, map, commits   (docs/knack-ux/views.md: one page, five sections)
 * A worker has five destinations and nothing else, so Today, Week, Presence, Genome, Graph and Git are not places any more: their content is a Growth section
 * (or, for Today, Home). The Firm views are top-level addresses of their own (`/roles`, `/people`, `/brief`).
 */
const MAP: Record<string, string> = {
  "/queue": "/needs-you",
  "/briefing": "/needs-you",
  "/repeats": "/routines?tab=could-automate",
  "/privacy": "/your-data?section=sent",
  "/memory": "/your-data?section=remembers",
  "/notices": "/home?settings=interruptions",
  "/predictions": "/forecasts",
  "/settings": "/home?settings=live-models",
  "/today": "/home",
  "/week": "/growth?section=time",
  "/presence": "/growth?section=time",
  "/genome": "/growth?section=steps",
  "/graph": "/growth?section=map",
  "/git": "/growth?section=commits",
  "/firm/roles": "/roles",
  "/firm/onboarding": "/onboarding",
  "/firm/people": "/people",
  "/firm/automation": "/automation",
  "/firm/risk": "/risk",
  "/firm/forecasts": "/forecasts",
  "/firm/brief": "/brief",
};

const split = (to: string): { path: string; query: URLSearchParams } => {
  const [p, q = ""] = to.split("?");
  return { path: p, query: new URLSearchParams(q) };
};

/** The address as the router reads it: a leading slash, lower case (the first segment names a screen), no trailing slash. `#/Needs-You/` is `#/needs-you`. */
export function normalisePath(p: string): string {
  const withSlash = (p.startsWith("/") ? p : `/${p}`).toLowerCase();
  return withSlash.length > 1 ? withSlash.replace(/\/+$/, "") || "/" : withSlash;
}

/** The old set-up screen is Settings, "Set up again", at /setup (the admin Onboarding screen now owns /onboarding). */
export const SETUP_PATH = "/setup";

/**
 * Where a route really lands, or null when it is already canonical.
 * `view` matters for two routes only. In the Worker view the old `#/onboarding` meant the role set-up, so it lands on /setup (in the Admin view `/onboarding`
 * is the Onboarding speed screen and stays); and the old Agents screen is the worker's background tasks, which live on Routines (in the Admin view
 * `/agents` stays: it is "Background runs" under More).
 */
export function redirectFor(path: string, query: URLSearchParams, view: "worker" | "admin" = "worker"): RouteTarget | null {
  const p = path.length > 1 ? path.replace(/\/+$/, "") : path;
  if (p === "/onboarding" && view === "worker" && query.get("as") !== "admin") return { path: SETUP_PATH, query: new URLSearchParams(query) };
  if (p === "/agents" && view === "worker") return { path: "/routines", query: new URLSearchParams(query) };
  if (p === "/repeats" && query.get("as") === "admin") {
    const q = new URLSearchParams(query);
    q.delete("as");
    return { path: "/automation", query: q };
  }
  // A Firm sub-address that names no view reads as the Firm overview.
  const to = MAP[p] ?? (p.startsWith("/firm/") ? "/firm" : undefined);
  if (!to) return null;
  const t = split(to);
  const merged = new URLSearchParams(t.query);
  query.forEach((v, k) => merged.set(k, v));
  return { path: t.path, query: merged };
}

export const hashOf = (t: RouteTarget): string => {
  const q = t.query.toString();
  return q ? `${t.path}?${q}` : t.path;
};
