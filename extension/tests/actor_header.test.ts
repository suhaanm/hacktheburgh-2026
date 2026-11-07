// @vitest-environment node
// The engine's HTTP guard (understudy_engine/http_guard.py) refuses a browser write that does not name its actor. The extension names itself
// "extension" on every request to the engine, and sends nothing else new (no token, no secret).
import { build } from "esbuild";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { pollConsent } from "../src/background/consent";
import { Batcher } from "../src/background/engine_client";
import { RecordingUploader } from "../src/background/recording";
import { ACTOR, ACTOR_HEADER } from "../src/shared/actor";
import type { L0Event, RecordedStep } from "../src/shared/types";
import { repo } from "./helpers";

const ev: L0Event = { schema: 1, id: "ev_00000001", t: "2026-11-07T14:00:00.000Z", origin: "real", actor: "human", person: "p_9f3a", role: "benefits-processor", source: "browser", type: "click" };
const headersOf = (init: RequestInit | undefined): Record<string, string> => Object.fromEntries(Object.entries((init?.headers ?? {}) as Record<string, string>).map(([k, v]) => [k.toLowerCase(), v]));

describe("actor header", () => {
  it("is exactly x-understudy-actor: extension", () => {
    expect(ACTOR_HEADER).toBe("x-understudy-actor");
    expect(ACTOR).toBe("extension");
  });

  it("POST /events sends the actor, the JSON content type and nothing else", async () => {
    const calls: { url: string; init: RequestInit }[] = [];
    const fetchMock = vi.fn(async (url: string, init: RequestInit) => {
      calls.push({ url, init });
      return new Response(JSON.stringify({ accepted: 1, rejected: [] }), { status: 200 });
    });
    const b = new Batcher({
      fetch: fetchMock as unknown as typeof fetch,
      getUrl: async () => "http://127.0.0.1:7700",
      load: async () => [],
      save: async () => undefined,
      setTimer: () => 1,
      clearTimer: () => undefined,
      now: () => 0,
    });
    await b.add(ev);
    await b.flush();
    expect(calls).toHaveLength(1);
    expect(calls[0]!.url).toBe("http://127.0.0.1:7700/events");
    expect(calls[0]!.init.method).toBe("POST");
    expect(headersOf(calls[0]!.init)).toEqual({ "content-type": "application/json", "x-understudy-actor": "extension" });
  });

  it("the L1 recording upload and the consent poll send it too", async () => {
    const seen: RequestInit[] = [];
    const f = vi.fn(async (_url: string, init: RequestInit) => {
      seen.push(init);
      return new Response("[]", { status: 200 });
    });
    await pollConsent(f as unknown as typeof fetch, "http://127.0.0.1:7700");
    expect(headersOf(seen[0])).toEqual({ accept: "application/json", "x-understudy-actor": "extension" });
    const up = new RecordingUploader({
      fetch: f as unknown as typeof fetch,
      getUrl: async () => "http://127.0.0.1:7700",
      getTargets: () => ["calc-entry-3x"],
      identity: () => ({ person: "p_9f3a", role: "benefits-processor" }),
      now: () => 0,
      uuid: () => "00000000-0000-4000-8000-000000000001",
    });
    up.addStep({ op: "goto", url_template: "/step/1", t: "2026-11-07T14:00:00.000Z" } as unknown as RecordedStep);
    await up.flush();
    expect(headersOf(seen[1])).toEqual({ "content-type": "application/json", "x-understudy-actor": "extension" });
  });

  it("the service worker bundle carries the header, and no bundle sends a token header", async () => {
    const out = mkdtempSync(join(tmpdir(), "understudy-ext-actor-"));
    await build({ entryPoints: { worker: join(repo, "extension/src/background/worker.ts") }, outdir: out, bundle: true, format: "iife", target: "chrome116", platform: "browser", logLevel: "silent" });
    const code = readFileSync(join(out, "worker.js"), "utf8");
    expect(code).toContain("x-understudy-actor");
    expect(code).toContain('"extension"');
    expect(code.toLowerCase()).not.toContain("x-understudy-token");
  });
});
