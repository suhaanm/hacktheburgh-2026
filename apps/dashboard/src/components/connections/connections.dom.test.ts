// @vitest-environment jsdom
// The chips and the panel in a real DOM: every chip is off, nothing connects without the click on Connect, the consent lines are printed before it, a token is
// typed into a password field and is gone from the DOM the moment it is handed over, and Revoke asks first.
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import fixture from "../../screens/Connections/fixture.json";
import { forRole, type ConnectionsClient } from "../../screens/Connections/client";
import { wordCount, BUDGET, type Connection } from "../../screens/Connections/model";
import { ConnectionChips } from "./ConnectionChips";
import { ConnectionsPanel } from "./ConnectionsPanel";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const all = (fixture as { data: Connection[] }).data;
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x)) as T;

function fakeClient(opts: { example?: boolean; fail?: string } = {}) {
  const state = new Map(clone(all).map((c) => [c.id, c]));
  const calls: { op: string; id?: string; body?: unknown }[] = [];
  const client: ConnectionsClient = {
    async list(role) { calls.push({ op: "list" }); const items = forRole([...state.values()], role); return { items: clone(items), example: opts.example ?? false }; },
    async connect(id, body) {
      calls.push({ op: "connect", id, body });
      if (opts.fail) throw new Error(opts.fail);
      const c = state.get(id) as Connection;
      Object.assign(c, { state: "connected", mode: body.mode, example: body.mode === "example" });
      return clone(c);
    },
    async reconfirm(id) { calls.push({ op: "reconfirm", id }); const c = state.get(id) as Connection; c.state = "connected"; return clone(c); },
    async revoke(id) { calls.push({ op: "revoke", id }); const c = state.get(id) as Connection; Object.assign(c, { state: "off", mode: null, example: false }); return clone(c); },
  };
  return { client, calls, state };
}

let host: HTMLDivElement;
let root: Root;
beforeEach(() => { host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host); });
afterEach(() => { act(() => root.unmount()); host.remove(); });

const flush = async () => { await act(async () => { await new Promise((r) => setTimeout(r, 0)); }); };
const click = async (el: Element | null | undefined) => { expect(el, "element to click").toBeTruthy(); await act(async () => { (el as HTMLElement).click(); }); await flush(); };
const button = (label: string | RegExp) => [...host.querySelectorAll("button")].find((b) => (typeof label === "string" ? b.textContent === label || b.getAttribute("aria-label") === label : label.test(b.textContent ?? "") || label.test(b.getAttribute("aria-label") ?? "")));
const typeInto = async (input: HTMLInputElement, value: string) => {
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!;
    setter.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
};

describe("ConnectionChips (the first-run role card)", () => {
  it("shows the role's tools as chips, every one off, and connects nothing by itself", async () => {
    const { client, calls } = fakeClient();
    await act(async () => { root.render(createElement(ConnectionChips, { role: "programmer", client })); });
    await flush();
    const chips = [...host.querySelectorAll(".cx-chip")];
    expect(chips.map((c) => c.querySelector(".cx-chip__name")?.textContent)).toEqual(["GitHub", "Git", "Jira", "Slack", "Sentry", "Files"].map((n) => n));
    expect(chips.every((c) => c.getAttribute("data-state") === "off")).toBe(true);
    expect(host.querySelector(".pill")).toBeNull();
    expect(calls.map((c) => c.op)).toEqual(["list"]);
    expect(host.querySelector("h2")?.textContent).toBe("Connect your tools");
  });

  it("flags the source-available licence and the unmaintained server on the chip itself", async () => {
    const { client } = fakeClient();
    await act(async () => { root.render(createElement(ConnectionChips, { role: "programmer", client })); });
    await flush();
    expect(host.textContent).toContain("Source-available licence");
    const data = fakeClient();
    root.unmount();
    root = createRoot(host);
    await act(async () => { root.render(createElement(ConnectionChips, { role: "data-analyst", client: data.client })); });
    await flush();
    expect(host.textContent).toContain("Vendor says unmaintained");
  });

  it("a click on a chip shows the consent lines and still connects nothing; only Connect does", async () => {
    const { client, calls } = fakeClient();
    const seen: string[][] = [];
    await act(async () => { root.render(createElement(ConnectionChips, { role: "programmer", client, onChange: (ids) => seen.push(ids) })); });
    await flush();
    await click(host.querySelector(".cx-chip"));
    const region = host.querySelector('[role="region"]') as HTMLElement;
    expect(region.textContent).toContain("Example data: invented and kept on this Mac.");
    expect(region.textContent).toContain("No account is used");
    expect(region.textContent).toContain("Revoke any time");
    expect(calls.filter((c) => c.op === "connect")).toHaveLength(0);
    expect(seen).toEqual([]);
    await click(button("Connect"));
    expect(calls.filter((c) => c.op === "connect")).toEqual([{ op: "connect", id: "github", body: { mode: "example", confirm: true } }]);
    expect(seen).toEqual([["github"]]);
    const chip = host.querySelector(".cx-chip") as HTMLElement;
    expect(chip.getAttribute("data-state")).toBe("connected");
    expect(chip.querySelector(".pill")?.textContent).toBe("Example");
  });

  it("'Not now' closes the consent and connects nothing", async () => {
    const { client, calls } = fakeClient();
    await act(async () => { root.render(createElement(ConnectionChips, { role: "programmer", client })); });
    await flush();
    await click(host.querySelector(".cx-chip"));
    await click(button("Not now"));
    expect(host.querySelector('[role="region"]')).toBeNull();
    expect(calls.some((c) => c.op === "connect")).toBe(false);
  });

  it("a connected chip can be revoked in one click", async () => {
    const { client, calls } = fakeClient();
    const seen: string[][] = [];
    await act(async () => { root.render(createElement(ConnectionChips, { role: "programmer", client, onChange: (ids) => seen.push(ids) })); });
    await flush();
    await click(host.querySelector(".cx-chip"));
    await click(button("Connect"));
    await click(host.querySelector(".cx-chip"));
    await click(button("Revoke"));
    expect(calls.filter((c) => c.op === "revoke")).toHaveLength(1);
    expect(seen).toEqual([["github"], []]);
  });

  it("says plainly when it could not connect and changes nothing", async () => {
    const { client } = fakeClient({ fail: "It could not be connected. Nothing was changed." });
    await act(async () => { root.render(createElement(ConnectionChips, { role: "programmer", client })); });
    await flush();
    await click(host.querySelector(".cx-chip"));
    await click(button("Connect"));
    expect(host.querySelector('[role="alert"]')?.textContent).toBe("It could not be connected. Nothing was changed.");
    expect((host.querySelector(".cx-chip") as HTMLElement).getAttribute("data-state")).toBe("off");
  });

  it("says when these are example connections", async () => {
    const { client } = fakeClient({ example: true });
    await act(async () => { root.render(createElement(ConnectionChips, { role: "benefits-processor", client })); });
    await flush();
    expect(host.textContent).toContain("Example connections: the engine is not running.");
  });
});

describe("ConnectionsPanel (Settings)", () => {
  it("lists every tool by set, all off, each with one Connect button, and prints where the traffic goes", async () => {
    const { client, calls } = fakeClient();
    await act(async () => { root.render(createElement(ConnectionsPanel, { client })); });
    await flush();
    expect(calls.map((c) => c.op), "mounting the panel only reads").toEqual(["list"]);
    expect([...host.querySelectorAll(".cx-group > summary")].map((h) => h.textContent)).toEqual(["Dev tools (6)", "Data tools (6)", "Benefits tools (3)"]);
    expect([...host.querySelectorAll(".cx-group")].every((d) => !(d as HTMLDetailsElement).open), "nothing is on, so every set starts closed").toBe(true);
    expect(host.querySelectorAll(".cx-row")).toHaveLength(15);
    expect(host.querySelectorAll(".cx-row .pill, .cx-row .cx-dot"), "an off row carries no state decoration").toHaveLength(0);
    expect(host.textContent).toContain("outside the frame guard");
    for (const row of host.querySelectorAll(".cx-row")) {
      expect(wordCount(row.querySelector(".cx-row__meta")?.textContent ?? ""), row.id).toBeLessThanOrEqual(BUDGET.rowMetaWords);
      expect([...row.querySelectorAll("button")].map((b) => b.textContent)).toEqual(["Connect"]);
    }
  });

  it("an example connect needs the consent lines and one click", async () => {
    const { client, calls } = fakeClient();
    await act(async () => { root.render(createElement(ConnectionsPanel, { client })); });
    await flush();
    await click(button("Connect GitHub"));
    const form = host.querySelector("form") as HTMLElement;
    expect(form.textContent).toContain("Example data: invented and kept on this Mac.");
    expect(calls.some((c) => c.op === "connect")).toBe(false);
    await click(form.querySelector('button[type="submit"]'));
    expect(calls.filter((c) => c.op === "connect")).toEqual([{ op: "connect", id: "github", body: { mode: "example", confirm: true } }]);
    expect(host.querySelector("#conn-github .pill")?.textContent).toBe("Example");
    expect(host.querySelector(".cx-row")?.id).toBe("conn-github");
  });

  it("a real connect shows the publisher, package, version, hosts and 'with your token' before the click, takes the token in a password field and leaves none in the page", async () => {
    const { client, calls } = fakeClient();
    await act(async () => { root.render(createElement(ConnectionsPanel, { client })); });
    await flush();
    await click(button("Connect Slack"));
    await click([...host.querySelectorAll("form .segmented button")].find((b) => b.textContent === "Real"));
    const form = host.querySelector("form") as HTMLElement;
    expect(form.textContent).toContain("Knack starts Slack server 1.3.0 (npm slack-mcp-server) by korotovsky");
    expect(form.textContent).toContain("It talks to slack.com with your token.");
    expect(form.textContent).toContain("(community author)");
    expect(form.textContent).not.toContain("Community server");
    const input = form.querySelector('input[type="password"]') as HTMLInputElement;
    expect(input.autocomplete).toBe("off");
    await click(form.querySelector('button[type="submit"]'));
    expect(host.querySelector('[role="alert"]')?.textContent).toBe("Slack user token is needed.");
    expect(calls.some((c) => c.op === "connect")).toBe(false);
    await typeInto(input, "bad token with spaces");
    await click(form.querySelector('button[type="submit"]'));
    expect(host.querySelector('[role="alert"]')?.textContent).toContain("The token has a space");
    expect(host.querySelector('[role="alert"]')?.textContent).not.toContain("bad token");
    await typeInto(input, "xoxp-1111-2222-SECRETSECRET");
    await click(form.querySelector('button[type="submit"]'));
    const sent = calls.find((c) => c.op === "connect") as { body: { mode: string; confirm: boolean; secrets: Record<string, string> } };
    expect(sent.body).toEqual({ mode: "real", confirm: true, secrets: { SLACK_MCP_XOXP_TOKEN: "xoxp-1111-2222-SECRETSECRET" } });
    expect(host.innerHTML).not.toContain("xoxp-1111");
    expect(host.querySelector("#conn-slack .pill")?.textContent).toBe("On");
    expect(host.querySelector("input")).toBeNull();
  });

  it("asks for the folder or the address a real connection needs", async () => {
    const { client } = fakeClient();
    await act(async () => { root.render(createElement(ConnectionsPanel, { client })); });
    await flush();
    await click(button("Connect Jira"));
    await click([...host.querySelectorAll("form .segmented button")].find((b) => b.textContent === "Real"));
    expect([...host.querySelectorAll("form label")].map((l) => l.textContent)).toEqual(["Jira site address", "Jira email", "Jira API token"]);
    expect(host.querySelectorAll("form input[type=password]")).toHaveLength(1);
  });

  it("a connection that has only an example gives no Real choice", async () => {
    const { client, state } = fakeClient();
    (state.get("graph_outlook") as Connection).modes.real = null;
    await act(async () => { root.render(createElement(ConnectionsPanel, { client })); });
    await flush();
    await click(button("Connect Outlook calendar"));
    expect(host.querySelector("form .segmented")).toBeNull();
  });

  it("Revoke asks first, says what happens, keeps by default and only the confirm click revokes", async () => {
    const { client, calls } = fakeClient();
    await act(async () => { root.render(createElement(ConnectionsPanel, { client })); });
    await flush();
    await click(button("Connect GitHub"));
    await click(host.querySelector('form button[type="submit"]'));
    await click(button("Revoke GitHub"));
    const confirm = host.querySelector(".confirm-row") as HTMLElement;
    expect(confirm.textContent).toContain("Revoke GitHub?");
    expect(confirm.textContent).toContain("Its token is forgotten and it stops.");
    expect(document.activeElement?.textContent).toBe("Keep");
    expect(calls.some((c) => c.op === "revoke")).toBe(false);
    await click([...confirm.querySelectorAll("button")].find((b) => b.textContent === "Keep"));
    expect(calls.some((c) => c.op === "revoke")).toBe(false);
    await click(button("Revoke GitHub"));
    await click([...host.querySelectorAll(".confirm-row button")].find((b) => b.textContent === "Revoke"));
    expect(calls.filter((c) => c.op === "revoke")).toHaveLength(1);
    expect(host.querySelector("#conn-github .pill"), "off again: no state decoration").toBeNull();
    expect(button("Connect GitHub")).toBeTruthy();
  });

  it("a connection whose version or command changed needs a confirm again, and says so", async () => {
    const { client, calls, state } = fakeClient();
    Object.assign(state.get("slack") as Connection, { state: "needs_reconfirm", mode: "real", example: false });
    await act(async () => { root.render(createElement(ConnectionsPanel, { client })); });
    await flush();
    expect(host.querySelector("#conn-slack")?.textContent).toContain("It changed since you agreed.");
    expect(host.querySelector("#conn-slack .pill")?.textContent).toBe("Changed");
    await click(button("Confirm again"));
    expect(calls.filter((c) => c.op === "reconfirm")).toHaveLength(1);
    expect(host.querySelector("#conn-slack .pill")?.textContent).toBe("On");
  });

  it("opens the set that has something on, and only that set", async () => {
    const { client, state } = fakeClient();
    Object.assign(state.get("notion") as Connection, { state: "connected", mode: "example", example: true });
    await act(async () => { root.render(createElement(ConnectionsPanel, { client })); });
    await flush();
    expect([...host.querySelectorAll(".cx-group")].map((d) => (d as HTMLDetailsElement).open)).toEqual([false, true, false]);
    expect(host.querySelector("#conn-notion .pill")?.textContent).toBe("Example");
    expect(host.querySelector("#conn-notion .cx-flag")?.textContent).toBe("Vendor says unmaintained");
  });

  it("puts what is on first, and marks the example list when the engine is away", async () => {
    const { client, state } = fakeClient({ example: true });
    Object.assign(state.get("sentry") as Connection, { state: "connected", mode: "example", example: true });
    await act(async () => { root.render(createElement(ConnectionsPanel, { client })); });
    await flush();
    expect(host.textContent).toContain("Example connections");
    const devRows = [...host.querySelectorAll('[aria-label="Dev tools"] .cx-row')].map((r) => r.id);
    expect(devRows[0]).toBe("conn-sentry");
  });

  it("is the default export Settings finds by glob, and takes no required props", async () => {
    const mod = await import("./ConnectionsPanel");
    expect(typeof mod.default).toBe("function");
    expect(mod.default).toBe(ConnectionsPanel);
    const chips = await import("./ConnectionChips");
    expect(chips.default).toBe(ConnectionChips);
    vi.fn();
  });
});
