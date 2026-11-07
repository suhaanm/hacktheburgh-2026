import { createHash } from "node:crypto";
import { describe, expect, it } from "vitest";
import { hashDomain, hashLabel, hashQuery, normaliseLabel, randomHex, sha256Hex } from "../src/shared/hash";

const ref = (s: string) => createHash("sha256").update(s, "utf8").digest("hex");

describe("sha256Hex", () => {
  it.each(["", "abc", "a".repeat(55), "a".repeat(56), "a".repeat(64), "a".repeat(119), "x".repeat(1000),
    "naïve café 日本語 \u{1F600} emoji", "line1\nline2\u0000nul"])("matches node crypto for %j", (s) => {
    expect(sha256Hex(s)).toBe(ref(s));
  });
});

describe("salted identifier hashes", () => {
  const salt = "a".repeat(32);
  it("have the schema's shape", () => {
    expect(hashLabel(salt, "Calculate")).toMatch(/^h:[0-9a-f]{12}$/);
    expect(hashDomain(salt, "127.0.0.1:7801")).toMatch(/^d:[0-9a-f]{12}$/);
    expect(hashQuery(salt, "tax credit")).toMatch(/^h:[0-9a-f]{12}$/);
  });
  it("are deterministic and normalise case and whitespace", () => {
    expect(hashLabel(salt, "  Check   Cliff Edges ")).toBe(hashLabel(salt, "check cliff edges"));
    expect(normaliseLabel("  A\n b\t")).toBe("a b");
  });
  it("depend on the salt, so two installs cannot be linked", () => {
    expect(hashLabel("a".repeat(32), "x")).not.toBe(hashLabel("b".repeat(32), "x"));
    expect(hashDomain("a".repeat(32), "h")).not.toBe(hashDomain("b".repeat(32), "h"));
  });
  it("differ across kinds for the same text", () => {
    expect(hashLabel(salt, "same")).not.toBe(hashQuery(salt, "same"));
  });
  it("randomHex gives hex of the right length", () => {
    expect(randomHex(16)).toMatch(/^[0-9a-f]{32}$/);
    expect(randomHex(16)).not.toBe(randomHex(16));
  });
});
