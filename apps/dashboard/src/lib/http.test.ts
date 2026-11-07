import { describe, expect, it } from "vitest";
import { isWrite, notReadyReason, requestBody, requestHeaders } from "./http";

describe("request headers", () => {
  it("sends nothing extra on a read", () => {
    expect(requestHeaders("GET")).toBeUndefined();
    expect(requestHeaders("head")).toBeUndefined();
    expect(requestBody("GET", undefined)).toBeUndefined();
  });
  it("sends JSON and the worker actor on every kind of write, even with no body", () => {
    for (const m of ["POST", "PUT", "PATCH", "DELETE", "post"]) {
      expect(isWrite(m)).toBe(true);
      expect(requestHeaders(m)).toEqual({ "Content-Type": "application/json", "X-Understudy-Actor": "worker" });
      expect(requestBody(m, undefined)).toBe("{}");
    }
  });
  it("names the approval actor only when asked, and never another one", () => {
    expect(requestHeaders("POST", "worker_approval")?.["X-Understudy-Actor"]).toBe("worker_approval");
    expect(requestHeaders("POST", "worker")?.["X-Understudy-Actor"]).toBe("worker");
  });
  it("sends the body it is given", () => {
    expect(requestBody("PUT", { markdown: "a" })).toBe('{"markdown":"a"}');
  });
  it("explains a refused release in plain words only when the token is the reason", () => {
    expect(notReadyReason(403, "token_required", false)).toMatch(/make dev/);
    expect(notReadyReason(403, "bad_token", false)).toMatch(/not ready/);
    expect(notReadyReason(403, "write_refused", true)).toMatch(/Nothing was changed/); // the dev server found no token file
    expect(notReadyReason(403, "write_refused", false)).toBeNull();
    expect(notReadyReason(404, "token_required", true)).toBeNull();
    expect(notReadyReason(422, undefined, false)).toBeNull();
  });
});
