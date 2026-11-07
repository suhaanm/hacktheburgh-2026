// Data for the worker home ("Your week"): the pointers, the reason behind each, what an admin can see, and the feedback that can only
// make things quieter. Reads `/insights/*` (worker routes never return admin data). Example data answers when the engine cannot.
import type { Loaded } from "../../api";
import { insightRead, insightWrite, qs } from "../../components/firm/net";
import { normaliseSharing, normaliseWhy, normaliseWorker } from "../../components/firm/model";
import type { WirePointer, WireSharing, WireWhy, WireWorker } from "../../components/firm/wire";
import workerFx from "../../fixtures/home-worker.json";
import workerGoodFx from "../../fixtures/home-worker-good.json";
import whyFx from "../../fixtures/home-why.json";
import sharingFx from "../../fixtures/home-sharing.json";
import { APP_NAME } from "../../brand";

export type WorkerStory = "pointers" | "good" | "quiet" | "onboarding";
export const STORY_LABEL: Record<WorkerStory, string> = { pointers: "Worth a look", good: "Going well", quiet: "Nothing stands out", onboarding: "Just started" };
export const WORKER_STORIES: WorkerStory[] = ["pointers", "good", "quiet", "onboarding"];

const NOTHING = "Nothing stands out this week.";
const STARTING = `${APP_NAME} is still learning how you work.`;

/** The example week for a story: the engine's sample, changed only in ways the engine itself can answer (no pointers, with a fixed message). */
export function exampleWorker(story: WorkerStory): unknown {
  const base = JSON.parse(JSON.stringify(story === "good" ? workerGoodFx : workerFx)) as { data: Record<string, unknown>; meta: Record<string, unknown> };
  if (story === "quiet") {
    Object.assign(base.data, { pointers: [], status: "nothing_stands_out", nothing_stands_out: true, message: NOTHING, monday_note: null });
    base.meta.n = 0;
  } else if (story === "onboarding") {
    Object.assign(base.data, { pointers: [], status: "onboarding", nothing_stands_out: true, message: STARTING, monday_note: null });
    base.meta.n = 0;
  }
  return base;
}

export const parseStory = (q: string | null): WorkerStory => (q === "good" || q === "quiet" || q === "onboarding" ? q : "pointers");

/** What the page shows when the engine knows nobody yet: no pointers, and a fixed line pointing at set-up. */
const NOT_SET_UP = { data: { pointers: [], status: "onboarding", nothing_stands_out: true, message: `Choose your role first. ${APP_NAME} then starts learning how you work, and says nothing until it has something worth your time.` } };

export function loadWorker(person: string | null, story: WorkerStory = "pointers"): Promise<Loaded<WireWorker>> {
  return insightRead(`/insights/worker${qs({ person })}`, "worker", () => exampleWorker(story), normaliseWorker, { unknownPerson: () => NOT_SET_UP });
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
  return insightRead(`/insights/sharing${qs({ person })}`, "worker", () => sharingFx, normaliseSharing, {
    unknownPerson: () => ({ data: { items: [], never: [], notice: "Nothing is shared yet, because nothing is set up. Once you choose a role, this page lists exactly what an admin could see." } }),
  });
}

export type FeedbackEvent = "useful" | "not_useful" | "dismissed" | "done" | "never_show";

/** Feedback only ever makes things quieter, and "done" and "dismissed" count as seen. In example mode it is kept on this page only. */
export function sendFeedback(insight: string, event: FeedbackEvent, person: string | null): Promise<{ source: "live" | "demo" }> {
  return insightWrite(`/insights/feedback${qs({ person })}`, { insight, event });
}
