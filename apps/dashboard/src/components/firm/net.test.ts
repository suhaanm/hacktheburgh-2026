import { describe, expect, it } from "vitest";
import { ROLE_HEADER, readHeaders, refusalText } from "./net";

describe("the admin role header", () => {
  it("is sent on admin reads and never on worker reads", () => {
    expect(readHeaders("admin")).toEqual({ [ROLE_HEADER]: "admin" });
    expect(readHeaders("worker")).toBeUndefined();
    expect(ROLE_HEADER).toBe("x-understudy-role");
  });
});

describe("a refused admin request, in plain words", () => {
  it("says the start-up token is missing and how to fix it", () => {
    const t = refusalText(403, "admin_token_required");
    expect(t).toMatch(/start-up token/);
    expect(t).toMatch(/make dev/);
    expect(refusalText(403, undefined, true)).toMatch(/start-up token/);
  });
  it("says the screen is for the Admin role", () => {
    expect(refusalText(403, "admin_only")).toMatch(/Admin role/);
  });
  it("says a script or an agent is not answered", () => {
    expect(refusalText(403, "admin_actor_refused")).toMatch(/person at the keyboard/);
    expect(refusalText(403, "worker_actor_required")).toMatch(/person at the keyboard/);
  });
  it("leaves every other answer alone", () => {
    expect(refusalText(404, "extension_off")).toBeNull();
    expect(refusalText(500, "boom")).toBeNull();
    expect(refusalText(403, "something_else")).toBeNull();
  });
});
