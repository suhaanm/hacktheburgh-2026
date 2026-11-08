// @vitest-environment jsdom
// The sidebar's status reads the live and example sources of the screen you are on. A read whose fallback draws NOTHING (the tasks list, one task, the skills) is
// "quiet": an agent service that is down must not make every screen read "Some example data" when none of them draws any.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, forgetBackoff } from "./api";
import { dataMode, getState, resetSources } from "./store";

const down = () => vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("connection refused"); }));
const answers = (status: number, body: unknown) => vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })));

beforeEach(() => { forgetBackoff(); resetSources(); });
afterEach(() => { vi.unstubAllGlobals(); });

describe("quiet reads", () => {
  it("count nothing when the agent service is down, so the sidebar does not turn 'Some example data'", async () => {
    down();
    const t = await api.tasks();
    expect(t.source).toBe("demo");   // the list still knows it was not live (Track C's list falls back to its own rule)
    await api.skills();
    await api.taskDetail("tk_1");
    expect(getState().demo).toBe(0);
    expect(getState().live).toBe(0);
    expect(dataMode(getState())).toBe("unknown");
  });

  it("count nothing when they answer live either: a live task list is not a source for a screen's numbers", async () => {
    answers(200, []);
    expect((await api.tasks()).source).toBe("live");
    expect(getState().live).toBe(0);
  });

  it("a read that draws example data still counts as example data", async () => {
    down();
    await api.queue("pending");
    expect(getState().demo).toBe(1);
    expect(dataMode(getState())).toBe("demo");
  });

  it("a live read of what a screen draws still counts, and live plus example is mixed", async () => {
    answers(200, { data: [] });
    await api.queue("pending");
    expect(getState().live).toBe(1);
    down();
    forgetBackoff();
    await api.queue("pending");
    expect(dataMode(getState())).toBe("mixed");
  });
});
