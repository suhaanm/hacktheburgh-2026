import { lazy, Suspense } from "react";
import { api } from "../../api";
import { useLoad } from "../../hooks";
import { Loading } from "../common";
import { GrowthSection } from "./GrowthSection";
import { cleanGraph, graphHeadline } from "../../lib/graph";

// The graph layer belongs to its own track: this section only mounts its screen in `embedded` mode (no title, no badge, no page wrapper)
// and prints one headline sentence from the same data.
const WorkGraph = lazy(() => import("../../screens/Graph"));

/** My routines map: the things Knack knows about the worker's own work, and how they connect. Names show on hover, focus or click. */
export function MapSection({ open }: { open: boolean }) {
  const g = useLoad(() => api.workGraph(), []);
  const sentence = g.data ? graphHeadline(cleanGraph(g.data)) : "";
  const headline = g.data ? (sentence || "Nothing is mapped yet. Knack adds things as it sees your work.") : g.status === "error" ? "Your routines map could not be read just now." : "Reading your routines map.";
  return (
    <GrowthSection id="map" title="How my routines connect" headline={headline} open={open} summary="See the map" busy={!g.data && g.status !== "error"}>
      <Suspense fallback={<Loading label="Loading the map" />}>
        <WorkGraph embedded />
      </Suspense>
    </GrowthSection>
  );
}
