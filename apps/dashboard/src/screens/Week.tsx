import { TimeSection } from "../components/growth/TimeSection";

// This screen is now a section of Growth (docs/knack-ux/views.md). The old address redirects to it; this file only keeps the module resolving.
export default function Screen() {
  return <div className="page page--wide"><TimeSection open /></div>;
}
