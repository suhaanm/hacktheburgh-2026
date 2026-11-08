// Which file draws which route. Screens that other tracks are rebuilding (Needs you, Routines, Your data, the Settings contents, the set-up flow)
// are found with import.meta.glob, so this file builds whether or not a folder has landed in the branch being built. A glob that finds nothing
// shows nothing rather than a build error (the folders exist on main).
import { lazy, type ComponentType } from "react";
import type { Screen } from "./router";

type Loader = () => Promise<{ default: ComponentType }>;
type Glob = Record<string, () => Promise<unknown>>;

/** The first loader found, in the order given. `files` is a glob result; `order` lists the keys to try. */
export function pick(files: Glob, order: string[]): Loader | null {
  for (const key of order) {
    const hit = files[key];
    if (hit) return hit as Loader;
  }
  return null;
}

const Missing: ComponentType = () => null;
/** The screen when its folder exists, else an empty one. */
const prefer = (load: Loader | null, standIn: ComponentType = Missing): ReturnType<typeof lazy> => lazy(load ?? (async () => ({ default: standIn })));

const NEEDS_YOU = import.meta.glob("./screens/NeedsYou/index.tsx");
const ROUTINES = import.meta.glob("./screens/Routines/index.tsx");
const YOUR_DATA = import.meta.glob("./screens/YourData/index.tsx");

export const screens: Record<Screen, ReturnType<typeof lazy>> = {
  home: lazy(() => import("./screens/Home")),
  "needs-you": prefer(pick(NEEDS_YOU, ["./screens/NeedsYou/index.tsx"])),
  routines: prefer(pick(ROUTINES, ["./screens/Routines/index.tsx"])),
  // One page, five sections (docs/knack-ux/views.md). GrowthHost draws Track D's page and, until it draws a section itself, the older screen for it.
  growth: lazy(() => import("./screens/GrowthHost")),
  "your-data": prefer(pick(YOUR_DATA, ["./screens/YourData/index.tsx"])),
  // The Admin views are all drawn by the Firm screen, which reads which one from the address (navModel.firmTabOf).
  firm: lazy(() => import("./screens/Firm")),
  brief: lazy(() => import("./screens/Firm")),
  forecasts: lazy(() => import("./screens/Firm")),
  roles: lazy(() => import("./screens/Firm")),
  people: lazy(() => import("./screens/Firm")),
  onboarding: lazy(() => import("./screens/Firm")),
  automation: lazy(() => import("./screens/Firm")),
  risk: lazy(() => import("./screens/Firm")),
  models: lazy(() => import("./screens/Models")),
  evidence: lazy(() => import("./screens/Evidence")),
  agents: lazy(() => import("./screens/Agents")),
  "first-run": lazy(() => import("./screens/FirstRun")),
  // "Set up again" (Settings) reruns first run, the same three screens, from the top.
  setup: lazy(() => import("./screens/FirstRun")),
};
