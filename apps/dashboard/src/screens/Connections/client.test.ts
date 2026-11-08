import { describe, expect, it } from "vitest";
import { createClient, ConnectionsError } from "./client";
import fixture from "./fixture.json";
import { connectBody, type Connection } from "./model";

const all = (fixture as { data: Connection[] }).data;
const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

function fakeFetch(handler: (url: string, init: RequestInit) => Response | Promise<Response>) {
  const calls: { url: string; init: RequestInit }[] = [];
  const f = (async (url: string, init: RequestInit = {}) => { calls.push({ url: String(url), init }); return handler(String(url), init); }) as unknown as typeof fetch;
  return { f, calls };
}
const down = () => fakeFetch(() => { throw new TypeError("network"); });

describe("with the engine", () => {
  it("reads the role's list and returns it as live data", async () => {
    const { f, calls } = fakeFetch(() => json(200, { meta: {}, data: all.slice(0, 3) }));
    const r = await createClient(f, "/engine").list("programmer");
    expect(r.example).toBe(false);
    expect(r.items).toHaveLength(3);
    expect(calls[0].url).toBe("/engine/connections?role=programmer");
    expect(calls[0].init.method).toBe("GET");
  });

  it("sends the worker's click as JSON with the worker actor, and the token only in that one body", async () => {
    const { f, calls } = fakeFetch(() => json(200, { meta: {}, data: { ...all[0], state: "connected", mode: "real" } }));
    const c = createClient(f, "/engine");
    const jira = all.find((x) => x.id === "jira") as Connection;
    await c.connect("jira", connectBody(jira, "real", { site: "https://a.example.org", username: "u@example.org", JIRA_API_TOKEN: "tok-abcdefgh" }));
    expect(calls[0].url).toBe("/engine/connections/jira/connect");
    expect(calls[0].init.method).toBe("POST");
    expect(calls[0].init.headers).toEqual({ "Content-Type": "application/json", "X-Understudy-Actor": "worker" });
    expect(JSON.parse(String(calls[0].init.body))).toMatchObject({ mode: "real", confirm: true, secrets: { JIRA_API_TOKEN: "tok-abcdefgh" } });
  });

  it("will not send a connect that was not confirmed", async () => {
    const { f, calls } = fakeFetch(() => json(200, { data: all[0] }));
    await expect(createClient(f).connect("github", { mode: "example", confirm: false as unknown as true })).rejects.toBeInstanceOf(ConnectionsError);
    expect(calls).toHaveLength(0);
  });

  it("shows the engine's own refusal in its words and does not fall back to example state", async () => {
    const { f } = fakeFetch((url) => (url.endsWith("/connect") ? json(400, { error: { code: "bad_secret", message: "The token has a space." } }) : json(200, { data: all })));
    const c = createClient(f);
    await c.list();
    await expect(c.connect("slack", { mode: "real", confirm: true, secrets: { SLACK_MCP_XOXP_TOKEN: "x" } })).rejects.toMatchObject({ code: "bad_secret", message: "The token has a space." });
  });

  it("revokes and returns the connection as the engine now has it", async () => {
    const { f, calls } = fakeFetch(() => json(200, { data: { revoked: true, connection: { ...all[0], state: "off" } } }));
    expect((await createClient(f).revoke(all[0].id)).state).toBe("off");
    expect(calls[0].url).toContain("/revoke");
  });
});

describe("without the engine", () => {
  it("shows the example list and says so", async () => {
    const r = await createClient(down().f).list("programmer");
    expect(r.example).toBe(true);
    expect(r.items.map((c) => c.id).sort()).toEqual(["filesystem", "github", "jira", "local_git", "sentry", "slack"]);
    expect(r.items.every((c) => c.state === "off")).toBe(true);
  });

  it("falls back when the layer is off (404 extension_off) or the engine errors", async () => {
    for (const res of [json(404, { error: { code: "extension_off", message: "off" } }), json(503, {})]) {
      expect((await createClient(fakeFetch(() => res).f).list()).example).toBe(true);
    }
  });

  it("keeps the click in example state only, and never keeps a token", async () => {
    const c = createClient(down().f);
    await c.list();
    const jira = all.find((x) => x.id === "jira") as Connection;
    const on = await c.connect("jira", connectBody(jira, "real", { site: "https://a.example.org", username: "u@example.org", JIRA_API_TOKEN: "tok-abcdefgh" }));
    expect(on.state).toBe("connected");
    expect(on.example).toBe(true);
    expect(JSON.stringify(on)).not.toContain("tok-abcdefgh");
    expect(JSON.stringify((await c.list()).items)).not.toContain("tok-abcdefgh");
    expect((await c.revoke("jira")).state).toBe("off");
  });

  it("does not leak local clicks into the shared fixture", async () => {
    const a = createClient(down().f);
    await a.connect("github", { mode: "example", confirm: true });
    const b = createClient(down().f);
    expect((await b.list()).items.find((c) => c.id === "github")?.state).toBe("off");
  });
});
