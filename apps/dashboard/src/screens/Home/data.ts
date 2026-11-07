// Data for the worker home ("Your week"): the pointers, the reason behind each, what an admin can see, and the feedback that can only
// make things quieter. Reads `/insights/*` (worker routes never return admin data). Example data answers when the engine cannot.
import type { Loaded } from "../../api";
import { insightRead, insightWrite, qs } from "../../components/firm/net";
import { normaliseSharing, normaliseWhy, normaliseWorker } from "../../components/firm/model";
import type { WirePointer, WireSharing, WireWhy, WireWorker } from "../../components/firm/wire";
import workerFx from "../../fixtures/home-worker.json";
import whyFx from "../../fixtures/home-why.json";
import sharingFx from "../../fixtures/home-sharing.json";

export type WorkerStory = "pointers" | "quiet" | "onboarding";
export const STORY_LABEL: Record<WorkerStory, string> = { pointers: "Three pointers", quiet: "Nothing stands out", onboarding: "Just started" };
export const WORKER_STORIES: WorkerStory[] = ["pointers", "quiet", "onboarding"];

const NOTHING = "Nothing stands out this week.";
const STARTING = "Understudy is still learning how you work.";

/** The example week for a story: the engine's sample, changed only in ways the engine itself can answer (no pointers, with a fixed message). */
export function exampleWorker(story: WorkerStory): unknown {
  const base = JSON.parse(JSON.stringify(workerFx)) as { data: Record<string, unknown>; meta: Record<string, unknown> };
  if (story === "quiet") {
    Object.assign(base.data, { pointers: [], status: "nothing_stands_out", nothing_stands_out: true, message: NOTHING, monday_note: null });
    base.meta.n = 0;
  } else if (story === "onboarding") {
    Object.assign(base.data, { pointers: [], status: "onboarding", nothing_stands_out: true, message: STARTING, monday_note: null });
    base.meta.n = 0;
  }
  return base;
}

export const parseStory = (q: string | null): WorkerStory => (q === "quiet" || q === "onboarding" ? q : "pointers");

export function loadWorker(person: string | null, story: WorkerStory = "pointers"): Promise<Loaded<WireWorker>> {
  return insightRead(`/insights/worker${qs({ person })}`, "worker", () => exampleWorker(story), normaliseWorker);
}

/** The reason behind a pointer. In example mode a pointer the sample does not cover gets the same fixed limits and its own headline. */
export function exampleWhy(id: string, headline: string): unknown {
  const sample = whyFx as unknown as { data: { id: string; because: string[]; limits: string[]; sources: unknown[] } };
  if (sample.data.id === id) return sample;
  return {
    meta: (whyFx as unknown as { meta: unknown }).meta,
    data: { id, headline, because: ["It compares your recent weeks with the weeks before, on this skill only."], limits: sample.data.limits, sources: sample.data.sources, state: "selected", reason_text: "Selected: it passed every check and scored among the highest." },
  };
}

export function loadWhy(p: Pick<WirePointer, "id" | "headline">, person: string | null): Promise<Loaded<WireWhy>> {
  return insightRead(`/insights/why${qs({ insight: p.id, person })}`, "worker", () => exampleWhy(p.id, p.headline), normaliseWhy);
}

export function loadSharing(person: string | null): Promise<Loaded<WireSharing>> {
  return insightRead(`/insights/sharing${qs({ person })}`, "worker", () => sharingFx, normaliseSharing);
}

export type FeedbackEvent = "useful" | "not_useful" | "dismissed" | "done" | "never_show";

/** Feedback only ever makes things quieter, and "done" and "dismissed" count as seen. In example mode it is kept on this page only. */
export function sendFeedback(insight: string, event: FeedbackEvent, person: string | null): Promise<{ source: "live" | "demo" }> {
  return insightWrite(`/insights/feedback${qs({ person })}`, { insight, event });
}
