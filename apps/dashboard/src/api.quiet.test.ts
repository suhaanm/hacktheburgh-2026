// @vitest-environment jsdom
// The sidebar's status reads the live and example sources of the screen you are on. A read whose fallback draws NOTHING (the tasks list, one task, the skills) is
// "quiet": an agent service that is down must not make every screen read "Some example data" when none of them draws any.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, forgetBackoff } from "./api";
import { dataMode, getState, resetSources, setState } from "./store";

const down = () => vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("connection refused"); }));
const answers = (status: number, body: unknown) => vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })));

beforeEach(() => { forgetBackoff(); resetSources(); setState({ extReady: true, ext: {} }); });   // /health has answered: no read waits for it
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

describe("calm unknown: the engine answered that nothing is recorded for this worker", () => {
  const unknown = { error: { code: "unknown_person", message: "No such worker." } };
  it("is not example data: a benefits processor's missing commit habits leave the sidebar on Live", async () => {
    answers(404, unknown);
    const r = await api.gitHabits("p_learn01");
    expect(r.why?.status).toBe(404);          // the screen still hears the 404 (Growth turns it into its own calm line)
    expect(getState().demo).toBe(0);
    answers(422, unknown);
    await api.calendarWeek("p_learn01");
    await api.genome("t_entitlement_check", "p_learn01").catch(() => undefined);   // a plain read that is refused with 422 throws: the screen shows the error, nothing is counted
    answers(404, unknown);
    await api.genome("t_entitlement_check", "p_learn01");
    await api.workGraph("p_learn01");
    expect(getState().demo).toBe(0);
  });
  it("is still example data when no service answered, or the route is missing, or the engine failed", async () => {
    down();
    await api.gitHabits("p_learn01");
    expect(getState().demo).toBe(1);
    resetSources(); forgetBackoff();
    answers(404, undefined);                  // a 404 with no error of its own: the route is not there
    await api.gitHabits("p_learn01");
    expect(getState().demo).toBe(1);
    resetSources(); forgetBackoff();
    answers(502, unknown);
    await api.calendarWeek("p_learn01");
    expect(getState().demo).toBe(1);
  });
  it("applies only to the reads that ask for it: any other read of an unknown worker is still example data", async () => {
    answers(404, unknown);
    await api.queue("pending");
    expect(getState().demo).toBe(1);
  });
});
