import { afterEach, describe, expect, it, vi } from "vitest";
import { createHash } from "node:crypto";
import { FakeAuth } from "./FakeAuth";
import { LocalAuth } from "./LocalAuth";
import { authForApproval, needsStepUp, stepUpNotice } from "./gate";
import { hashSub, isFresh, MAX_AUTH_AGE_S } from "./fresh";
import { createAuth } from "./index";

afterEach(() => vi.restoreAllMocks());

describe("freshness rule", () => {
  const now = 1_800_000_000;
  it("accepts a sign-in within 120 seconds, inclusive, and nothing older", () => {
    expect(MAX_AUTH_AGE_S).toBe(120);
    expect(isFresh(now - 5, now)).toBe(true);
    expect(isFresh(now - 120, now)).toBe(true);
    expect(isFresh(now - 121, now)).toBe(false);
  });
  it("does not trust a missing, non-numeric or far-future auth_time", () => {
    expect(isFresh(undefined, now)).toBe(false);
    expect(isFresh(null, now)).toBe(false);
    expect(isFresh(Number.NaN, now)).toBe(false);
    expect(isFresh(now + 600, now)).toBe(false);
  });
});

describe("subHash", () => {
  it("is the first 12 hex characters of SHA-256 of the sub", async () => {
    const sub = "google-oauth2|1234567890";
    const expected = createHash("sha256").update(sub).digest("hex").slice(0, 12);
    const h = await hashSub(sub);
    expect(h).toBe(expected);
    expect(h).toMatch(/^[0-9a-f]{12}$/);
    expect(h).not.toContain("1234567890");
  });
});

describe("the step-up gate on approvals", () => {
  it("steps up only for irreversible and outward items", () => {
    expect(needsStepUp("irreversible")).toBe(true);
    expect(needsStepUp("outward")).toBe(true);
    expect(needsStepUp("normal")).toBe(false);
  });

  it("blocks an irreversible approval without a fresh sign-in, and says why in plain words", async () => {
    const auth = new FakeAuth({ authAgeSec: 600 });
    const g = await authForApproval(auth, "irreversible");
    expect(g.allowed).toBe(false);
    if (!g.allowed) expect(g.message).toMatch(/nothing was approved/);
    expect(auth.stepUpCalls).toBe(1);
  });

  it("blocks when the person closes the sign-in popup", async () => {
    const g = await authForApproval(new FakeAuth({ cancel: true }), "outward");
    expect(g.allowed).toBe(false);
    if (!g.allowed) expect(g.message).toMatch(/closed/);
  });

  it("blocks when the person signs in as a different account", async () => {
    const g = await authForApproval(new FakeAuth({ otherAccount: true }), "irreversible");
    expect(g.allowed).toBe(false);
    if (!g.allowed) expect(g.message).toMatch(/different account/);
  });

  it("allows it with fresh auth and sends the method and the hash only", async () => {
    const auth = new FakeAuth({ authAgeSec: 30, subHash: "0123456789ab" });
    const g = await authForApproval(auth, "irreversible");
    expect(g).toEqual({ allowed: true, auth: { method: "auth0_stepup", sub_hash: "0123456789ab" } });
    if (g.allowed) {
      expect(Object.keys(g.auth).sort()).toEqual(["method", "sub_hash"]);
      expect(JSON.stringify(g)).not.toMatch(/email|name|picture|token/i);
    }
  });

  it("does not ask for a sign-in on a normal item, even with Auth0 on", async () => {
    const auth = new FakeAuth({ authAgeSec: 9999 });
    const g = await authForApproval(auth, "normal");
    expect(g).toEqual({ allowed: true, auth: { method: "local" } });
    expect(auth.stepUpCalls).toBe(0);
  });

  it("local mode is unchanged: approves at once with method local and never touches the network", async () => {
    const fetchSpy = vi.fn(() => { throw new Error("no network in local mode"); });
    vi.stubGlobal("fetch", fetchSpy);
    for (const risk of ["irreversible", "outward", "normal"]) {
      const g = await authForApproval(new LocalAuth(), risk);
      expect(g).toEqual({ allowed: true, auth: { method: "local" } });
    }
    const off = new FakeAuth({ enabled: false, authAgeSec: 9999 });
    expect(await authForApproval(off, "irreversible")).toEqual({ allowed: true, auth: { method: "local" } });
    expect(off.stepUpCalls).toBe(0);
    expect(fetchSpy).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("uses plain language for the reason", () => {
    expect(stepUpNotice("irreversible")).toBe("Approving this cannot be undone, so we ask you to sign in again.");
    expect(stepUpNotice("outward")).toMatch(/sign in again/);
  });
});

describe("which provider is built", () => {
  it("is local by default and when only one Auth0 value is set; nothing is imported or fetched", () => {
    expect(createAuth({}).kind).toBe("local");
    expect(createAuth({ VITE_AUTH0_DOMAIN: "example.eu.auth0.com" }).kind).toBe("local");
    expect(createAuth({ VITE_AUTH0_CLIENT_ID: "abc" }).kind).toBe("local");
    expect(createAuth({ VITE_AUTH0_DOMAIN: " ", VITE_AUTH0_CLIENT_ID: " " }).kind).toBe("local");
    expect(createAuth({}).enabled).toBe(false);
  });
});
