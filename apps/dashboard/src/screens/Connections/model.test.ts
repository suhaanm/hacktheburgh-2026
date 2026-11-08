import { describe, expect, it } from "vitest";
import fixture from "./fixture.json";
import {
  BUDGET, byGroup, connectBody, consentFor, fieldsFor, hasReal, isOn, metaLine, onFirst, problemWith, stateTone, stateWord, usageLine, wordCount,
  type Connection,
} from "./model";

const all = (fixture as { data: Connection[] }).data;
const get = (id: string): Connection => ({ ...(all.find((c) => c.id === id) as Connection) });
const on = (id: string, patch: Partial<Connection> = {}): Connection => ({ ...get(id), state: "connected", mode: "example", example: true, ...patch });

describe("the example list", () => {
  it("holds every curated preset, every one OFF, by the sets the owner asked for", () => {
    expect(all).toHaveLength(15);
    expect(all.every((c) => c.state === "off" && c.mode === null && c.routines.length === 0)).toBe(true);
    expect(byGroup(all).map((g) => [g.group, g.items.length])).toEqual([["dev", 6], ["data", 6], ["benefits", 3]]);
    expect(all.filter((c) => c.roles.includes("programmer")).map((c) => c.id).sort()).toEqual(["filesystem", "github", "jira", "local_git", "sentry", "slack"]);
    expect(all.filter((c) => c.roles.includes("data-analyst")).map((c) => c.id).sort()).toEqual(["bigquery", "google_workspace", "jupyter", "notion", "postgres", "slack", "sqlite"]);
    expect(all.filter((c) => c.roles.includes("benefits-processor")).map((c) => c.id).sort()).toEqual(["graph_outlook", "graph_teams", "sharepoint"]);
  });

  it("keeps every printed line inside the word budgets", () => {
    for (const c of all) {
      expect(wordCount(c.app), c.id).toBeLessThanOrEqual(BUDGET.pillWords + 2);
      expect(wordCount(c.short), c.id).toBeLessThanOrEqual(BUDGET.rowMetaWords);
      expect(wordCount(c.caution), c.id).toBeLessThanOrEqual(BUDGET.rowMetaWords);
      for (const m of [c.modes.example, c.modes.real]) if (m) expect(wordCount(m.summary), `${c.id} ${m.mode}`).toBeLessThanOrEqual(BUDGET.consentWords);
      expect(wordCount(metaLine(c))).toBeLessThanOrEqual(BUDGET.rowMetaWords);
    }
    for (const w of ["Connect", "Cancel", "Revoke", "Keep", "Confirm again", "Not now", "Close"]) expect(wordCount(w)).toBeLessThanOrEqual(BUDGET.buttonWords);
    for (const s of ["Off", "On", "Changed", "Needs setup", "Problem"]) expect(wordCount(s)).toBeLessThanOrEqual(BUDGET.pillWords);
  });

  it("has well-formed consent lines (no stray full stops, a closing line, the example says no account)", () => {
    for (const c of all) {
      for (const m of [c.modes.example, c.modes.real]) {
        if (!m) continue;
        expect(m.summary, c.id).not.toMatch(/\.\s*\./);
        expect(m.lines.every((l) => /[.]$/.test(l)), c.id).toBe(true);
        expect(m.summary).toContain("Revoke any time");
      }
      expect(c.modes.example.summary).toContain("No account is used");
      expect(c.modes.example.example).toBe(true);
    }
  });

  it("names publisher, package, version, hosts and 'with your token' on every real consent that needs a token", () => {
    for (const c of all) {
      const r = c.modes.real;
      if (!r || r.package === null || c.kind === "source") continue;
      expect(r.summary, c.id).toContain(r.version as string);
      expect(r.summary, c.id).toContain(r.package);
      expect(r.summary, c.id).toContain(r.publisher.split(" (")[0]);
      if (r.needs_token) expect(r.summary, c.id).toContain("with your token");
      for (const h of r.hosts) expect(r.summary).toContain(h);
    }
  });

  it("flags the unmaintained Notion server and the source-available Sentry licence on the chip itself", () => {
    expect(get("notion").caution).toBe("Vendor says unmaintained");
    expect(get("sentry").caution).toBe("Source-available licence");
    expect(all.filter((c) => c.caution).map((c) => c.id).sort(), "only the two honesty flags are printed on a chip; who made a server is in the consent lines").toEqual(["notion", "sentry"]);
    for (const id of ["slack", "jira", "jupyter", "google_workspace", "sharepoint"]) expect(get(id).modes.real?.summary, id).toMatch(/\(community( author)?\)|community author/);
  });
});

describe("state words", () => {
  it("says one short thing per state, and the colour only repeats it", () => {
    expect(stateWord(get("github"))).toBe("Off");
    expect(stateWord(on("github"))).toBe("On");
    expect(stateWord(on("github", { mode: "real", example: false }))).toBe("On");
    expect(stateWord(on("github", { state: "needs_reconfirm" }))).toBe("Changed");
    expect(stateWord(on("github", { state: "needs_setup" }))).toBe("Needs setup");
    expect(stateWord(on("github", { state: "error" }))).toBe("Problem");
    expect([stateTone(get("github")), stateTone(on("github")), stateTone(on("github", { state: "needs_reconfirm" })), stateTone(on("github", { state: "error" }))]).toEqual(["idle", "good", "warn", "bad"]);
  });

  it("counts only: what it has read, never what", () => {
    expect(usageLine(on("github"))).toBe("Not used yet");
    const used = on("github", { usage: { calls: 13, reads: 12, changes_asked: 1, refused: 0, needed_click: 1, last_call: "2026-11-08T00:00:00Z" } });
    expect(usageLine(used)).toBe("12 reads, 1 asked to change");
    expect(usageLine(on("github", { usage: { ...used.usage, calls: 1, reads: 1, changes_asked: 0 } }))).toBe("1 read, no changes");
    expect(wordCount(usageLine(used))).toBeLessThanOrEqual(BUDGET.rowMetaWords);
    expect(metaLine(get("github"))).toBe("Issues, pull requests, code");
    expect(metaLine(on("github", { state: "needs_reconfirm" }))).toBe("It changed since you agreed.");
    expect(metaLine(on("github", { state: "error", reason: "launcher_missing" }))).toBe("It needs Node, uv or Docker.");
    expect(metaLine(on("github", { state: "error", reason: "something_new" }))).toBe("It did not start.");
    for (const r of ["launcher_missing", "timeout", "server_error", "missing_param", "bad_param", "keeps_stopping", "x"]) expect(wordCount(metaLine(on("github", { state: "error", reason: r })))).toBeLessThanOrEqual(BUDGET.rowMetaWords);
  });

  it("puts what is on first and keeps the pack's order otherwise", () => {
    const list = [get("github"), on("jira"), get("slack"), on("sentry")];
    expect(onFirst(list).map((c) => c.id)).toEqual(["jira", "sentry", "github", "slack"]);
    expect(isOn(get("github"))).toBe(false);
    expect(isOn(on("github", { state: "needs_setup" }))).toBe(true);
  });
});

describe("the fields of a real connection and what is sent", () => {
  it("asks for exactly the folder, address, user and token the preset needs, the token as a secret", () => {
    expect(fieldsFor(get("github"), "example")).toEqual([]);
    expect(fieldsFor(get("github"), "real").map((f) => [f.key, f.secret])).toEqual([["GITHUB_PERSONAL_ACCESS_TOKEN", true]]);
    expect(fieldsFor(get("jira"), "real").map((f) => [f.key, f.kind])).toEqual([["site", "url"], ["username", "text"], ["JIRA_API_TOKEN", "secret"]]);
    expect(fieldsFor(get("filesystem"), "real").map((f) => [f.key, f.kind])).toEqual([["folder", "path"]]);
    expect(hasReal(get("github"))).toBe(true);
  });

  it("refuses an empty field, a token with a space or a quote, a relative path and an address without a scheme, in plain words and without repeating the token", () => {
    const jira = get("jira");
    const good = { site: "https://acme.example.org", username: "worker@example.org", JIRA_API_TOKEN: "abcd1234efgh" };
    expect(problemWith(jira, "real", good)).toBeNull();
    expect(problemWith(jira, "real", { ...good, site: "" })).toBe("Jira site address is needed.");
    expect(problemWith(jira, "real", { ...good, site: "acme.example.org" })).toContain("must be an address");
    for (const bad of ["has space token", 'has"quote', "back\\slash", "abc"]) {
      const p = problemWith(jira, "real", { ...good, JIRA_API_TOKEN: bad }) as string;
      expect(p).toContain("The token has a space");
      expect(p).not.toContain(bad);
    }
    expect(problemWith(get("filesystem"), "real", { folder: "relative/dir" })).toContain("full folder path");
    expect(problemWith(get("filesystem"), "real", { folder: "/a/../b" })).toContain("full folder path");
    expect(problemWith(get("filesystem"), "real", { folder: "/Users/example/work" })).toBeNull();
    expect(problemWith(get("github"), "example", {})).toBeNull();
  });

  it("builds the one click: confirm is true, an example sends nothing else, a real one splits values from the token", () => {
    expect(connectBody(get("github"), "example", { ignored: "x" })).toEqual({ mode: "example", confirm: true });
    const body = connectBody(get("jira"), "real", { site: " https://acme.example.org ", username: "w@example.org", JIRA_API_TOKEN: " abcd1234efgh " });
    expect(body).toEqual({ mode: "real", confirm: true, params: { site: "https://acme.example.org", username: "w@example.org" }, secrets: { JIRA_API_TOKEN: "abcd1234efgh" } });
    expect(consentFor(get("github"), "real")?.mode).toBe("real");
    expect(consentFor(get("graph_outlook"), "example")?.example).toBe(true);
  });
});
