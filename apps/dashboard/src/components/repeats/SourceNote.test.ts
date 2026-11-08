// A service that did not answer is a connection fact, never a label about the data (owner, 8 Nov 2026): the fallback's own sentences say what happened to the
// request and carry no word about example, sample or stand-in data, and no screen draws a note for them.
import { describe, expect, it } from "vitest";
import * as fallback from "../../lib/fallback";
import * as common from "../common";
import { classify } from "../../lib/fallback";

const WHO = { service: "The engine", flag: "UNDERSTUDY_X_HITLIST" };
const WORDS = /example|sample|stand[- ]in|made[- ]up|synthetic|simulated|your own data/i;

describe("the fallback sentences", () => {
  it("name the connection fact and never the kind of data drawn instead", () => {
    const all = [
      classify({ reached: false }, WHO),
      classify({ reached: true, status: 404, body: { error: { code: "extension_off", message: "layer is off" } } }, WHO),
      classify({ reached: true, status: 404, body: {} }, WHO),
      classify({ reached: true, status: 501 }, WHO),
      classify({ reached: true, status: 500, body: { error: { message: "boom" } } }, WHO),
      classify({ reached: true, status: 503 }, WHO),
    ];
    expect(all.map((f) => f.kind)).toEqual(["offline", "extension_off", "missing", "missing", "error", "error"]);
    for (const f of all) expect(f.message, f.kind).not.toMatch(WORDS);
    expect(all[1].message).toContain("UNDERSTUDY_X_HITLIST=1");
  });

  it("have no one-line note, label or badge component left", () => {
    for (const name of ["EXAMPLE_LINE", "FALLBACK_LABEL", "needsNote"]) expect(name in fallback, name).toBe(false);
    for (const name of ["SourceNote", "ExampleBadge"]) expect(name in common, name).toBe(false);
  });
});
