// Stand-ins for the destinations whose new screens another track is still building. Until screens/NeedsYou, screens/Routines (folder),
// screens/YourData and screens/Settings exist, a route shows the old screens that held the same things, so no route is blank and no feature
// goes missing. screenRegistry.ts prefers the new folder the moment it appears, so nothing here needs deleting for the swap.
import { Suspense, lazy, type ComponentType } from "react";
import { useRoute } from "./router";

type Loader = () => Promise<{ default: ComponentType }>;
const OLD = import.meta.glob("./screens/{Queue.tsx,Briefing.tsx,Routines.tsx,Memory.tsx,Privacy.tsx,Notices.tsx,Repeats/index.tsx}");
const part = (key: string): ComponentType | null => (OLD[key] ? (lazy(OLD[key] as Loader) as unknown as ComponentType) : null);

const Queue = part("./screens/Queue.tsx");
const Briefing = part("./screens/Briefing.tsx");
const Routines = part("./screens/Routines.tsx");
const Repeats = part("./screens/Repeats/index.tsx");
const Memory = part("./screens/Memory.tsx");
const Privacy = part("./screens/Privacy.tsx");
export const Notices = part("./screens/Notices.tsx");

function Stack({ parts }: { parts: (ComponentType | null)[] }) {
  return <Suspense fallback={null}>{parts.map((P, i) => (P ? <P key={i} /> : null))}</Suspense>;
}

/** Needs you: the approval queue, then the briefing cards. */
export function NeedsYouLegacy() { return <Stack parts={[Queue, Briefing]} />; }
/** Routines: what runs (Routines), or what could run (Repeats) when the address asks for that tab. */
export function RoutinesLegacy() { return <Stack parts={[useRoute().query.get("tab") === "could-automate" ? Repeats : Routines]} />; }
/** Your data: the record of what was sent when the address asks for it, else what Knack remembers. */
export function YourDataLegacy() { const s = useRoute().query.get("section"); return <Stack parts={[s === "sent" ? Privacy : Memory]} />; }
