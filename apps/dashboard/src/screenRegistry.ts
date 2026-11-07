// Which file draws which route. Screens that other tracks are rebuilding (Needs you, Routines, Your data, the Settings contents, the set-up flow)
// are found with import.meta.glob, in order of preference, so this file builds before and after their folders land: until then
// the old screen stands in, and nothing here has to change when the new one arrives. A glob that finds nothing gives a calm fallback.
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
const lazyOf = (load: Loader | null): ReturnType<typeof lazy> => lazy(load ?? (async () => ({ default: Missing })));

const NEEDS_YOU = import.meta.glob("./screens/{NeedsYou/index.tsx,Queue.tsx}");
const ROUTINES = import.meta.glob("./screens/{Routines/index.tsx,Routines.tsx}");
const YOUR_DATA = import.meta.glob("./screens/{YourData/index.tsx,Memory.tsx}");
const SETUP = import.meta.glob("./screens/{Settings/SetUp.tsx,Onboarding.tsx}");

export const screens: Record<Screen, ReturnType<typeof lazy>> = {
  home: lazy(() => import("./screens/Home")),
  "needs-you": lazyOf(pick(NEEDS_YOU, ["./screens/NeedsYou/index.tsx", "./screens/Queue.tsx"])),
  routines: lazyOf(pick(ROUTINES, ["./screens/Routines/index.tsx", "./screens/Routines.tsx"])),
  growth: lazy(() => import("./screens/Growth")),
  "your-data": lazyOf(pick(YOUR_DATA, ["./screens/YourData/index.tsx", "./screens/Memory.tsx"])),
  firm: lazy(() => import("./screens/Firm")),
  roles: lazy(() => import("./screens/Firm")),
  onboarding: lazy(() => import("./screens/Firm")),
  genome: lazy(() => import("./screens/Genome")),
  presence: lazy(() => import("./screens/Presence")),
  graph: lazy(() => import("./screens/Graph")),
  week: lazy(() => import("./screens/Week")),
  git: lazy(() => import("./screens/Git")),
  forecasts: lazy(() => import("./screens/Predictions")),
  agents: lazy(() => import("./screens/Agents")),
  models: lazy(() => import("./screens/Models")),
  today: lazy(() => import("./screens/Today")),
  evidence: lazy(() => import("./screens/Evidence")),
  "first-run": lazy(() => import("./screens/FirstRun")),
  setup: lazyOf(pick(SETUP, ["./screens/Settings/SetUp.tsx", "./screens/Onboarding.tsx"])),
};
