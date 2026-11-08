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
const SETUP = import.meta.glob("./screens/{Settings/SetUp.tsx,Onboarding.tsx}");

export const screens: Record<Screen, ReturnType<typeof lazy>> = {
  home: lazy(() => import("./screens/Home")),
  "needs-you": prefer(pick(NEEDS_YOU, ["./screens/NeedsYou/index.tsx"])),
  routines: prefer(pick(ROUTINES, ["./screens/Routines/index.tsx"])),
  growth: lazy(() => import("./screens/Growth")),
  "your-data": prefer(pick(YOUR_DATA, ["./screens/YourData/index.tsx"])),
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
  setup: prefer(pick(SETUP, ["./screens/Settings/SetUp.tsx", "./screens/Onboarding.tsx"])),
};
