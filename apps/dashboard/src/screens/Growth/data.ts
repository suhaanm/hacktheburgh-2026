// Data for the Growth screen. A small client of its own (the shared api.ts is not built for DELETE or file export):
// reads `GET /growth`, `GET /cue/ledger`, writes `DELETE /cue/ledger` as the worker. When the engine is down, the Cue layer is
// off (404 extension_off) or the route is missing, the example stories answer instead and the screen says so.
import { ApiError, ENGINE_URL, api, type Loaded } from "../../api";
import { classify, type Fallback } from "../../lib/fallback";
import { requestBody, requestHeaders } from "../../lib/http";
import { noteSource } from "../../store";
import type { AnalyticMeta } from "../../types";
import { STORIES, emptyGrowth, loadBundle, type GrowthBundle, type Story } from "../../fixtures/growth";
import type { Envelope, LedgerRow, WireDeleted, WireGrowth, WireLedger } from "../../components/growth/wire";
import { deletedCount } from "../../components/growth/model";
import { envelope, failure, isMissing, qs, type Reached } from "../../components/growth/net";

export { STORIES };
export type { Story };

const WHO = { service: "The engine", flag: "UNDERSTUDY_X_CUE" };
const TIMEOUT_MS = 40_000;

async function call(path: string, method: "GET" | "DELETE" = "GET"): Promise<Reached> {
  const ctl = new AbortController();
  const timer = window.setTimeout(() => ctl.abort(), TIMEOUT_MS);
  try {
    // Every write carries the worker actor and a JSON body (lib/http), as the engine requires.
    const res = await fetch(`${ENGINE_URL}${path}`, { method, signal: ctl.signal, headers: requestHeaders(method), body: requestBody(method, undefined) });
    let body: unknown = null;
    try { body = await res.json(); } catch { body = null; }
    return { reached: true, status: res.status, body };
  } catch {
    return { reached: false };
  } finally {
    window.clearTimeout(timer);
  }
}

function errorOf(r: Reached & { reached: true }): ApiError {
  const e = (r.body as { error?: { code?: string; message?: string } } | null)?.error;
  return new ApiError(r.status, e?.code ?? `http_${r.status}`, e?.message ?? `The engine answered with status ${r.status}.`);
}

/* -- Who we are -------------------------------------------------------------------------------- */
let identity: Promise<string | null> | null = null;
/** The person id the engine knows the worker by, once onboarding has run; null before that (the engine then uses its default). */
export function whoAmI(): Promise<string | null> {
  identity ??= api.identity().then((i) => i?.person ?? null).catch(() => null);
  return identity;
}

/* -- Example state: what the stories become when the worker deletes the ledger ----------------- */
const cleared = new Set<Story>();
const bundles = new Map<Story, GrowthBundle>();
async function bundleOf(story: Story): Promise<GrowthBundle> {
  let b = bundles.get(story);
  if (!b) { b = await loadBundle(story); bundles.set(story, b); }
  return b;
}
export const isCleared = (story: Story) => cleared.has(story);
export function restoreExample(story: Story): void { cleared.delete(story); }

const asLoaded = <T,>(env: Envelope<T>, source: "live" | "demo", why: Fallback | null): Loaded<T> => ({ data: env.data, meta: env.meta as unknown as AnalyticMeta | null, source, why });

/* -- Reads ------------------------------------------------------------------------------------- */
export async function loadGrowth(skill: string | null, story: Story): Promise<Loaded<WireGrowth>> {
  const person = await whoAmI();
  const r = await call(`/growth${qs({ person, skill })}`);
  // The engine is there and Cue is on, but nobody is set up yet: that is a real, empty answer, not a missing feature.
  if (r.reached && r.status === 404 && (r.body as { error?: { code?: string } } | null)?.error?.code === "unknown_person") {
    noteSource("live");
    const b = await bundleOf(story);
    // The engine answered, so this is not example data: nothing is set up, nothing is counted. The meta is plain, never the sample's (which carries
    // the sample's origin, its n and its note).
    const meta = { origin: "real", n: 0, n_unit: "occurrences", split: null, interval_level: 0.95, note: "Nobody is set up yet, so nothing is counted.", generated_at: new Date().toISOString() } as unknown as Envelope<WireGrowth>["meta"];
    void b;
    return asLoaded(emptyGrowth("", skill, meta), "live", null);
  }
  if (isMissing(r)) {
    const why = classify(failure(r), WHO);
    noteSource("demo");
    const b = await bundleOf(story);
    if (cleared.has(story)) return asLoaded(emptyGrowth(b.person, skill, b.overall.meta), "demo", why);
    const env = skill ? b.skills[skill] ?? b.overall : b.overall;
    return asLoaded(JSON.parse(JSON.stringify(env)) as Envelope<WireGrowth>, "demo", why);
  }
  if (r.reached && r.status >= 400) throw errorOf(r);
  noteSource("live");
  return asLoaded(envelope<WireGrowth>(r.reached ? r.body : null), "live", null);
}

export interface LedgerView {
  rows: LedgerRow[];
  counts: { assist: number; delegated: number; automation: number } | null;
}

/** The ledger rows the screen needs: delegated and overnight work for the "done for you" list, assist rows only when the curve cannot be drawn yet. */
export async function loadLedger(story: Story, wantAssist: boolean): Promise<Loaded<LedgerView>> {
  const person = await whoAmI();
  const streams = wantAssist ? (["delegated", "automation", "assist"] as const) : (["delegated", "automation"] as const);
  const rs = await Promise.all(streams.map((stream) => call(`/cue/ledger${qs({ person, stream, limit: stream === "assist" ? "12" : "10" })}`)));
  const bad = rs.find((r) => isMissing(r));
  if (bad) {
    const why = classify(failure(bad), WHO);
    const b = await bundleOf(story);
    const env = JSON.parse(JSON.stringify(b.ledger)) as Envelope<WireLedger>;
    if (cleared.has(story)) return asLoaded<LedgerView>({ meta: env.meta, data: { rows: [], counts: { assist: 0, delegated: 0, automation: 0 } } }, "demo", why);
    return asLoaded<LedgerView>({ meta: env.meta, data: { rows: env.data.rows, counts: env.data.counts ?? null } }, "demo", why);
  }
  const hardFail = rs.find((r) => r.reached && r.status >= 400);
  if (hardFail && hardFail.reached) throw errorOf(hardFail);
  const envs = rs.map((r) => envelope<WireLedger>(r.reached ? r.body : null));
  const rows = envs.flatMap((e) => e.data?.rows ?? []);
  const counts = envs.map((e) => e.data?.counts).find((c) => !!c) ?? null;
  return asLoaded<LedgerView>({ meta: envs[0].meta, data: { rows, counts } }, "live", null);
}

/* -- Export and delete ------------------------------------------------------------------------- */
/** The ledger as the engine would export it: a JSON body, nothing else. */
export async function exportLedger(story: Story, example: boolean): Promise<{ filename: string; text: string }> {
  const stamp = new Date().toISOString().slice(0, 10);
  const filename = `understudy-assist-ledger-${stamp}.json`;
  if (!example) {
    const person = await whoAmI();
    const r = await call(`/cue/ledger/export${qs({ person })}`);
    if (!r.reached) throw new ApiError(0, "offline", "The engine is not running, so your record could not be exported. Start it and try again.");
    if (r.status >= 400) throw errorOf(r);
    return { filename, text: JSON.stringify(r.body, null, 2) };
  }
  const b = await bundleOf(story);
  const rows = cleared.has(story) ? [] : b.ledger.data.rows;
  return { filename, text: JSON.stringify({ origin: "example data (synthetic)", rows }, null, 2) };
}

/** Delete the worker's ledger. Worker-only on the engine. In example mode it clears the example, so the empty state can be seen. */
export async function deleteLedger(story: Story, example: boolean): Promise<number> {
  if (example) {
    const b = await bundleOf(story);
    const n = b.ledger.data.rows.length;
    cleared.add(story);
    return n;
  }
  const person = await whoAmI();
  const r = await call(`/cue/ledger${qs({ person })}`, "DELETE");
  if (!r.reached) throw new ApiError(0, "offline", "The engine is not running, so nothing was deleted. Start it and try again.");
  if (r.status >= 400) throw errorOf(r);
  const body = envelope<WireDeleted>(r.body).data;
  return body ? deletedCount(body) : 0;
}

/** Trigger a browser download of text the worker asked for. */
export function downloadText(filename: string, text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
