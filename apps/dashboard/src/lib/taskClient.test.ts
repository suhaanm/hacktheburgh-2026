import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { answerQuestion, decideConsent, readTask, submitTask } from "./taskClient";
import { NOT_STARTED, SEND_FAILED, TOO_MANY } from "./taskbox";

interface Seen { url: string; method?: string; headers?: Record<string, string>; body?: string }
let seen: Seen[] = [];
const reply = (status: number, body: unknown, headers: Record<string, string> = {}) => ({ ok: status >= 200 && status < 300, status, json: async () => { if (body === undefined) throw new Error("no json"); return body; }, headers: { get: (k: string) => headers[k.toLowerCase()] ?? null } });
const stub = (...answers: (ReturnType<typeof reply> | Error)[]) => {
  let i = 0;
  vi.stubGlobal("fetch", async (url: string, init: { method?: string; headers?: Record<string, string>; body?: string }) => {
    seen.push({ url, method: init.method, headers: init.headers, body: init.body });
    const a = answers[Math.min(i++, answers.length - 1)];
    if (a instanceof Error) throw a;
    return a;
  });
};

beforeEach(() => { seen = []; });
afterEach(() => { vi.unstubAllGlobals(); });

describe("sending a task", () => {
  it("posts JSON as the worker to /agent/tasks and reads the 201", async () => {
    stub(reply(201, { task_id: "tk_1", route: "answer", summary: "On it.", needs_consent: null, question: null }));
    const r = await submitTask("Check this", "typed");
    expect(r).toMatchObject({ kind: "placed", sub: { id: "tk_1", route: "answer", summary: "On it." } });
    expect(seen).toHaveLength(1);
    expect(seen[0].url).toBe("/agent/tasks");
    expect(seen[0].method).toBe("POST");
    expect(seen[0].headers).toEqual({ "Content-Type": "application/json", "X-Understudy-Actor": "worker" });
    expect(JSON.parse(seen[0].body!)).toEqual({ text: "Check this", source: "typed" });
  });
  it("says it was a voice task when it was", async () => {
    stub(reply(201, { task_id: "tk_2", route: "answer", summary: "" }));
    await submitTask("Hello", "voice");
    expect(JSON.parse(seen[0].body!).source).toBe("voice");
  });
  it("is unavailable when nothing answers or the proxy has nothing behind it, and that is not an error", async () => {
    for (const s of [new Error("connection refused"), reply(502, null), reply(503, { error: { message: "x" } }), reply(504, null), reply(404, undefined)]) {
      stub(s);
      expect(await submitTask("x"), String((s as { status?: number }).status ?? s)).toEqual({ kind: "unavailable" });
    }
    expect(NOT_STARTED).toMatch(/nothing was started/);
  });
  it("names the limit of three at a time", async () => {
    stub(reply(429, { error: { code: "too_many_tasks", message: "Too many" } }));
    expect(await submitTask("x")).toEqual({ kind: "error", message: TOO_MANY });
  });
  it("shows the service's own short message for a refusal, a fixed sentence for the rest", async () => {
    stub(reply(422, { error: { code: "bad_task", message: "That task is too vague." } }));
    expect(await submitTask("x")).toEqual({ kind: "error", message: "That task is too vague." });
    stub(reply(500, undefined));
    expect(await submitTask("x")).toEqual({ kind: "error", message: SEND_FAILED });
  });
  it("is an error, not a task, when a 201 carries no task id", async () => {
    stub(reply(201, { summary: "hello" }));
    expect(await submitTask("x")).toEqual({ kind: "error", message: SEND_FAILED });
  });
  it("asks once more when the start-up token changed under it, and not again", async () => {
    stub(reply(403, { error: { code: "token_invalid" } }), reply(201, { task_id: "tk_9", route: "answer", summary: "ok" }));
    expect((await submitTask("x")).kind).toBe("placed");
    expect(seen).toHaveLength(2);
    stub(reply(403, { error: { code: "token_invalid" } }));
    seen = [];
    expect((await submitTask("x")).kind).toBe("error");
    expect(seen).toHaveLength(2);
  });
});

describe("answering a consent card", () => {
  it("sends the choice as the approval actor, and nothing else is ever sent as it", async () => {
    stub(reply(200, { ok: true }));
    expect(await decideConsent("tk_1", "allow")).toEqual({ kind: "done" });
    expect(seen[0].url).toBe("/agent/tasks/tk_1/consent");
    expect(seen[0].headers).toEqual({ "Content-Type": "application/json", "X-Understudy-Actor": "worker_approval" });
    expect(JSON.parse(seen[0].body!)).toEqual({ choice: "allow" });
    await submitTask("x");
    await answerQuestion("tk_1", "a");
    expect(seen.slice(1).every((s) => s.headers?.["X-Understudy-Actor"] === "worker")).toBe(true);
  });
  it("sends everything and decline as written, and puts the id in the path safely", async () => {
    stub(reply(200, {}));
    await decideConsent("tk_1", "everything");
    await decideConsent("a/b?c", "decline");
    expect(JSON.parse(seen[0].body!)).toEqual({ choice: "everything" });
    expect(seen[1].url).toBe("/agent/tasks/a%2Fb%3Fc/consent");
    expect(JSON.parse(seen[1].body!)).toEqual({ choice: "decline" });
  });
  it("says so when the service is gone or refuses", async () => {
    stub(new Error("down"));
    expect(await decideConsent("tk_1", "allow")).toEqual({ kind: "unavailable" });
    stub(reply(409, { error: { message: "That task already started." } }));
    expect(await decideConsent("tk_1", "allow")).toEqual({ kind: "error", message: "That task already started." });
  });
});

describe("answering a question and reading a task", () => {
  it("posts the option id", async () => {
    stub(reply(200, {}));
    expect(await answerQuestion("tk_1", "opt_a")).toEqual({ kind: "done" });
    expect(JSON.parse(seen[0].body!)).toEqual({ option_id: "opt_a" });
  });
  it("reads the task as it is, with the full inline answer once it is done", async () => {
    stub(reply(200, { task_id: "tk_1", state: "done", result: "Done: 3 files.", answer: "x".repeat(2000), latest: null, reason: null, steps: [] }));
    const t = (await readTask("tk_1"))!;
    expect(t.state).toBe("done");
    expect(t.answer).toHaveLength(1500);
    expect(t.result).toBe("Done: 3 files.");
    expect(seen[0].method).toBe("GET");
    expect(seen[0].headers).toBeUndefined();
  });
  it("is null when the service does not answer, and tolerates a body of any shape", async () => {
    stub(new Error("down"));
    expect(await readTask("tk_1")).toBeNull();
    for (const body of [null, "x", 5, [], {}]) { stub(reply(200, body)); const t = await readTask("tk_1"); expect(t === null || t.state === "", JSON.stringify(body)).toBe(true); }
  });
});
