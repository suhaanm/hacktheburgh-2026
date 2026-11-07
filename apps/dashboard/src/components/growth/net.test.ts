import { describe, expect, it } from "vitest";
import { classify } from "../../lib/fallback";
import { envelope, failure, isMissing, qs, type Reached } from "./net";

const WHO = { service: "The engine", flag: "UNDERSTUDY_X_CUE" };
const http = (status: number, body: unknown): Reached => ({ reached: true, status, body });

describe("missing or not", () => {
  it("treats a down service, a missing route and a server error as 'show example data'", () => {
    expect(isMissing({ reached: false })).toBe(true);
    expect(isMissing(http(404, null))).toBe(true);
    expect(isMissing(http(405, null))).toBe(true);
    expect(isMissing(http(501, null))).toBe(true);
    expect(isMissing(http(503, null))).toBe(true);
  });
  it("does not hide a refusal or a bad request behind example data", () => {
    expect(isMissing(http(403, null))).toBe(false);
    expect(isMissing(http(422, null))).toBe(false);
    expect(isMissing(http(200, {}))).toBe(false);
  });
});

describe("the note under the badge", () => {
  it("says calmly that the route is not there yet", () => {
    const why = classify(failure(http(404, { error: { code: "not_found", message: "There is no such route or item." } })), WHO);
    expect(why.kind).toBe("missing");
    expect(why.message).toContain("does not have this route yet");
  });
  it("names the switch when the Cue layer is off", () => {
    const why = classify(failure(http(404, { error: { code: "extension_off", message: "Cue is off." } })), WHO);
    expect(why.kind).toBe("extension_off");
    expect(why.message).toContain("UNDERSTUDY_X_CUE=1");
  });
  it("says the engine is not running when it cannot be reached", () => {
    expect(classify(failure({ reached: false }), WHO).kind).toBe("offline");
  });
});

describe("query and envelope", () => {
  it("leaves out empty values", () => {
    expect(qs({ person: "p_a", skill: null, stream: "assist" })).toBe("?person=p_a&stream=assist");
    expect(qs({ person: null })).toBe("");
  });
  it("reads an envelope or a bare body", () => {
    expect(envelope<{ a: number }>({ meta: { n: 1 }, data: { a: 2 } }).data).toEqual({ a: 2 });
    expect(envelope<{ a: number }>({ a: 3 }).data).toEqual({ a: 3 });
    expect(envelope<{ a: number }>({ data: { a: 4 } }).meta).toBeNull();
  });
});
